"""anyjev_server.py — AnyJev FastBridge for System 1 Decision Protocol.

Supports:
1. Native System 1 / Jev protocol: POST /v1/systemone
2. Laya Sidecar compatibility endpoint: POST /ask
3. OpenAI Chat Completions classifier: POST /v1/chat/completions
4. Health and metadata endpoints: GET /health, GET /version, GET /capabilities

Optimized for Tacit-4B / Tacit-2B on llama-server with:
- Prefix-First KV-cache prompt structure (0 ms re-prefill on cached rubrics)
- Pre-warmed token ID cache for zero /tokenize network overhead
- Balanced two-pass position debiasing (forward + reverse option ordering)
- Correct Qwen3 <think>\\n\\n</think>\\n\\n template alignment
- Semantic invariants for visual (@image:) and web (@url:) artifacts
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx
import numpy as np
import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("anyjev-server")

LLAMA_URL = os.environ.get("LLAMA_URL", "http://127.0.0.1:8081").rstrip("/")
PORT = int(os.environ.get("PORT", "8080"))
MCP_PORT = int(os.environ.get("MCP_PORT", "8787"))
CTX_SIZE = int(os.environ.get("CTX_SIZE", "1024"))
MODEL_NAME = os.environ.get("MODEL_NAME", "Tacit-4B-Q4_K_M")
DEBIASE_MODE = os.environ.get("DEBIASE_MODE", "two_pass")  # 'two_pass' (forward+reverse) or 'raw' (1 pass)

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Global reusable HTTP client with connection pooling
_client = httpx.Client(
    timeout=30.0,
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
)


def truncate_state(state: str, max_chars: int = 1500) -> str:
    """Safely clamp state text to prevent prompt overflow in limited context slots.
    Preserves recent context and instruction tail if state is long.
    """
    if not state or len(state) <= max_chars:
        return state
    head_len = max_chars // 3
    tail_len = max_chars - head_len - 20
    return state[:head_len] + "\n...[truncated]...\n" + state[-tail_len:]


# -----------------------------------------------------------------------------
# Fast Tacit Engine with Prefix-First KV-Caching
# -----------------------------------------------------------------------------

class FastTacitEngine:
    """High-throughput, low-latency System 1 Decision Engine for Tacit/Qwen3."""

    def __init__(self, base_url: str = LLAMA_URL):
        self.base_url = base_url.rstrip("/")
        self.client = _client
        self._token_cache: Dict[str, int] = {}
        self._init_token_cache()

    def _init_token_cache(self) -> None:
        """Pre-populate token IDs for standard option letters, digits, and words."""
        labels_to_probe = (
            list(LETTERS)
            + [str(i) for i in range(10)]
            + ["Yes", "No", "yes", "no", "true", "false"]
        )
        for label in labels_to_probe:
            for cand in (label, " " + label):
                try:
                    r = self.client.post(
                        f"{self.base_url}/tokenize",
                        json={"content": cand, "add_special": False},
                        timeout=5.0,
                    )
                    if r.is_success:
                        toks = r.json().get("tokens", [])
                        if len(toks) == 1:
                            self._token_cache[cand] = toks[0]
                            if cand == label or label not in self._token_cache:
                                self._token_cache[label] = toks[0]
                except Exception:
                    pass

    def get_token_id(self, label: str) -> int:
        """Retrieve token ID from cache or resolve on the fly."""
        if label in self._token_cache:
            return self._token_cache[label]
        for cand in (label, " " + label):
            try:
                r = self.client.post(
                    f"{self.base_url}/tokenize",
                    json={"content": cand, "add_special": False},
                    timeout=5.0,
                )
                if r.is_success:
                    toks = r.json().get("tokens", [])
                    if len(toks) == 1:
                        self._token_cache[label] = toks[0]
                        return toks[0]
            except Exception:
                pass
        return 0

    def get_logprobs(self, prompt: str, token_ids: Sequence[int]) -> np.ndarray:
        """Fetch next-token log probabilities with prefix KV caching enabled."""
        body = {
            "prompt": prompt,
            "max_tokens": 1,
            "temperature": 0.0,
            "logprobs": max(40, len(token_ids) * 2),
            "cache_prompt": True,
        }
        try:
            resp = self.client.post(
                f"{self.base_url}/v1/completions",
                json=body,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            top_list = data["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
            by_id = {item["id"]: float(item["logprob"]) for item in top_list}
            min_observed = min((float(item["logprob"]) for item in top_list), default=-15.0)
            fallback = min_observed - 2.0
            return np.array([by_id.get(tid, fallback) for tid in token_ids], dtype=np.float64)
        except Exception as e:
            log.error("llama-server completions error: %s", e)
            raise RuntimeError(f"Backend llama-server unavailable: {e}") from e

    def decide_choice(
        self,
        state: str,
        instructions: str,
        options: List[Tuple[str, str]],
        mode: str = DEBIASE_MODE,
    ) -> Dict[str, Any]:
        """Evaluate a discrete choice question between candidate options.
        
        options: list of (key, description)
        mode: 'raw' (single forward pass) or 'two_pass' (forward + reverse debiased)
        """
        state = truncate_state(state)
        k = len(options)
        if k == 0:
            return {"choice": None, "confidence": 0.0, "probabilities": {}}
        if k == 1:
            return {"choice": options[0][0], "confidence": 1.0, "probabilities": {options[0][0]: 1.0}}

        labels = list(LETTERS[:k])
        label_ids = [self.get_token_id(l) for l in labels]

        # Pass 1: Forward order
        opt_lines_fwd = [
            f"{labels[i]}. {options[i][0]}: {options[i][1]}" if options[i][1] else f"{labels[i]}. {options[i][0]}"
            for i in range(k)
        ]
        sys_fwd = (
            "<|im_start|>system\n"
            "You are a decision function. You will be given a question with options, and a state.\n"
            f"Question: {instructions.strip()}\n"
            "Options:\n" + "\n".join(opt_lines_fwd) + "\n"
            "Reply with the answer label only: no words, no punctuation, no explanation.<|im_end|>\n"
        )
        user_part = (
            f"<|im_start|>user\nState:\n{state.strip()}\n"
            "Answer with the letter only.<|im_end|>\n"
            "<|im_start|>assistant\n<think>\n\n</think>\n\n"
        )

        lp1 = self.get_logprobs(sys_fwd + user_part, label_ids)

        if mode == "two_pass" and k >= 2:
            # Pass 2: Reverse order
            rev_indices = list(reversed(range(k)))
            opt_lines_rev = [
                f"{labels[i]}. {options[rev_indices[i]][0]}: {options[rev_indices[i]][1]}"
                if options[rev_indices[i]][1]
                else f"{labels[i]}. {options[rev_indices[i]][0]}"
                for i in range(k)
            ]
            sys_rev = (
                "<|im_start|>system\n"
                "You are a decision function. You will be given a question with options, and a state.\n"
                f"Question: {instructions.strip()}\n"
                "Options:\n" + "\n".join(opt_lines_rev) + "\n"
                "Reply with the answer label only: no words, no punctuation, no explanation.<|im_end|>\n"
            )
            lp2_raw = self.get_logprobs(sys_rev + user_part, label_ids)
            lp2 = np.zeros_like(lp1)
            for pos_i, orig_i in enumerate(rev_indices):
                lp2[orig_i] = lp2_raw[pos_i]
            combined_lp = (lp1 + lp2) / 2.0
        else:
            combined_lp = lp1

        # Normalized softmax distribution
        combined_lp -= np.max(combined_lp)
        probs = np.exp(combined_lp)
        probs /= np.sum(probs)

        best_idx = int(np.argmax(probs))
        dist = {options[i][0]: float(probs[i]) for i in range(k)}

        return {
            "type": "choice",
            "choice": options[best_idx][0],
            "confidence": round(float(probs[best_idx]), 4),
            "probabilities": dist,
        }

    def decide_noul(
        self,
        state: str,
        instructions: str,
        criteria: Optional[Dict[str, str]] = None,
        mode: str = "raw",
    ) -> Dict[str, Any]:
        """Evaluate a binary yes/no statement."""
        state = truncate_state(state)
        yes_id = self.get_token_id("Yes")
        no_id = self.get_token_id("No")

        desc_text = ""
        if criteria and isinstance(criteria, dict):
            desc_text = "\n" + "\n".join([f"- {k}: {v}" for k, v in criteria.items() if v])

        sys_prompt = (
            "<|im_start|>system\n"
            "You are a decision function. You will be given a question and a state.\n"
            f"Question: {instructions.strip()}{desc_text}\n"
            "Answer Yes or No.\n"
            "Reply with the answer word only: no words, no punctuation, no explanation.<|im_end|>\n"
        )
        user_part = (
            f"<|im_start|>user\nState:\n{state.strip()}\n"
            "Answer Yes or No.<|im_end|>\n"
            "<|im_start|>assistant\n<think>\n\n</think>\n\n"
        )

        lp = self.get_logprobs(sys_prompt + user_part, [yes_id, no_id])
        lp -= np.max(lp)
        p = np.exp(lp)
        p /= np.sum(p)
        p_true = float(p[0])

        return {
            "type": "noul",
            "noul": round(p_true, 4),
            "passed": p_true >= 0.5,
            "confidence": round(max(p_true, 1.0 - p_true), 4),
        }

    def decide_score(
        self,
        state: str,
        instructions: str,
        levels: List[Tuple[str, str]],
        mode: str = "raw",
    ) -> Dict[str, Any]:
        """Evaluate an ordinal score/rubric rating."""
        state = truncate_state(state)
        k = len(levels)
        digits = [str(i + 1) for i in range(k)]
        token_ids = [self.get_token_id(d) for d in digits]

        level_lines = [
            f"{digits[i]}. {levels[i][0]}: {levels[i][1]}" if levels[i][1] else f"{digits[i]}. {levels[i][0]}"
            for i in range(k)
        ]
        sys_prompt = (
            "<|im_start|>system\n"
            "You are a decision function. Pick the level that applies (the levels are ordered):\n"
            f"Question: {instructions.strip()}\n"
            "Levels:\n" + "\n".join(level_lines) + "\n"
            "Reply with the level number only: no words, no punctuation, no explanation.<|im_end|>\n"
        )
        user_part = (
            f"<|im_start|>user\nState:\n{state.strip()}\n"
            "Answer with the number only.<|im_end|>\n"
            "<|im_start|>assistant\n<think>\n\n</think>\n\n"
        )

        lp = self.get_logprobs(sys_prompt + user_part, token_ids)
        lp -= np.max(lp)
        p = np.exp(lp)
        p /= np.sum(p)

        best_idx = int(np.argmax(p))
        dist = {levels[i][0]: float(p[i]) for i in range(k)}
        expected_value = float(sum(i * p[i] for i in range(k)))

        return {
            "type": "score",
            "score": round(expected_value, 4),
            "level": levels[best_idx][0],
            "confidence": round(float(p[best_idx]), 4),
            "probabilities": dist,
            "value": round(expected_value, 4),
        }


# Global Fast Engine
fast_engine = FastTacitEngine()


# -----------------------------------------------------------------------------
# Decision Execution Pipeline
# -----------------------------------------------------------------------------

def parse_options(criteria: Any) -> List[Tuple[str, str]]:
    """Parse criteria dictionary or list into list of (key, desc) tuples."""
    if isinstance(criteria, dict):
        return [(str(k), str(v or "")) for k, v in criteria.items()]
    elif isinstance(criteria, list):
        return [(str(item), "") for item in criteria]
    return [("yes", ""), ("no", "")]


def execute_decision(state: Any, questions: Any) -> Dict[str, Any]:
    """Execute decision for a state across one or multiple typed questions."""
    t0 = time.time()
    state_str = json.dumps(state, ensure_ascii=False) if isinstance(state, (dict, list)) else str(state)

    if isinstance(questions, list):
        q_dict: Dict[str, Any] = {
            q.get("id", f"q{i}"): q for i, q in enumerate(questions) if isinstance(q, dict)
        }
    elif isinstance(questions, dict):
        q_dict = questions
    else:
        q_dict = {}

    answers: Dict[str, Any] = {}

    for qid, q_data in q_dict.items():
        q_type = q_data.get("type", "choice")
        instructions = q_data.get("instructions", "")
        criteria = q_data.get("criteria", {})

        if q_type == "choice":
            options = parse_options(criteria)
            res = fast_engine.decide_choice(state_str, instructions, options)
            answers[qid] = res

        elif q_type == "noul":
            crit_dict = criteria if isinstance(criteria, dict) else {}
            res = fast_engine.decide_noul(state_str, instructions, crit_dict)
            answers[qid] = res

        elif q_type == "score":
            levels = parse_options(criteria) if criteria else [(str(i + 1), "") for i in range(5)]
            res = fast_engine.decide_score(state_str, instructions, levels)
            answers[qid] = res

    # Semantic invariants for tool_decision
    # If the user request clearly contains visual artifacts (@image:) or external URLs (@url:),
    # or if an explicit tool category (marketplace, filesystem, vision, terminal) has high confidence,
    # prevent false direct_chat degradation.
    if "tool_decision" in answers:
        td_ans = answers["tool_decision"]
        choice = td_ans.get("choice")
        probs = td_ans.get("probabilities", {})

        has_media_artifact = "@image:" in state_str or "@url:" in state_str
        cat_is_tool_action = False
        if "category" in answers:
            cat_choice = answers["category"].get("choice")
            if cat_choice in (
                "multimedia_and_vision",
                "marketplace_and_commerce",
                "filesystem",
                "terminal_execution",
                "code_and_git",
                "browser_automation",
            ):
                cat_is_tool_action = True

        if choice == "direct_chat" and (has_media_artifact or (cat_is_tool_action and td_ans.get("confidence", 0.0) < 0.70)):
            td_ans["choice"] = "execute_tools"
            if probs:
                p_exec = probs.get("execute_tools", 0.5)
                p_chat = probs.get("direct_chat", 0.5)
                probs["execute_tools"] = max(p_exec, 0.85)
                probs["direct_chat"] = min(p_chat, 0.15)
                td_ans["confidence"] = 0.85

    latency_ms = round((time.time() - t0) * 1000, 2)
    return {"answers": answers, "usage": {"latency_ms": latency_ms}}


# -----------------------------------------------------------------------------
# REST Endpoints
# -----------------------------------------------------------------------------

async def api_health(request: Request) -> JSONResponse:
    """Service health status and underlying llama-server readiness."""
    backend_ok = False
    loop = asyncio.get_running_loop()
    try:
        def _check_backend():
            try:
                r = _client.get(f"{LLAMA_URL}/health", timeout=2.0)
                return r.is_success and r.json().get("status") == "ok"
            except Exception:
                return False

        backend_ok = await loop.run_in_executor(None, _check_backend)
    except Exception as e:
        log.warning("Healthcheck backend check error: %s", e)
        backend_ok = False

    status_code = 200 if backend_ok else 503
    return JSONResponse(
        {
            "ok": backend_ok,
            "status": "ok" if backend_ok else "degraded",
            "device": os.environ.get("DEVICE", "cuda:0"),
            "engine": "anyjev",
            "model": os.path.basename(os.environ.get("MODEL_PATH", "Tacit-4B-Q4_K_M")).replace(".gguf", "").lower(),
            "backend": "llama-server",
            "debiase_mode": DEBIASE_MODE,
        },
        status_code=status_code,
    )


async def api_version(request: Request) -> JSONResponse:
    return JSONResponse({
        "ok": True,
        "version": "0.3.2",
        "engine": "anyjev-fastbridge",
        "primitives": ["choice", "noul", "score"],
    })


async def api_capabilities(request: Request) -> JSONResponse:
    return JSONResponse({
        "ok": True,
        "primitives": ["choice", "noul", "score"],
        "max_len": CTX_SIZE,
        "head_max_len": min(512, CTX_SIZE // 2),
        "max_opts": 32,
        "max_batch": 16,
    })


async def api_systemone(request: Request) -> JSONResponse:
    """Native System 1 / Jev protocol endpoint: POST /v1/systemone."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    state = body.get("state", "")
    questions = body.get("questions", {})
    if not questions:
        return JSONResponse({"error": "questions required"}, status_code=400)

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, execute_decision, state, questions)
    except RuntimeError as e:
        log.error("Inference runtime error in /v1/systemone: %s", e)
        return JSONResponse({"error": str(e)}, status_code=503)
    except Exception as e:
        log.error("Execution error in /v1/systemone: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

    return JSONResponse(result)


async def api_ask(request: Request) -> JSONResponse:
    """Laya Sidecar compatibility endpoint for hermes-laya-tools: POST /ask."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)

    state = body.get("state", "")
    questions = body.get("questions", {})
    if not questions:
        return JSONResponse({"ok": False, "error": "questions required"}, status_code=400)

    loop = asyncio.get_running_loop()
    try:
        res = await loop.run_in_executor(None, execute_decision, state, questions)
    except RuntimeError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=503)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    resp = {
        "ok": True,
        "model": os.path.basename(os.environ.get("MODEL_PATH", "Tacit-4B-Q4_K_M")).replace(".gguf", "").lower(),
        "device": os.environ.get("DEVICE", "cuda:0"),
        "answers": res.get("answers", {}),
        "latency_ms": res.get("usage", {}).get("latency_ms", 0.0),
        "usage": res.get("usage", {}),
    }
    return JSONResponse(resp)


async def api_chat_completions(request: Request) -> JSONResponse:
    """OpenAI-compatible /v1/chat/completions endpoint for hermes-token-router."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    messages = body.get("messages", [])
    model = body.get("model", MODEL_NAME)

    full_prompt_text = ""
    for m in messages:
        c = m.get("content", "")
        if c:
            full_prompt_text += f"\n{c}"

    toolsets_map: Dict[str, str] = {}
    user_message = ""

    # Parse text format from hermes-token-router:
    # "Available toolsets:\n- name: desc\n...\nUser message:\n..."
    toolsets_match = re.search(
        r"Available toolsets:\s*\n(.*?)(?:\n\s*User message:|\Z)",
        full_prompt_text,
        re.DOTALL | re.IGNORECASE,
    )
    if toolsets_match:
        lines = toolsets_match.group(1).strip().splitlines()
        for line in lines:
            line = line.strip()
            if line.startswith("-") or line.startswith("*"):
                line = line[1:].strip()
            if ":" in line:
                ts_name, ts_desc = line.split(":", 1)
                toolsets_map[ts_name.strip()] = ts_desc.strip()

    user_match = re.search(r"User message:\s*\n(.*)", full_prompt_text, re.DOTALL | re.IGNORECASE)
    if user_match:
        user_message = user_match.group(1).strip()
    else:
        for m in reversed(messages):
            if m.get("role") == "user":
                user_message = str(m.get("content", "")).strip()
                break

    if not toolsets_map:
        tools = body.get("tools", [])
        for t in tools:
            fn = t.get("function", {})
            name = fn.get("name", "")
            desc = fn.get("description", "")
            if name:
                toolsets_map[name] = desc

    if not user_message:
        user_message = full_prompt_text.strip()[:1000]

    # Gate: requires_tools?
    gate_questions = {
        "requires_tools": {
            "type": "noul",
            "instructions": (
                "Does this user request require calling tools/actions (like files, web search, "
                "terminal, git, system actions), or is it pure conversational chat/greeting/general knowledge?"
            ),
        }
    }

    loop = asyncio.get_running_loop()
    try:
        gate_res = await loop.run_in_executor(None, execute_decision, user_message, gate_questions)
        prob_tools = gate_res.get("answers", {}).get("requires_tools", {}).get("noul", 0.5)
    except Exception as e:
        log.warning("Gate check execution error: %s", e)
        prob_tools = 0.5

    # Check for direct chat with safety threshold (>= 0.75 confidence to strip tools)
    if prob_tools < 0.25 and ("@image:" not in user_message and "@url:" not in user_message):
        content_json = {
            "confidence": round(1.0 - prob_tools, 2),
            "action": "no_tools",
            "toolsets": [],
            "reason_code": "anyjev_gate_pass",
        }
    else:
        if toolsets_map:
            criteria = {k: v[:120] for k, v in list(toolsets_map.items())[:16]}
            choice_questions = {
                "toolset_decision": {
                    "type": "choice",
                    "instructions": "Which toolset best fulfills the user's request?",
                    "criteria": criteria,
                }
            }
            try:
                choice_res = await loop.run_in_executor(None, execute_decision, user_message, choice_questions)
                ans = choice_res.get("answers", {}).get("toolset_decision", {})
                top_choice = ans.get("choice")
                probs = ans.get("probabilities", {})
                choice_conf = ans.get("confidence", 0.5)

                chosen = []
                if top_choice and top_choice in toolsets_map:
                    chosen.append(top_choice)
                for ts, p in probs.items():
                    if ts != top_choice and p >= 0.20 and ts in toolsets_map:
                        chosen.append(ts)

                content_json = {
                    "confidence": round(float(choice_conf), 2),
                    "action": "narrow" if chosen else "no_tools",
                    "toolsets": chosen,
                    "reason_code": "anyjev_toolset_choice",
                }
            except Exception as e:
                log.warning("Toolset choice execution error: %s; failing open", e)
                content_json = {
                    "confidence": 0.5,
                    "action": "full",
                    "toolsets": ["all"],
                    "reason_code": "anyjev_fallback_error",
                }
        else:
            content_json = {
                "confidence": 0.5,
                "action": "full",
                "toolsets": ["all"],
                "reason_code": "anyjev_default",
            }

    resp_payload = {
        "id": f"chatcmpl-anyjev-{int(time.time()*1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": json.dumps(content_json),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": max(1, len(user_message) // 4),
            "completion_tokens": 20,
            "total_tokens": max(1, len(user_message) // 4) + 20,
        },
    }
    return JSONResponse(resp_payload)


routes = [
    Route("/health", api_health, methods=["GET"]),
    Route("/version", api_version, methods=["GET"]),
    Route("/capabilities", api_capabilities, methods=["GET"]),
    Route("/v1/systemone", api_systemone, methods=["POST"]),
    Route("/ask", api_ask, methods=["POST"]),
    Route("/v1/chat/completions", api_chat_completions, methods=["POST"]),
]

app = Starlette(
    routes=routes,
    middleware=[
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ],
)

if __name__ == "__main__":
    bind_port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    log.info("Starting AnyJev FastBridge on port %d (backend: %s)", bind_port, LLAMA_URL)
    uvicorn.run(app, host="0.0.0.0", port=bind_port, log_level="info")

"""anyjev_server.py — AnyJev FastBridge for System 1 Decision Protocol.

Supports:
1. Native System 1 / Jev protocol: POST /v1/systemone
2. Laya Sidecar compatibility endpoint: POST /ask
3. OpenAI Chat Completions classifier: POST /v1/chat/completions
4. Health and metadata endpoints: GET /health, GET /version, GET /capabilities
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
from typing import Any, Dict, List, Optional, Sequence

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

# Global reusable HTTP client with connection pooling
_client = httpx.Client(timeout=30.0, limits=httpx.Limits(max_keepalive_connections=20, max_connections=50))


# -----------------------------------------------------------------------------
# LlamaServerBackend for AnyJev
# -----------------------------------------------------------------------------

class LlamaTokenizer:
    """Lightweight tokenizer proxy calling llama-server's /tokenize endpoint."""

    def __init__(self, base_url: str = LLAMA_URL, client: Optional[httpx.Client] = None):
        self.base_url = base_url.rstrip("/")
        self.client = client or _client
        self.chat_template = True

    def encode(self, text: str, add_special_tokens: bool = False) -> List[int]:
        try:
            resp = self.client.post(
                f"{self.base_url}/tokenize",
                json={"content": text, "add_special": add_special_tokens},
                timeout=10.0,
            )
            if resp.is_success:
                data = resp.json()
                return data.get("tokens", [])
            log.warning("Tokenize endpoint returned HTTP %s for %r", resp.status_code, text[:60])
        except Exception as e:
            log.error("Tokenize error for text %r: %s", text[:60], e)
        return []

    def apply_chat_template(
        self,
        messages: List[Dict[str, str]],
        tokenize: bool = False,
        add_generation_prompt: bool = True,
        **kwargs,
    ) -> str:
        parts = []
        for m in messages:
            role = m["role"]
            content = m["content"]
            parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
        if add_generation_prompt:
            parts.append("<|im_start|>assistant\n<think>\n</think>\n")
        rendered = "\n".join(parts)
        if tokenize:
            return self.encode(rendered)
        return rendered


class LlamaServerBackend:
    """AnyJev Backend running over llama-server (OpenAI completions with logprobs)."""

    def __init__(self, base_url: str = LLAMA_URL, model_name: str = MODEL_NAME):
        self.base_url = base_url.rstrip("/")
        self.name = model_name
        self.client = _client
        self.tokenizer = LlamaTokenizer(base_url, client=self.client)

    def _one(self, prompt: str, ids: Sequence[int]) -> np.ndarray:
        body = {
            "prompt": prompt,
            "max_tokens": 1,
            "temperature": 0.0,
            "logprobs": max(50, len(ids) * 2),
        }
        try:
            resp = self.client.post(
                f"{self.base_url}/v1/completions",
                json=body,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.error("LlamaServer completions request failed: %s", e)
            raise RuntimeError(f"Backend llama-server unavailable: {e}") from e

        try:
            top_list = data["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
            by_id = {item["id"]: float(item["logprob"]) for item in top_list}
            # Adaptive lower floor: use (min_observed - 2.0) instead of extreme -30.0
            # to avoid false +23.5 nats exponent explosion in Level 0 debiasing
            min_observed = min((float(item["logprob"]) for item in top_list), default=-15.0)
            fallback_logprob = min_observed - 2.0
        except (KeyError, IndexError, TypeError) as e:
            log.warning("Could not extract logprobs from llama-server response: %s", e)
            raise RuntimeError(f"Malformed logprobs from llama-server: {e}") from e

        return np.array([by_id.get(tid, fallback_logprob) for tid in ids], dtype=np.float64)

    def next_token_logprobs(
        self, prompts: Sequence[str], token_ids: Sequence[Sequence[int]]
    ) -> List[np.ndarray]:
        return [self._one(p, ids) for p, ids in zip(prompts, token_ids)]


# Global AnyJev Decider instance
backend = LlamaServerBackend()
from anyjev import Decider, Question
decider = Decider(backend, level="L0")


# -----------------------------------------------------------------------------
# Decision Helper Logic
# -----------------------------------------------------------------------------

def parse_question(qid: str, q_data: Dict[str, Any]) -> Optional[Question]:
    q_type = q_data.get("type", "choice")
    instructions = q_data.get("instructions", "")
    criteria = q_data.get("criteria", {})

    if q_type == "choice":
        if isinstance(criteria, dict) and criteria:
            options = list(criteria.keys())
            lines = [instructions]
            for opt, desc in criteria.items():
                if desc:
                    lines.append(f"- {opt}: {desc}")
            full_text = "\n".join(lines)
            return Question.choice(full_text, options, name=qid)
        elif isinstance(criteria, list) and criteria:
            return Question.choice(instructions, criteria, name=qid)
        else:
            return Question.choice(instructions, ["yes", "no"], name=qid)

    elif q_type == "noul":
        full_text = instructions
        if isinstance(criteria, dict) and criteria:
            lines = [instructions]
            for opt, desc in criteria.items():
                if desc:
                    lines.append(f"- {opt}: {desc}")
            full_text = "\n".join(lines)
        return Question.noul(full_text, name=qid)

    elif q_type == "score":
        if isinstance(criteria, list) and criteria:
            return Question.score(instructions, levels=criteria, name=qid)
        elif isinstance(criteria, dict) and criteria:
            lines = [instructions]
            for opt, desc in criteria.items():
                if desc:
                    lines.append(f"- {opt}: {desc}")
            full_text = "\n".join(lines)
            return Question.score(full_text, levels=list(criteria.keys()), name=qid)
        else:
            return Question.score(instructions, bins=5, name=qid)

    return None


def execute_decision(state: Any, questions: Any) -> Dict[str, Any]:
    t0 = time.time()
    state_str = json.dumps(state, ensure_ascii=False) if isinstance(state, (dict, list)) else str(state)

    if isinstance(questions, list):
        q_dict: Dict[str, Any] = {q.get("id", f"q{i}"): q for i, q in enumerate(questions) if isinstance(q, dict)}
    elif isinstance(questions, dict):
        q_dict = questions
    else:
        q_dict = {}

    parsed_qs = []
    q_map = {}
    for qid, q_data in q_dict.items():
        q_obj = parse_question(qid, q_data)
        if q_obj:
            parsed_qs.append(q_obj)
            q_map[qid] = q_data

    if not parsed_qs:
        return {"answers": {}, "usage": {"latency_ms": 0.0}}

    res = decider.decide(state_str, parsed_qs)
    answers = {}

    for qid, q_data in q_map.items():
        d = res[qid]
        q_type = q_data.get("type", "choice")

        if q_type == "choice":
            top_choice = str(d.answer)
            answers[qid] = {
                "choice": top_choice,
                "probabilities": d.distribution,
                "confidence": round(float(d.confidence), 4),
            }
        elif q_type == "noul":
            prob_true = float(d.p_true)
            passed = prob_true >= 0.5
            answers[qid] = {
                "noul": round(prob_true, 4),
                "passed": passed,
                "confidence": round(float(d.confidence), 4),
            }
        elif q_type == "score":
            val = getattr(d, "value", None)
            answers[qid] = {
                "score": str(d.answer),
                "probabilities": d.distribution,
                "confidence": round(float(d.confidence), 4),
                "value": round(float(val), 4) if val is not None else None,
            }

    latency_ms = round((time.time() - t0) * 1000, 2)
    return {"answers": answers, "usage": {"latency_ms": latency_ms}}


# -----------------------------------------------------------------------------
# REST Endpoints
# -----------------------------------------------------------------------------

async def api_health(request: Request) -> JSONResponse:
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
        },
        status_code=status_code,
    )


async def api_version(request: Request) -> JSONResponse:
    return JSONResponse({
        "ok": True,
        "version": "0.3.1",
        "engine": "anyjev",
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
    """Laya Sidecar compatibility endpoint for /ask."""
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

    # 1. Gather all message text to parse embedded router headers
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
        # Fallback to standard OpenAI format
        for m in reversed(messages):
            if m.get("role") == "user":
                user_message = str(m.get("content", "")).strip()
                break

    # If tools were passed via OpenAI tools field
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

    if prob_tools < 0.35:
        content_json = {
            "confidence": round(1.0 - prob_tools, 2),
            "action": "no_tools",
            "toolsets": [],
            "reason_code": "anyjev_gate_pass",
        }
    else:
        # Narrow toolsets if available
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

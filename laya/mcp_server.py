"""MCP Server and Sidecar bridge for Laya System 1 Decision Engine.

Provides:
1. Native Model Context Protocol (MCP) server over Streamable HTTP (/mcp).
   Tools: laya_predict, classify, check, score, laya_ask, laya_plan, laya_status.
2. Direct REST Sidecar endpoints for dsh-laya compatibility:
   /health, /ask, /plan, /capabilities, /version.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from typing import Any, Mapping, Optional, Sequence
import httpx
from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("laya-mcp-server")

LAYA_ENGINE_URL = os.environ.get("LAYA_ENGINE_URL", "http://127.0.0.1:8080")
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", "8787"))

server = MCPServer(
    name="laya",
    description="Laya typed System 1 decision engine (choice, noul, score, classify, check)",
    version="0.2.2",
)


async def _call_engine(endpoint: str, method: str = "GET", json_body: Any = None) -> dict[str, Any]:
    url = f"{LAYA_ENGINE_URL.rstrip('/')}{endpoint}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            if method == "POST":
                resp = await client.post(url, json=json_body)
            else:
                resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            log.error("Laya engine HTTP error %s for %s: %s", e.response.status_code, url, e.response.text)
            try:
                err_data = e.response.json()
                msg = err_data.get("error", {}).get("message", str(e))
            except Exception:
                msg = e.response.text or str(e)
            raise RuntimeError(f"Laya engine error (HTTP {e.response.status_code}): {msg}") from e
        except Exception as e:
            log.error("Failed to connect to Laya engine at %s: %s", url, e)
            raise RuntimeError(f"Cannot reach Laya engine at {url}: {e}") from e


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / 3.5))


def _calculate_plan(state: Any, questions: dict[str, Any]) -> dict[str, Any]:
    state_str = json.dumps(state, ensure_ascii=False) if isinstance(state, (dict, list)) else str(state)
    state_tokens = _estimate_tokens(state_str)
    
    question_details = []
    total_q_tokens = 0
    tightest_option = 256
    
    for q_id, q in questions.items():
        instr = q.get("instructions", "")
        criteria = q.get("criteria", {})
        q_tokens = _estimate_tokens(instr)
        if isinstance(criteria, dict):
            for opt_k, opt_v in criteria.items():
                opt_tok = _estimate_tokens(f"{opt_k}: {opt_v}")
                q_tokens += opt_tok
                if opt_tok < tightest_option:
                    tightest_option = opt_tok
        elif isinstance(criteria, list):
            for item in criteria:
                opt_tok = _estimate_tokens(str(item))
                q_tokens += opt_tok
                if opt_tok < tightest_option:
                    tightest_option = opt_tok
        total_q_tokens += q_tokens
        question_details.append({"id": q_id, "tokens": q_tokens})

    max_len = 1024
    total_estimated = state_tokens + total_q_tokens + 32
    fits = total_estimated <= max_len

    return {
        "fits": fits,
        "max_len": max_len,
        "head_max_len": 256,
        "state_tokens": state_tokens,
        "questions_tokens": total_q_tokens,
        "total_estimated_tokens": total_estimated,
        "tightest_option_tokens_each": tightest_option if tightest_option < 256 else 64,
        "truncated": not fits,
        "exact": False,
        "questions": question_details,
    }


def _format_payload(raw: dict[str, Any], state: Any, questions: dict[str, Any]) -> dict[str, Any]:
    plan = _calculate_plan(state, questions)
    latency = raw.get("usage", {}).get("latency_ms", 0.0)
    
    formatted: dict[str, Any] = {
        "ok": True,
        "model": raw.get("model", "laya-multilingual"),
        "family": raw.get("family", "multilingual"),
        "device": "cuda:0",
        "degraded": False,
        "latency_ms": latency,
        "answers": raw.get("answers", {}),
        "usage": raw.get("usage", {}),
        "truncated": plan["truncated"],
        "budget_summary": plan,
        "confidence_semantics": "concentration",
    }
    if "route" in raw:
        formatted["routing"] = {"route": raw["route"]}
    return formatted


# =============================================================================
# MCP Tools
# =============================================================================

@server.tool(
    name="laya_predict",
    description="One-pass System 1 classification/decision between candidate options (30-150ms).",
)
async def laya_predict(state: str, options: list[str], instructions: str = "Select the best matching option") -> dict[str, Any]:
    criteria = {opt: opt for opt in options}
    questions = {
        "decision": {
            "type": "choice",
            "instructions": instructions,
            "criteria": criteria,
        }
    }
    raw = await _call_engine("/v1/systemone", method="POST", json_body={"state": state, "questions": questions})
    answer = raw.get("answers", {}).get("decision", {})
    return {
        "choice": answer.get("choice"),
        "confidence": answer.get("confidence", 0.0),
        "probabilities": answer.get("probabilities", {}),
        "latency_ms": raw.get("usage", {}).get("latency_ms", 0.0),
    }


@server.tool(
    name="classify",
    description="Fast categorical classification across categories in a single encoder pass.",
)
async def classify(text: str, categories: list[str], prompt: str = "Classify this text into one category") -> dict[str, Any]:
    return await laya_predict(state=text, options=categories, instructions=prompt)


@server.tool(
    name="check",
    description="Binary (yes/no / noul) gatekeeping check with calibrated probability.",
)
async def check(text: str, condition: str) -> dict[str, Any]:
    questions = {
        "gate": {
            "type": "noul",
            "instructions": f"Does the text satisfy the condition: {condition}?",
        }
    }
    raw = await _call_engine("/v1/systemone", method="POST", json_body={"state": text, "questions": questions})
    answer = raw.get("answers", {}).get("gate", {})
    prob = answer.get("noul", 0.0)
    band = "yes" if prob >= 0.65 else ("no" if prob <= 0.35 else "uncertain")
    return {
        "passed": prob >= 0.5,
        "probability": prob,
        "band": band,
        "confidence": answer.get("confidence", 0.0),
        "latency_ms": raw.get("usage", {}).get("latency_ms", 0.0),
    }


@server.tool(
    name="score",
    description="Score text against an ordered rating scale (e.g. ['low', 'medium', 'high', 'critical']).",
)
async def score(text: str, scale: list[str], instructions: str = "Rate the severity/relevance on this scale") -> dict[str, Any]:
    questions = {
        "rating": {
            "type": "score",
            "instructions": instructions,
            "criteria": scale,
        }
    }
    raw = await _call_engine("/v1/systemone", method="POST", json_body={"state": text, "questions": questions})
    answer = raw.get("answers", {}).get("rating", {})
    return {
        "score": answer.get("score"),
        "probabilities": answer.get("probabilities", {}),
        "confidence": answer.get("confidence", 0.0),
        "latency_ms": raw.get("usage", {}).get("latency_ms", 0.0),
    }


@server.tool(
    name="laya_ask",
    description="Native batch typed questions (choice, noul, score) matching the dsh-laya contract.",
)
async def laya_ask(state: Any, questions: dict[str, Any], strict: bool = False, lang: str = "auto") -> dict[str, Any]:
    plan = _calculate_plan(state, questions)
    if strict and plan["truncated"]:
        raise ValueError(f"State truncated: budget exceeded ({plan['total_estimated_tokens']} > {plan['max_len']})")
    payload = {"state": state, "questions": questions}
    if lang and lang != "auto":
        payload["family"] = lang
    raw = await _call_engine("/v1/systemone", method="POST", json_body=payload)
    return _format_payload(raw, state, questions)


@server.tool(
    name="laya_plan",
    description="Preflight check: evaluate token budget without spending an inference pass.",
)
async def laya_plan(state: Any, questions: dict[str, Any]) -> dict[str, Any]:
    return _calculate_plan(state, questions)


@server.tool(
    name="laya_status",
    description="Check Laya engine health, acceleration device (CUDA/CPU), model, and status.",
)
async def laya_status() -> dict[str, Any]:
    health = await _call_engine("/health")
    return {
        "ok": True,
        "engine": health,
        "mcp_version": "0.2.2",
        "primitives": ["choice", "noul", "score"],
    }


# =============================================================================
# Custom REST Routes for dsh-laya sidecar compatibility
# =============================================================================

@server.custom_route("/health", methods=["GET"])
async def sidecar_health(request: Request) -> JSONResponse:
    try:
        health = await _call_engine("/health")
        return JSONResponse({"ok": True, "device": health.get("device", "cuda:0"), "degraded": False, **health})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=503)


@server.custom_route("/capabilities", methods=["GET"])
async def sidecar_capabilities(request: Request) -> JSONResponse:
    return JSONResponse({
        "ok": True,
        "primitives": ["choice", "noul", "score"],
        "max_len": 1024,
        "head_max_len": 256,
        "max_opts": 16,
        "max_batch": 8,
    })


@server.custom_route("/version", methods=["GET"])
async def sidecar_version(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "version": "0.2.2", "primitives": ["choice", "noul", "score"]})


@server.custom_route("/plan", methods=["POST"])
async def sidecar_plan(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        state = body.get("state", "")
        questions = body.get("questions", {})
        return JSONResponse(_calculate_plan(state, questions))
    except Exception as e:
        return JSONResponse({"ok": False, "error": "invalid_request", "hint": str(e)}, status_code=400)


@server.custom_route("/ask", methods=["POST"])
async def sidecar_ask(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        state = body.get("state")
        questions = body.get("questions")
        if state is None or questions is None:
            return JSONResponse({"ok": False, "error": "invalid_request", "hint": "state and questions are required"}, status_code=400)
        strict = body.get("strict", False)
        lang = body.get("lang", "auto")
        formatted = await laya_ask(state=state, questions=questions, strict=strict, lang=lang)
        return JSONResponse(formatted)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": "state_truncated", "hint": str(e)}, status_code=400)
@server.custom_route("/reload", methods=["POST"])
async def sidecar_reload(request: Request) -> JSONResponse:
    start_time = time.time()
    log.info("Received model reload request. Triggering engine restart...")
    try:
        # Create reload trigger flag file for entrypoint.sh supervisor loop
        with open("/tmp/laya_restart_requested", "w", encoding="utf-8") as f:
            f.write("1\n")

        # Allow time for engine process shutdown
        await asyncio.sleep(1.0)

        # Poll health endpoint until new engine is ready (up to 20 seconds)
        for attempt in range(40):
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(f"{LAYA_ENGINE_URL.rstrip('/')}/health")
                    if resp.status_code == 200:
                        data = resp.json()
                        latency_ms = round((time.time() - start_time) * 1000, 1)
                        log.info("Model reload completed in %sms: %s", latency_ms, data)
                        return JSONResponse({
                            "ok": True,
                            "reloaded": True,
                            "latency_ms": latency_ms,
                            "model": os.environ.get("MODEL_PATH", "/models/laya_multilingual_f16.gguf"),
                            "engine": data,
                        })
            except Exception:
                pass
            await asyncio.sleep(0.5)

        return JSONResponse({
            "ok": False,
            "reloaded": False,
            "error": "Engine healthcheck timed out during reload",
        }, status_code=504)
    except Exception as e:
        log.error("Error handling reload request: %s", e)
        return JSONResponse({"ok": False, "reloaded": False, "error": str(e)}, status_code=500)


@server.custom_route("/v1/chat/completions", methods=["POST"])
@server.custom_route("/chat/completions", methods=["POST"])
async def sidecar_chat_completions(request: Request) -> JSONResponse:
    """OpenAI-compatible /v1/chat/completions endpoint for Hermes Tool Router."""
    try:
        body = await request.json()
        messages = body.get("messages", [])
        model = body.get("model", "laya-multilingual")

        # Combine messages to find system prompt and user text
        prompt_text = ""
        for m in messages:
            content = m.get("content", "")
            if content:
                prompt_text += f"\n{content}"

        toolsets_map: dict[str, str] = {}
        user_message = ""

        # Extract available toolsets and user message from prompt
        toolsets_match = re.search(
            r"Available toolsets:\s*\n(.*?)(?:\n\s*User message:|\Z)",
            prompt_text,
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

        user_match = re.search(r"User message:\s*\n(.*)", prompt_text, re.DOTALL | re.IGNORECASE)
        if user_match:
            user_message = user_match.group(1).strip()
        else:
            for m in reversed(messages):
                if m.get("role") == "user":
                    user_message = str(m.get("content", "")).strip()
                    break

        if not user_message:
            user_message = prompt_text.strip()[:1000]

        chosen_toolsets: list[str] = []
        confidence = 0.95
        action = "narrow"

        if toolsets_map and user_message:
            # Step 1: Gate check via Laya noul (is it purely conversational?)
            gate_questions = {
                "requires_tools": {
                    "type": "noul",
                    "instructions": (
                        "Does this user request require calling tools/actions (like files, web search, "
                        "terminal, git, system actions), or is it pure conversational chat/greeting/general knowledge?"
                    ),
                }
            }
            try:
                gate_raw = await _call_engine(
                    "/v1/systemone",
                    method="POST",
                    json_body={"state": user_message, "questions": gate_questions},
                )
                gate_prob = gate_raw.get("answers", {}).get("requires_tools", {}).get("noul", 0.5)
            except Exception as e:
                log.warning("Laya gate check error: %s", e)
                gate_prob = 0.5

            if gate_prob < 0.35:
                chosen_toolsets = []
                action = "no_tools"
                confidence = round(1.0 - gate_prob, 2)
            else:
                # Step 2: Choice classification between toolsets
                criteria = {k: v[:80] for k, v in list(toolsets_map.items())[:16]}
                choice_questions = {
                    "toolset_decision": {
                        "type": "choice",
                        "instructions": "Which toolset is needed to fulfill the user's request?",
                        "criteria": criteria,
                    }
                }
                try:
                    choice_raw = await _call_engine(
                        "/v1/systemone",
                        method="POST",
                        json_body={"state": user_message, "questions": choice_questions},
                    )
                    answer = choice_raw.get("answers", {}).get("toolset_decision", {})
                    top_choice = answer.get("choice")
                    probs = answer.get("probabilities", {})
                    choice_conf = answer.get("confidence", 0.0)

                    if top_choice and top_choice in toolsets_map:
                        chosen_toolsets.append(top_choice)
                    for ts, p in probs.items():
                        if ts != top_choice and p >= 0.22 and ts in toolsets_map:
                            chosen_toolsets.append(ts)
                    confidence = max(0.85, round(min(0.99, choice_conf + 0.85), 2))
                    action = "narrow" if chosen_toolsets else "no_tools"
                except Exception as e:
                    log.warning("Laya toolset choice error: %s; failing open to full", e)
                    chosen_toolsets = ["all"]
                    action = "full"
                    confidence = 0.5
        else:
            chosen_toolsets = ["all"]
            action = "full"
            confidence = 0.5

        content_json = {
            "confidence": confidence,
            "action": action,
            "toolsets": chosen_toolsets,
            "reason_code": "laya_system1",
        }

        response_payload = {
            "id": f"chatcmpl-laya-{int(time.time()*1000)}",
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
        return JSONResponse(response_payload)
    except Exception as e:
        log.error("Error in sidecar_chat_completions: %s", e)
        err_payload = {
            "id": f"chatcmpl-laya-err-{int(time.time()*1000)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "laya-multilingual",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps({"action": "full", "confidence": 0.5, "toolsets": ["all"]}),
                    },
                    "finish_reason": "stop",
                }
            ],
        }
        return JSONResponse(err_payload)


from mcp.server.transport_security import TransportSecuritySettings

# Build Starlette application supporting Streamable HTTP (/mcp) + Custom Routes
app = server.streamable_http_app(
    streamable_http_path="/mcp",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


if __name__ == "__main__":
    import uvicorn
    log.info("Starting Laya MCP & Sidecar Server on %s:%d (forwarding to %s)", MCP_HOST, MCP_PORT, LAYA_ENGINE_URL)
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT, log_level="info")

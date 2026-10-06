"""MCP Server and Sidecar bridge for Laya System 1 Decision Engine.

Provides:
1. Native Model Context Protocol (MCP) server over Streamable HTTP (/mcp).
   Tools: laya_predict, classify, check, score, laya_ask, laya_plan, laya_status.
2. Direct REST Sidecar endpoints for dsh-laya compatibility:
   /health, /ask, /plan, /capabilities, /version.
"""

from __future__ import annotations

import json
import logging
import os
import sys
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
    except Exception as e:
        return JSONResponse({"ok": False, "error": "inference_error", "hint": str(e)}, status_code=500)


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

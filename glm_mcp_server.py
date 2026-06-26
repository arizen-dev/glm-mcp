#!/usr/bin/env python3
"""MCP stdio server exposing two tools: run (fast, bounded) and advise (deep reasoning)."""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any

from openai import OpenAI

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "glm-mcp"
SERVER_VERSION = "0.3.0"

PRICING: dict[str, dict[str, float]] = {
    "glm-5.2": {"in": 1.40, "out": 5.60},
}

DEFAULT_SYSTEM_PROMPT = (
    "You are a precise assistant completing bounded tasks. "
    "All context is included inline in the prompt below — never reference files, "
    "external sources, or prior conversations. If context is missing, say so. "
    "Do not fabricate specific numbers, percentages, timeframes, durations, "
    "or statistics unless they appear verbatim in the input. "
    "When asked to be concrete or specific, use qualitative language "
    "rather than invented quantities. "
    "If you are uncertain about a fact, say so explicitly rather than guessing. "
    "Be concise: no preamble, no 'Certainly!', no restatement of the task. "
    "Start your response with the answer. "
    "Use structured output (tables, lists, JSON) when the task calls for it. "
    "Flag ambiguity explicitly with a one-line note rather than silently resolving it. "
    "If the task has sub-parts, address each one."
)

ADVISOR_SYSTEM_PROMPT = (
    "You are a sharp, honest senior advisor consulted when the primary agent needs "
    "a second opinion, deeper analysis, or a check on a consequential decision. "
    "All context is included inline in the prompt below — never reference files, "
    "external sources, or prior conversations. If context is missing, say so. "
    "Do not fabricate numbers, percentages, or statistics — if data is absent, say so. "
    "Structure every response in three sections: "
    "(1) CONCLUSION — your direct answer or recommendation in 1-3 sentences. "
    "(2) REASONING — the key factors, evidence, or logic behind your conclusion. "
    "(3) WATCH OUT — caveats, failure modes, alternatives, or what the primary agent "
    "may have missed. Omit this section only if there is genuinely nothing to flag. "
    "Be direct. If the question has no good answer, say so and explain why. "
    "Do not hedge unnecessarily — the primary agent needs a clear signal, not diplomatic fog."
)

EFFORT_LEVELS = frozenset({"max", "high", "minimal"})

REASONING_HEADROOM: dict[str, int] = {
    "max": 8000,
    "high": 4000,
    "minimal": 0,
}
SAFETY_CEILING = 32000
MIN_VISIBLE = 2000

LOG_DIR = os.path.expanduser("~/.glm-mcp")
LOG_FILE = os.path.join(LOG_DIR, "calls.jsonl")


def resolve_key() -> str:
    """Resolve API key: .env → env var."""
    dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
    try:
        with open(dotenv_path) as f:
            for line in f:
                line = line.strip()
                for prefix in ("GLM_API_KEY=", "NEURALWATT_API_KEY="):
                    if line.startswith(prefix):
                        return line.split("=", 1)[1].strip("\"'")
    except (OSError, FileNotFoundError):
        pass

    for var in ("GLM_API_KEY", "NEURALWATT_API_KEY"):
        val = os.environ.get(var, "")
        if val:
            return val
    return ""


def get_api_key() -> str:
    return resolve_key()


def get_base_url() -> str:
    return os.environ.get("GLM_BASE_URL", "https://api.neuralwatt.com/v1")


def get_model() -> str:
    return os.environ.get("GLM_MODEL", "glm-5.2")


def api_client() -> OpenAI:
    return OpenAI(
        api_key=get_api_key(),
        base_url=get_base_url(),
        timeout=180,
        max_retries=1,
    )


def _api_key_status() -> str:
    key = get_api_key()
    if not key:
        return "missing"
    if len(key) < 8:
        return "too-short"
    return "set"


def _log_call(entry: dict[str, Any]) -> None:
    if not os.environ.get("GLM_MCP_LOG"):
        return
    os.makedirs(LOG_DIR, exist_ok=True)
    entry["ts"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


TOOLS: list[dict[str, Any]] = [
    {
        "name": "run",
        "title": "Run",
        "description": (
            "Fast, bounded task execution with thinking disabled. "
            "Best for: classification, summarization, JSON edits, table generation, "
            "template population, pattern-copy refactors, inbox triage. "
            "Not for: decisions where being wrong has real cost — use `advise` for those. "
            "Typical latency: 2-15s."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Task prompt"},
                "system": {
                    "type": "string",
                    "description": (
                        "Optional additional system instructions. "
                        "Appended after the built-in epistemic honesty guard."
                    ),
                },
            },
            "required": ["prompt"],
        },
        "annotations": {
            "readOnlyHint": True,
            "idempotentHint": False,
        },
    },
    {
        "name": "advise",
        "title": "Advisor",
        "description": (
            "Deep reasoning with max thinking effort enabled. "
            "Use when `run` is not sufficient: multi-factor analysis, architectural "
            "tradeoffs, second opinions on consequential decisions, "
            "or anything where being wrong has real cost. "
            "Defaults to effort=max — exhaustive reasoning. "
            "Returns structured response: CONCLUSION / REASONING / WATCH OUT. "
            "Use effort=high for quicker reads, or minimal to skip reasoning entirely."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Question or problem to reason about"},
                "system": {
                    "type": "string",
                    "description": "Optional additional context or constraints for the advisor.",
                },
                "effort": {
                    "type": "string",
                    "enum": ["max", "high", "minimal"],
                    "default": "max",
"description": (
    "Reasoning depth (Neuralwatt GLM-5.2 docs). "
    "max: deepest reasoning, best for complex multi-step work (~30-90s). "
    "high: balanced depth and latency (~10-40s). "
    "minimal: skips the reasoning phase entirely (fast, ~2-5s) -- use when you want the advisor's structured format without spending reasoning tokens. "
    "Other providers may interpret these values differently; the server passes effort through unchanged."
),
                },
                "thinking_token_budget": {
                    "type": "integer",
                    "description": (
                        "Cap the reasoning phase to this many tokens. "
                        "Helps prevent runaway thinking on subjective questions. "
                        "Default varies by model; unset means no cap."
                    ),
                },
                "show_reasoning": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "If true, prepend a <reasoning>...</reasoning> block "
                        "with the model's chain-of-thought. Off by default to "
                        "keep responses compact — reasoning_content can be large."
                    ),
                },
            },
            "required": ["prompt"],
        },
        "annotations": {
            "readOnlyHint": True,
            "idempotentHint": False,
        },
    },
]


def _compute_cost(usage: Any, model: str) -> float | None:
    pricing = PRICING.get(model)
    if not pricing or usage is None:
        return None
    prompt_tokens = getattr(usage, "prompt_tokens", None) or 0
    completion_tokens = getattr(usage, "completion_tokens", None) or 0
    cost = (prompt_tokens * pricing["in"] + completion_tokens * pricing["out"]) / 1_000_000
    return cost


def _format_cost(cost: float | None) -> str:
    if cost is None:
        return ""
    if cost < 0.0001:
        return "  cost=<$0.0001"
    return f"  cost=${cost:.4f}"


def call_run(args: dict[str, Any], progress_token: Any = None) -> str:
    system_parts = [DEFAULT_SYSTEM_PROMPT]
    if args.get("system"):
        system_parts.append(args["system"])
    messages: list[dict[str, str]] = [
        {"role": "system", "content": "\n\n".join(system_parts)},
        {"role": "user", "content": args["prompt"]},
    ]

    started_at = time.time()
    model = get_model()

    stream = api_client().chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
        extra_body={"thinking": {"type": "disabled"}},
    )

    text, usage, _ = _collect_stream(stream, progress_token)
    result = _format_result(text, usage, model, started_at)
    cost = _compute_cost(usage, model)
    _log_call({
        "tool": "run", "model": model,
        "tokens_in": getattr(usage, "prompt_tokens", None) if usage else None,
        "tokens_out": getattr(usage, "completion_tokens", None) if usage else None,
        "latency_s": round(time.time() - started_at, 2),
        "cost_usd": round(cost, 6) if cost else None,
    })
    return result


def call_advisor(args: dict[str, Any], progress_token: Any = None) -> str:
    system_parts = [ADVISOR_SYSTEM_PROMPT]
    if args.get("system"):
        system_parts.append(args["system"])
    messages: list[dict[str, str]] = [
        {"role": "system", "content": "\n\n".join(system_parts)},
        {"role": "user", "content": args["prompt"]},
    ]

    caller_effort = args.get("effort", "max")
    if caller_effort not in EFFORT_LEVELS:
        raise ValueError(
            f"Invalid effort '{caller_effort}'. "
            f"Allowed: {sorted(EFFORT_LEVELS)}"
        )
    effort = caller_effort

    visible_budget = int(args.get("output_budget") or 4000)
    api_max_tokens = max(MIN_VISIBLE, visible_budget) + REASONING_HEADROOM.get(effort, 4000)
    api_max_tokens = min(api_max_tokens, SAFETY_CEILING)

    started_at = time.time()
    model = get_model()

    extra_body: dict[str, Any] = {
        "thinking": {"type": "enabled"},
        "reasoning_effort": effort,
    }
    if args.get("thinking_token_budget") is not None:
        extra_body["thinking_token_budget"] = args["thinking_token_budget"]

    if progress_token is not None:
        _emit_progress(progress_token, 0, "request started")

    stream = api_client().chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=api_max_tokens,
        stream=True,
        stream_options={"include_usage": True},
        extra_body=extra_body,
    )

    text, usage, reasoning_text = _collect_stream(stream, progress_token)

    if not text.strip() and reasoning_text:
        text = (
            f"[Advisor returned no visible text. The model spent the "
            f"completion budget on hidden reasoning. "
            f"effort={effort}, api_max_tokens={api_max_tokens}. "
            f"Retry with a larger output_budget or lower effort.]"
        )

    result = _format_result(text, usage, f"{model}·{effort}", started_at)
    cost = _compute_cost(usage, model)
    _log_call({
        "tool": "advise", "model": model, "effort": effort,
        "tokens_in": getattr(usage, "prompt_tokens", None) if usage else None,
        "tokens_out": getattr(usage, "completion_tokens", None) if usage else None,
        "latency_s": round(time.time() - started_at, 2),
        "cost_usd": round(cost, 6) if cost else None,
    })
    if reasoning_text and args.get("show_reasoning"):
        result = f"<reasoning>\n{reasoning_text}\n</reasoning>\n\n{result}"
    return result


def _collect_stream(stream: Any, progress_token: Any) -> tuple[str, Any, str]:
    text = ""
    reasoning = ""
    usage = None
    chunk_count = 0
    last_emit_time = time.monotonic()

    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta:
            content = getattr(delta, "content", None)
            if content:
                text += content
                chunk_count += 1
            rc = getattr(delta, "reasoning_content", None)
            if rc:
                reasoning += rc
                chunk_count += 1
        if getattr(chunk, "usage", None):
            usage = chunk.usage

        if progress_token is not None:
            now = time.monotonic()
            if (chunk_count and chunk_count % 20 == 0) or (now - last_emit_time) > 10:
                _emit_progress(progress_token, chunk_count, f"{len(text)} chars received")
                last_emit_time = now

    return text, usage, reasoning


def _emit_progress(progress_token: Any, progress: int, message: str) -> None:
    if progress_token is None:
        return
    sys.stdout.write(json.dumps({
        "jsonrpc": "2.0",
        "method": "notifications/progress",
        "params": {
            "progressToken": progress_token,
            "progress": progress,
            "message": message,
        },
    }) + "\n")
    sys.stdout.flush()


def _format_result(text: str, usage: Any, model_label: str, started_at: float) -> str:
    elapsed = round(time.time() - started_at, 2)
    model = model_label.split("·")[0]
    cost = _compute_cost(usage, model)
    metadata = [f"model={model_label}", f"latency={elapsed}s"]
    if usage:
        metadata.append(f"tokens={usage.prompt_tokens}+{usage.completion_tokens}")
    cost_str = _format_cost(cost)
    if cost_str:
        metadata.append(cost_str)
    return f"{text}\n\n---\n_glm-mcp · {'  '.join(metadata)}_"


def error_text(exc: Exception) -> str:
    raw = str(exc)
    lowered = raw.lower()
    if "402" in raw or "insufficient" in lowered:
        return f"API: insufficient balance. Add credits at portal.neuralwatt.com. ({raw})"
    if "401" in raw or "authentication" in lowered:
        return f"API: invalid key. Check GLM_API_KEY or NEURALWATT_API_KEY. ({raw})"
    if "429" in raw or "rate limit" in lowered:
        return f"API: rate limited. Wait and retry. ({raw})"
    if "timeout" in lowered:
        return f"API: request timed out. Try a shorter prompt. ({raw})"
    return raw


def handle(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")

    if method == "initialize":
        key_status = _api_key_status()
        if key_status != "set":
            print(
                "glm-mcp: API key not set. "
                "Set GLM_API_KEY or NEURALWATT_API_KEY in your MCP config env.",
                file=sys.stderr,
                flush=True,
            )
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                    "apiKey": key_status,
                },
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": TOOLS},
        }

    if method == "tools/call":
        params = request.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})
        progress_token = params.get("_meta", {}).get("progressToken")

        if not (args.get("prompt") or "").strip():
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": "prompt is required"},
            }

        try:
            if tool_name == "advise":
                text = call_advisor(args, progress_token)
            else:
                text = call_run(args, progress_token)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": text}],
                    "isError": False,
                },
            }
        except ValueError as e:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": str(e)}],
                    "isError": True,
                },
            }
        except Exception as exc:
            raw = error_text(exc)
            if raw != str(exc):
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": raw}],
                        "isError": True,
                    },
                }
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": raw},
            }

    if method in {"notifications/initialized", "notifications/cancelled"}:
        return None

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


def main() -> None:
    # Die when parent (opencode session) dies — prevents orphan accumulation
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        libc.prctl(1, signal.SIGTERM, 0, 0, 0)
    except Exception:
        pass

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    try:
        signal.signal(signal.SIGPIPE, lambda *_: sys.exit(0))
    except (AttributeError, ValueError):
        pass

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            response = handle(json.loads(line))
            if response is not None:
                print(json.dumps(response), flush=True)
        except Exception as exc:
            print(json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(exc)},
            }), flush=True)


if __name__ == "__main__":
    main()

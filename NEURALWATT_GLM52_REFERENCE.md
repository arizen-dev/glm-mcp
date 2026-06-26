# Neuralwatt GLM-5.2 Reference

Single source of truth for GLM-5.2 on Neuralwatt as served by `glm_mcp_server.py`.
Captured 2026-06-26 from Neuralwatt docs.

## Model variants

| Model | Context | Reasoning | Use for |
|-------|---------|-----------|---------|
| `glm-5.2` | 1024K | yes | `advise` (deep reasoning) |
| `glm-5.2-fast` | 1024K | no | `run` (thinking disabled) -- pending pricing + A/B test |
| `glm-5.2-short` | 195K | yes | only if context < 195K AND pricing discounts justify |
| `glm-5.2-short-fast` | 195K | no | skip unless pricing reveals a big discount |

## Pricing (USD per 1M tokens)

| Model | Input | Output |
|-------|-------|--------|
| `glm-5.2` (server default) | $1.40 | $5.60 |
| `glm-5.1` (reference) | $0.35 | $1.38 |
| `glm-5.2-fast` | TODO | confirm before flipping run default |

**Cache pricing:** cache reads = 25% of input rate.

## Effort levels

GLM-5.2 exposes **3 distinct behaviors**. Server uses `{max, high, minimal}`.

| Server value | Behavior | Native? |
|-------------|----------|---------|
| `max` | deepest reasoning (~30-90s) | native (default) |
| `high` | balanced depth/latency (~10-40s) | native |
| `minimal` | skips reasoning entirely (~2-5s) | off-tier |

Aliases mapped by Neuralwatt: xhigh->max, medium/low->high, none->thinking-off.

## Request fields used

| Field | Where | Values |
|-------|-------|--------|
| `thinking.type` | `extra_body` | enabled (advise) / disabled (run) |
| `reasoning_effort` | `extra_body` | max / high / minimal (advise) |
| `thinking_token_budget` | top-level | optional int cap (advise) |

## Capabilities

`capabilities.reasoning_effort: true` for GLM-5.2 (verify via GET /v1/models).

## Integrations (per Neuralwatt)

LLM Plugin, Claude Code, OpenCode

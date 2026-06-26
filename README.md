# glm-mcp

A tiny MCP stdio server with two tools: `run` for fast bounded tasks, `advise` for deep reasoning.

Provider-agnostic — swap `GLM_BASE_URL` to use Neuralwatt, OpenRouter, z.ai, or local vLLM.

## Tools

```
run(prompt, system?)           — fast, no thinking, 2-15s
advise(prompt, effort?, system?, thinking_token_budget?, show_reasoning?) — deep reasoning, 2-90s
```

| Tool | Mode | Best for |
|------|------|----------|
| `run` | Non-thinking | Classification, summarization, JSON edits, table generation, template population |
| `advise` | Thinking (effort: max/high/minimal) | Multi-factor analysis, tradeoffs, second opinions, architecture decisions |

## Quickstart

```bash
export GLM_API_KEY="your-key-here"

# Run directly
python3 /path/to/glm_mcp_server.py
```

## Configure

### Claude Code / OpenCode

```json
{
  "mcpServers": {
    "glm": {
      "command": "python3",
      "args": ["/path/to/glm_mcp_server.py"],
      "env": { "GLM_API_KEY": "${GLM_API_KEY}" },
      "timeout": 240000
    }
  }
}
```

## Providers

| Provider | `GLM_BASE_URL` | Notes |
|----------|-----------------|-------|
| Neuralwatt (default) | `https://api.neuralwatt.com/v1` | Energy-billed GPU |
| OpenRouter | `https://openrouter.ai/api/v1` | Requires OpenRouter key |
| z.ai (Zhipu) | `https://open.bigmodel.cn/api/paas/v4` | Official GLM provider |
| Local vLLM | `http://localhost:8000/v1` | Self-hosted weights |

## Cost

Per-call cost depends on token count and model (`GLM_MODEL`). Default GLM-5.2 pricing via Neuralwatt:

| Task | Input | Output | Typical |
|------|-------|--------|---------|
| Small (~1K in + ~0.5K out) | $1.40/M | $5.60/M | ~$0.004 |
| Medium (~4K in + ~2K out) | $1.40/M | $5.60/M | ~$0.017 |

Each response includes a footer with model, latency, tokens, and cost.

## Env vars

| Variable | Default | Description |
|----------|---------|-------------|
| `GLM_API_KEY` | — | API key (also accepts `NEURALWATT_API_KEY`) |
| `GLM_BASE_URL` | `https://api.neuralwatt.com/v1` | API base URL |
| `GLM_MODEL` | `glm-5.2` | Model name |
| `GLM_MCP_LOG` | (unset) | Set to `1` to log call metadata to `~/.glm-mcp/calls.jsonl` |

## Security

- Text-only output. No tool calls, no file access, no repo access.
- Output lands in the primary model's context — review before using.
- Do not commit API keys. Use env injection.

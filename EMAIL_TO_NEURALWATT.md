# Email to Neuralwatt — advisor-mcp Introduction

**Status:** Draft (not sent)  
**Date prepared:** 2026-06-24  
**Repo:** https://github.com/arizen-dev/advisor-mcp

---

**To:** Neuralwatt team (use their contact/support/partnerships email)

**Subject:** advisor-mcp — open-source MCP server defaulting to Neuralwatt

---

Hi Neuralwatt team,

I'm Igor, a developer building AI tooling at Arizen. I just published a small open-source project that defaults to your API, and I thought your users might find it useful.

It's called **glm-mcp** — a tiny MCP stdio server exposing two tools: `run` for fast bounded tasks (classification, summarization, JSON edits, template work) and `advise` for deep reasoning with configurable effort. It's a single Python file with one dependency (`openai`), and it works with any MCP client — Claude Code, OpenCode, and the rest.

The reason I'm writing: Neuralwatt is the documented default. Out of the box it points at `api.neuralwatt.com/v1` and authenticates with `GLM_API_KEY` / `NEURALWATT_API_KEY`, so anyone running GLM-5.2 through your API can drop it into their MCP config and go. The server is provider-agnostic (swap `GLM_BASE_URL`), but I set Neuralwatt as the default because it's what I use day to day and I'm happy with it.

Repo: https://github.com/arizen-dev/glm-mcp (MIT)

I noticed your docs already have an Integrations page covering the LLM Plugin, Claude Code, and OpenCode. If advisor-mcp looks like a fit, I'd be glad if you considered listing it there. I'm also open to a referral or partnership arrangement if that's something you do — but genuinely no pressure either way. Independent of all that, I'd value any feedback you have on the implementation.

Thanks for building a service I'm happy to default to.

Igor
Arizen

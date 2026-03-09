# AI Agentic Development - Useful Links & Best Practices

A curated reference for developers working with AI coding agents across multiple
agentic IDEs and CLIs. It includes shared workflow conventions plus
tool-specific references where they matter.

---

## Repo Baseline

This repository is an AI-agent system skeleton with a default internal baseline:

- `docs/adr/0002-multi-agent-pattern.md` defines the orchestrator + specialist workflow.
- `docs/adr/0003-agent-runtime-contract-and-retry-policy.md` defines the runtime contract.
- `docs/adr/0004-agent-state-model-short-term-vs-long-term-memory.md` defines the state model.
- `docs/specs/technical/agent-runtime/` contains the active runtime specifications.

Implementation stack choices still need project-specific ADRs, but the
agent-runtime baseline is part of the template by default.

## Visible Roles in Chat

Many coding-agent interfaces show only one assistant stream even when a
multi-agent workflow exists underneath. In this repository, the visible
convention is to label outputs with the active role:

- `Role: orchestrator`
- `Role: frontend-agent`
- `Role: backend-agent`
- `Role: docs-agent`
- `Role: platform-agent`
- `Role: qa-agent`

Use the same role labels in durable artifacts such as handoff files and QA
reports so the origin of a decision or summary remains clear after the chat ends.

---

## Tool-Specific References

### Claude Code

| Resource | Description |
|---|---|
| [Claude Code Docs](https://code.claude.com/docs) | Official documentation hub |
| [Best Practices (official)](https://code.claude.com/docs/en/best-practices) | Core recommended workflows |
| [CLAUDE.md reference](https://code.claude.com/docs/en/core-concepts/claude-md) | How to write project instructions |
| [Hooks](https://code.claude.com/docs/en/advanced/hooks) | Shell commands triggered by agent events |
| [MCP integration](https://code.claude.com/docs/en/advanced/mcp) | Connect external tools via Model Context Protocol |
| [Subagents / Tasks](https://code.claude.com/docs/en/advanced/subagents) | Spawning specialist agents from an orchestrator |
| [Permissions & Sandbox](https://code.claude.com/docs/en/security/permissions) | Allowlisting commands, OS-level isolation |
| [Awesome Claude Code (community)](https://github.com/hesreallyhim/awesome-claude-code) | Skills, hooks, slash-commands, plugins |

### Key concepts

- **CLAUDE.md** - loaded at the start of every session; define commands, style, workflow rules, and agent ownership maps here.
- **Skills** (`.claude/skills/`) - reusable, invocable prompt templates stored in the repo.
- **Hooks** - shell commands that fire on agent events (pre-tool, post-tool, etc.) to enforce guardrails or trigger side-effects.
- **MCP servers** - give the agent typed, sandboxed access to external tools (databases, APIs, filesystems) without prompt injection risk.

---

### OpenAI Codex

| Resource | Description |
|---|---|
| [Codex overview](https://developers.openai.com/codex/) | Official landing page |
| [AGENTS.md guide](https://developers.openai.com/codex/guides/agents-md/) | How Codex reads project instructions |
| [AGENTS.md spec (GitHub)](https://github.com/openai/codex/blob/main/docs/agents_md.md) | Full AGENTS.md format specification |
| [Use Codex with the Agents SDK](https://developers.openai.com/codex/guides/agents-sdk/) | Integrating Codex into agent pipelines |
| [Agent Skills](https://developers.openai.com/codex/skills/) | Codex skill definitions |
| [agents.md community site](https://agents.md/) | Ecosystem-wide AGENTS.md reference |

### Key concepts

- **AGENTS.md** - open format consumed by Codex, Claude Code, Amp, Cursor, and others. Layer global overrides (`AGENTS.override.md`) on top of repo-level files.
- **Test integration** - Codex will run test commands listed in AGENTS.md; document them explicitly.
- **AAIF (Agentic AI Foundation)** - cross-vendor standards effort; AGENTS.md is part of this convergence alongside MCP and Skills.

---

## Shared Ecosystem Standards

### Model Context Protocol (MCP)

Anthropic open standard (Nov 2024), now adopted by OpenAI, Google, and Microsoft.
Connects agents to tools and data sources through a typed, sandboxed protocol.

| Resource | Description |
|---|---|
| [modelcontextprotocol.io](https://modelcontextprotocol.io/specification/2025-11-25) | Official spec |
| [Wikipedia - MCP](https://en.wikipedia.org/wiki/Model_Context_Protocol) | Neutral overview |
| [Code execution with MCP (Anthropic Engineering)](https://www.anthropic.com/engineering/code-execution-with-mcp) | Deep dive on context efficiency |
| [mcp-agent (lastmile-ai)](https://github.com/lastmile-ai/mcp-agent) | OSS framework for MCP-based agents |

### Agent-to-Agent (A2A)

Google's April 2025 protocol for inter-agent messaging (complements MCP, which
handles agent-to-tool communication).

---

## Multi-Agent Architecture - Best Practices

1. **Declare ownership explicitly** - use `docs/agents/ownership.yml` (or equivalent) so each agent knows which paths it may write.
2. **Single orchestrator for conflicts** - specialist agents own their area; only the orchestrator resolves cross-area decisions.
3. **Instructions in-repo, not in prompts** - AGENTS.md / CLAUDE.md keep instructions version-controlled and auditable.
4. **Context efficiency matters** - model accuracy drops with large context windows; use MCP to load tools on demand rather than front-loading everything.
5. **Session continuity** - write handoff files between sessions (`docs/sessions/handoff-template.md`) so agents can resume cleanly.
6. **Sandbox risky operations** - use permission allowlists and OS-level sandboxing before running destructive commands.
7. **Test commands in AGENTS.md** - every agent must know how to run and verify tests for its area.

---

## Further Reading

- [OpenAI for Developers 2025](https://developers.openai.com/blog/openai-for-developers-2025/)
- [MCP Enterprise Adoption Guide](https://guptadeepak.com/the-complete-guide-to-model-context-protocol-mcp-enterprise-adoption-market-trends-and-implementation-strategies/)
- [Introducing Codex (OpenAI)](https://openai.com/index/introducing-codex/)

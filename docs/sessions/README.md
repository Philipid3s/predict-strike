# Session Handoffs

This folder stores session handoff files written by the orchestrator at the end of
a long working session or before starting a new one.

## Purpose

Each AI agent operates within a single context window. As a session grows long,
earlier context degrades in quality. Handoff files solve this by capturing the
current state of work in a durable, file-based format — so a new session can start
fresh with full continuity.

## Naming Convention

```
handoff-YYYY-MM-DD[-N].md
```

Use the optional `-N` suffix when multiple handoffs occur on the same day.

Examples:
```
handoff-2026-02-27.md
handoff-2026-02-27-2.md
```

## When to Write a Handoff

- Before ending a session where work is in progress
- When a session context is getting long and quality may drop
- After completing a major milestone, before starting the next one
- When switching from one agent to another on the same topic

## Plain-Language Triggers

Informal user phrases should also trigger handoff behavior.

Examples:
- `end of session`
- `handoff session`
- `that's all for today`
- `we stop here`
- `let's continue later`

When one of these appears, the orchestrator should treat it as a request to
write the session handoff before closing out.

## Who Writes It

The **orchestrator** is responsible for writing handoff files.
Specialist agents may request a handoff but do not write them directly.

## Template

See [`handoff-template.md`](handoff-template.md).

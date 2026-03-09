# ADR 0006: Verification Command Contract

## Status
Accepted

## Date
2026-03-06

## Context
Agentic development works best when every project exposes a small, predictable
set of verification commands. This skeleton cannot choose language-specific
tools yet, but it should define the contract that future projects must fill in.

## Decision
Each concrete project built from this skeleton must define and document standard
verification commands for the services it introduces.

At minimum, a project should define commands for:

- local development startup
- tests
- linting or static analysis
- production build or packaging

These commands must be documented in repository instructions and kept current as
the stack evolves.

The skeleton does not prescribe any particular tool. It only requires that the
commands exist, are runnable, and are unambiguous for both humans and agents.

## Consequences
- Agents can verify work consistently once a stack is chosen.
- Teams retain freedom to select the tooling that fits their project.
- Drift between implementation and documented verification steps becomes easier
  to detect in review.

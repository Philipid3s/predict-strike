# Specifications

This folder stores the functional and technical specifications that describe the
current Predict Strike system.

## Current Structure

```text
specs/
|-- technical/               # Active task/tool/retry/state specs and project technical docs
|-- README.md
|-- initial-draft-project-spec.md
`-- pizza-index-google-maps-activity.md
```

## What Lives Here

- `docs/specs/initial-draft-project-spec.md`
  - Working product scope, implementation overview, MVP boundaries, and
    milestone plan.
- `docs/specs/pizza-index-google-maps-activity.md`
  - Design reference for the Google Maps restaurant-activity slice that feeds
    `pizza_index`.
- `docs/specs/technical/agent-runtime/`
  - Canonical runtime contract, state model, and validation fixtures used by the
    agent workflow.

## Agent Runtime Baseline

`agent-runtime` means the execution environment that runs an AI agent. In this
repository, those docs define the default task envelope, tool contract, retry
policy, and temporary state model used while the agent is working.

These files remain normative for Predict Strike unless superseded by ADRs or a
later technical spec.

Related ADRs:

- `docs/adr/0003-agent-runtime-contract-and-retry-policy.md`
- `docs/adr/0004-agent-state-model-short-term-vs-long-term-memory.md`

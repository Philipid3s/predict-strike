# Specifications

This folder stores functional and technical specifications for Predict Strike.
The repository still inherits the AI-agent runtime baseline from the original
skeleton, but project-specific specs should now be documented here as the
implementation becomes concrete.

## What `incubator` Means

`incubator/` is a holding area for draft ideas that may be useful later but are
not part of the active skeleton contract.

Use `incubator/` for:

- optional reference material
- experimental specs
- patterns that a future project may adopt, revise, or discard

Do not treat files in `incubator/` as required defaults for every project built
from this repository.

By contrast, `technical/` contains the active agent-runtime baseline plus any
Predict Strike technical specs adopted by the implementation.

## What `agent-runtime` Means

`agent-runtime` means the execution environment that runs an AI agent.

It is the surrounding system that:

- receives tasks
- provides context
- manages tool calls
- applies limits, retries, and safety rules
- tracks temporary state while the agent is working

In this repository, `agent-runtime` documents define the default runtime
architecture for running agents. Projects built from this skeleton are expected
to either follow these specs or explicitly supersede them with ADRs.

## Current Structure

```text
specs/
|-- incubator/               # Optional future drafts and experiments
`-- technical/
    |-- agent-runtime/       # Active task/tool/retry/state specs
    `-- <project-specific specs go here>
```

Current project kickoff spec:

- `docs/specs/initial-draft-project-spec.md`
  - Working product scope, source inventory, MVP boundaries, and milestone plan
- `docs/specs/pizza-index-google-maps-activity.md`
  - Planned Google Maps behavioral-signal slice for target activity collection,
    provider fallback rules, and `pizza_index` derivation

## Agent Runtime Baseline

- `technical/agent-runtime/task.schema.json`
  - Canonical task submission envelope.
- `technical/agent-runtime/tool.contract.json`
  - Canonical tool call request/response envelope.
- `technical/agent-runtime/runtime-errors.md`
  - Error classification and retry semantics.
- `technical/agent-runtime/state-model.md`
  - Memory model and promotion/retrieval rules.
- `technical/agent-runtime/examples/`
  - Fixture payloads and expected outcomes for schema validation.

Status:
- These files remain normative for Predict Strike unless superseded by later
  ADRs.

Related ADRs:
- `docs/adr/0003-agent-runtime-contract-and-retry-policy.md`
- `docs/adr/0004-agent-state-model-short-term-vs-long-term-memory.md`

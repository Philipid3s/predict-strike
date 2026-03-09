# ADR 0005: Implementation Stack Selection Within the Agent Runtime Baseline

## Status
Accepted

## Date
2026-03-06

## Context
This repository is an AI-agent system skeleton, not a generic full-stack
template. The agent runtime contract and memory model are part of the baseline
architecture. However, concrete implementation choices for frontend, backend,
worker runtime, deployment tooling, and supporting services may still vary.

Without an explicit stack-selection gate, contributors may introduce those
implementation choices incrementally and without documentation, creating drift
between the reference architecture and the actual system.

## Decision
The skeleton adopts the agent-runtime baseline defined in ADR 0003 and ADR 0004,
while requiring explicit ADRs for implementation-stack choices.

Before implementation-stack selection:

- service directories may remain minimal
- commands may remain generic placeholders
- runtime contracts and state-model specs remain authoritative

When a real project starts, it must add ADRs for the chosen stack where
applicable, such as:

- frontend framework and build tool
- backend framework and runtime
- agent worker or executor runtime
- primary data store
- deployment and hosting model
- CI/CD toolchain

## Consequences
- The repo keeps a stable AI-agent system core while remaining flexible on
  implementation technology.
- Framework-specific decisions become explicit and reviewable.
- Teams can extend the skeleton without weakening the shared runtime baseline.

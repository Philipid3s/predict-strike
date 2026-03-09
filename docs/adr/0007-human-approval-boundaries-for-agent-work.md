# ADR 0007: Human Approval Boundaries for Agent Work

## Status
Accepted

## Date
2026-03-06

## Context
This repository is designed for AI-agentic development, but not every change
should be executed autonomously. An AI-agent system skeleton should define
approval boundaries that remain useful regardless of the eventual stack.

## Decision
Projects derived from this skeleton must define clear human-approval checkpoints
for high-impact changes.

At minimum, human review is required for:

- introducing or replacing major dependencies
- schema or data model changes
- infrastructure or deployment changes
- security, privacy, or permission model changes
- destructive repository operations

Projects may add more approval gates, but should not reduce these baseline
categories without an explicit ADR.

## Consequences
- Agent autonomy is bounded by reviewable risk categories.
- The rule remains valid across different languages, frameworks, and hosting
  models.
- Future projects must translate these categories into concrete workflow rules.

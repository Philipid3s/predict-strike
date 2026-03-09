# QA Reports

This folder stores compliance reports produced by the `qa-agent`.

## Naming Convention

```
qa-YYYY-MM-DD[-N].md
```

Use the optional `-N` suffix when multiple reports are produced on the same day.

## Purpose

Each report records whether the implementation at a given point in time is consistent
with the functional and technical specifications. Reports are never deleted - they
form an audit trail of QA checks over the project lifecycle.

## Agent Identity

Every report should make the authoring role explicit.

- QA reports must include `Prepared By: qa-agent`
- If another report type is added later, it should include the responsible agent
  role in the same format

## Ownership

Reports are written exclusively by `qa-agent`. No other agent modifies this folder.

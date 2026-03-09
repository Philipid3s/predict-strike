# Agent Runtime Examples

This folder provides example payloads for runtime implementers and CI validation.

## Files

- `task.valid.json`: valid task envelope example.
- `task.invalid.missing-goal.json`: invalid task envelope (missing `input.goal`).
- `tool.valid.success.json`: valid tool call with `status=success`.
- `tool.valid.error.json`: valid tool call with `status=error`.
- `tool.invalid.success-missing-result.json`: invalid tool call (`status=success` without `result`).
- `manifest.json`: expected validation outcomes used by CI.

## Usage

Validate each payload against its schema:
- Task payloads -> `../task.schema.json`
- Tool payloads -> `../tool.contract.json`

# NOTAM Samples

This folder contains reference material for the FAA NMS-API integration.
Use it together with `docs/guides/notam-faa-integration.md` and
`backend/.env.example`.

## Files

- `nms-api-1.0.17.yaml`
  - OpenAPI contract for the NMS-API
  - Best source for endpoint names, parameters, response shapes, and auth rules
- `nms-api_curl_examples.txt`
  - Manual verification commands for auth, ping, checklist, NOTAM, and initial-load flows
- `nms-api_checklist_example.json`
  - Compact checklist response sample for parser and filter tests
- `nms_api_initial_load_example.json`
  - JSON example showing the initial-load response shape and content URL
- `nms-api_sample_initial_load.xml`
  - Example compressed-load payload in AIXM/XML form
- `NMS-API-Pre-Prod-soapui-project_sample.xml`
  - SoapUI project export with request definitions and OAuth profile metadata
  - Treat this file as sensitive reference data because it contains embedded
    credential material

## How To Use These Samples

- Use the OpenAPI document to confirm supported headers, required query
  parameters, and response envelopes before coding.
- Use the curl examples to validate the auth flow and endpoint behavior against
  staging or production.
- Use the JSON and XML files as fixtures when writing parser tests or building
  extraction logic for checklist and initial-load responses.
- Do not wire the sample payloads directly into the app. They are meant to
  document shape and behavior, not act as production inputs.

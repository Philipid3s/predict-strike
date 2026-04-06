# FAA NOTAM Integration

This guide documents the FAA NMS-API onboarding path for the Predict Strike
NOTAM slice. It is based on the sample package under
`docs/ref/NOTAM SAMPLES/` and the staging environment flow provided by the API
administrator.

## What The App Uses

The NOTAM integration is not a browser workflow. It is a machine-to-machine
flow that uses OAuth 2.0 client credentials, then calls protected NMS-API
endpoints with a bearer token.

The repo should be configured with these environment variables:

- `NOTAM_API_BASE_URL`
- `NOTAM_AUTH_URL`
- `NOTAM_CLIENT_ID`
- `NOTAM_CLIENT_SECRET`
- `NOTAM_ENV`
- `NOTAM_RESPONSE_FORMAT`
- `NOTAM_DETAIL_FETCH_ENABLED`

The backend also supports environment-scoped overrides for this slice:

- `NOTAM_TEST_*`
- `NOTAM_PRODUCTION_*`

The unscoped `NOTAM_*` variables remain for legacy and local compatibility.

Recommended staging values:

- `NOTAM_AUTH_URL=https://api-staging.cgifederal-aim.com/v1/auth/token`
- `NOTAM_API_BASE_URL=https://api-staging.cgifederal-aim.com/nmsapi/v1`
- `NOTAM_ENV=test`

The sample materials also indicate a required response-format header for
`/v1/notams` requests:

- `nmsResponseFormat: AIXM`

In this repository, `NOTAM_RESPONSE_FORMAT` defaults to `GEOJSON`. Change it
only if the target environment requires a different format.

## Auth Flow

The expected sequence is:

1. `POST` to the auth URL using `grant_type=client_credentials`
1. Send the client ID and secret with HTTP basic auth
1. Read `access_token` from the JSON response
1. Use `Authorization: Bearer <token>` on subsequent NMS-API requests

The staging token response shown in the sample materials reports
`expires_in=1799`, which is about 30 minutes. That means the backend should
renew the token regularly instead of treating it as long-lived.

## Endpoints Used

The sample files document these usable NMS-API endpoints:

- `GET /v1/ping`
- `GET /v1/notams/checklist`
- `GET /v1/notams`
- `GET /v1/notams/il`
- `GET /v1/notams/il/{classification}`
- `GET /v1/content/{token}`
- `GET /v1/locationseries`

For this repo, the practical collection path is:

- `GET /v1/notams/checklist` for checklist discovery and filterable NOTAM
  metadata
- `GET /v1/notams` for targeted NOTAM pulls when you need the formatted body
- `GET /v1/notams/il` or `GET /v1/notams/il/{classification}` for bootstrap or
  full-load retrieval

The operator-facing NOTAM source page should read from the normalized backend
detail endpoint:

- `GET /api/v1/signals/sources/notam-feed/detail`

That route is intended to expose an analyst summary of the latest stored NOTAM
observation, not the raw upstream FAA payload.
Expected page sections include:

- total NOTAM count and alert/restricted count
- classification, accountability, and location breakdowns
- latest update and effective-window timestamps
- representative notices with number, location, classification, and alert flag
- provenance and fallback reason if the collector degraded

The `GET /v1/notams` and initial-load endpoints require the bearer token and the
`nmsResponseFormat` header. The initial-load routes may return a relative
content path that must then be fetched via `GET /v1/content/{token}`.

## Sample Files

The files in `docs/ref/NOTAM SAMPLES/` are directly useful for implementation
and testing:

- `nms-api-1.0.17.yaml` is the primary contract reference. It documents the
  auth flow, query parameters, headers, response schemas, and content URLs.
- `nms-api_curl_examples.txt` is the easiest manual verification reference. It
  shows the auth call and the endpoint shapes used by the staging environment.
- `nms-api_checklist_example.json` is a compact fixture for checklist parsing
  and filter logic.
- `nms_api_initial_load_example.json` and
  `nms-api_sample_initial_load.xml` demonstrate the initial-load/content-path
  flow and the compressed AIXM payload shape.
- `NMS-API-Pre-Prod-soapui-project_sample.xml` shows the SOAPUI request
  structure, but it also contains embedded credential material and should be
  treated as sensitive reference data.

## Local Verification

With the credentials in local environment variables, the quickest manual check
is:

```bash
curl -X POST \
  --location "https://api-staging.cgifederal-aim.com/v1/auth/token" \
  -d grant_type=client_credentials \
  -u <CLIENT_ID>:<CLIENT_SECRET>
```

Use the returned token in a ping request:

```bash
curl --location 'https://api-staging.cgifederal-aim.com/nmsapi/v1/ping' \
  --header 'Authorization: Bearer <BEARER_TOKEN>'
```

Then validate a NOTAM endpoint with the required response-format header:

```bash
curl -X GET 'https://api-staging.cgifederal-aim.com/nmsapi/v1/notams/checklist' \
  --header 'Authorization: Bearer <BEARER_TOKEN>'
```

For initial-load testing, use `curl -L` against `/v1/notams/il` or
`/v1/notams/il/DOMESTIC` so redirect handling follows the temporary content
URL.

## Operational Notes

- Treat the bearer token as short-lived and renew it on a schedule shorter than
  the reported 30-minute lifetime.
- Do not paste client credentials or bearer tokens into the repo, docs, or
  chat logs.
- The sample XML and YAML files are reference material, not runtime inputs.

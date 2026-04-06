from __future__ import annotations

import gzip
import io
import json
import unittest
from pathlib import Path
import sys
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from src.collectors.notam import (
    BOOTSTRAP_NOTAM_RESPONSE,
    NotamCollector,
    _TOKEN_CACHE,
    compute_notam_spike,
    parse_notices,
)


class _FakeResponse:
    def __init__(self, payload: dict[str, object] | bytes) -> None:
        if isinstance(payload, bytes):
            self._buffer = io.BytesIO(payload)
        else:
            self._buffer = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def read(self) -> bytes:
        return self._buffer.read()

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class NotamCollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        _TOKEN_CACHE.clear()

    def test_parse_notices_extracts_bootstrap_payload(self) -> None:
        notices = parse_notices(BOOTSTRAP_NOTAM_RESPONSE)

        self.assertEqual(len(notices), 3)
        self.assertEqual(notices[0].notice_id, "NOTAM-A1")

    def test_parse_notices_extracts_geojson_detail_payload(self) -> None:
        payload = {
            "status": "Success",
            "data": {
                "geojson": [
                    {
                        "type": "Feature",
                        "properties": {
                            "coreNOTAMData": {
                                "notam": {
                                    "id": "NMS_ID_1234567812345678",
                                    "classification": "DOM",
                                    "location": "KCLT",
                                    "number": "01/123",
                                    "text": "27 RWY END ID LGT U/S",
                                    "effectiveStart": "2026-04-05T10:00:00Z",
                                    "effectiveEnd": "2026-04-05T11:30:00Z",
                                }
                            }
                        },
                    }
                ]
            },
        }

        notices = parse_notices(payload)

        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].notice_id, "NMS_ID_1234567812345678")
        self.assertIn("RWY END", notices[0].text)

    def test_parse_notices_extracts_aixm_detail_payload(self) -> None:
        payload = {
            "status": "Success",
            "data": {
                "aixm": [
                    """
                    <AIXMBasicMessage xmlns:event="urn:us:gov:faa:atm:nems:event"
                                      xmlns:fnse="urn:us:gov:faa:atm:fnse"
                                      xmlns:gml="http://www.opengis.net/gml/3.2">
                      <hasMember>
                        <event:Event>
                          <event:textNOTAM>
                            <event:NOTAM gml:id="NOTAM_1_1757609538792382">
                              <event:number>430</event:number>
                              <event:year>2025</event:year>
                              <event:location>8WC</event:location>
                              <event:effectiveStart>202508210234</event:effectiveStart>
                              <event:effectiveEnd>202510012359</event:effectiveEnd>
                              <event:text>RWY 20 RWY END ID LGT U/S</event:text>
                              <event:translation>
                                <event:NOTAMTranslation>
                                  <event:simpleText>!STL 08/430 8WC RWY 20 RWY END ID LGT U/S</event:simpleText>
                                </event:NOTAMTranslation>
                              </event:translation>
                            </event:NOTAM>
                          </event:textNOTAM>
                          <event:extension>
                            <fnse:classification>DOM</fnse:classification>
                          </event:extension>
                        </event:Event>
                      </hasMember>
                    </AIXMBasicMessage>
                    """
                ]
            },
        }

        notices = parse_notices(payload)

        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].notice_id, "NOTAM_1_1757609538792382")
        self.assertEqual(notices[0].classification, "DOM")
        self.assertIn("RWY 20", notices[0].text)

    def test_authenticated_collector_fetches_checklist_and_detail_payloads(self) -> None:
        calls: list[dict[str, object]] = []

        def _fake_urlopen(request, timeout: int = 0):
            url = request.full_url
            method = request.method
            headers = {key.lower(): value for key, value in request.header_items()}
            body = request.data.decode("utf-8") if request.data else ""
            calls.append({"url": url, "method": method, "headers": headers, "body": body})

            if url.endswith("/v1/auth/token"):
                return _FakeResponse({"access_token": "test-access-token", "status": "approved"})

            if url.startswith("https://api-staging.cgifederal-aim.com/nmsapi/v1/notams/checklist"):
                return _FakeResponse(
                    {
                        "status": "Success",
                        "data": {
                            "checklist": [
                                {
                                    "id": "NMS_ID_1234567812345678",
                                    "classification": "DOMESTIC",
                                    "accountId": "ATL",
                                    "number": "09/186",
                                    "location": "ATL",
                                    "icaoLocation": "KATL",
                                    "lastUpdated": "2026-04-05T10:21:00Z",
                                }
                            ]
                        },
                    }
                )

            if "/nmsapi/v1/notams?" in url:
                return _FakeResponse(
                    {
                        "status": "Success",
                        "data": {
                            "geojson": [
                                {
                                    "type": "Feature",
                                    "properties": {
                                        "coreNOTAMData": {
                                            "notam": {
                                                "id": "NMS_ID_1234567812345678",
                                                "classification": "DOM",
                                                "location": "KATL",
                                                "number": "09/186",
                                                "text": "AIRSPACE RESTRICTION FOR MILITARY EXERCISE",
                                                "effectiveStart": "2026-04-05T10:00:00Z",
                                                "effectiveEnd": "2026-04-05T12:00:00Z",
                                            }
                                        }
                                    },
                                }
                            ]
                        },
                    }
                )

            raise AssertionError(f"Unexpected URL requested: {url}")

        collector = NotamCollector(
            auth_url="https://api-staging.cgifederal-aim.com/v1/auth/token",
            api_base_url="https://api-staging.cgifederal-aim.com/nmsapi/v1",
            client_id="client-id",
            client_secret="client-secret",
            classification="DOMESTIC",
            accountability="ATL",
            location="KATL",
            response_format="GEOJSON",
            max_items=5,
        )

        with patch("src.collectors.notam.urlopen", side_effect=_fake_urlopen):
            observation = collector.fetch_observation()

        self.assertEqual(observation.status, "active")
        self.assertIsNone(observation.fallback_reason)
        self.assertEqual(len(observation.notices), 1)
        self.assertGreater(observation.notam_spike, 0.0)
        self.assertTrue(any("AIRSPACE RESTRICTION" in notice.text for notice in observation.notices))
        self.assertEqual(len(calls), 3)
        auth_call, checklist_call, detail_call = calls
        self.assertEqual(auth_call["method"], "POST")
        self.assertEqual(auth_call["body"], "grant_type=client_credentials")
        self.assertIn("authorization", auth_call["headers"])
        self.assertIn("application/x-www-form-urlencoded", auth_call["headers"].get("content-type", ""))
        self.assertEqual(checklist_call["method"], "GET")
        self.assertEqual(checklist_call["headers"].get("authorization"), "Bearer test-access-token")
        self.assertEqual(detail_call["method"], "GET")
        self.assertEqual(detail_call["headers"].get("authorization"), "Bearer test-access-token")
        self.assertIn("nmsId=NMS_ID_1234567812345678", detail_call["url"])
        self.assertEqual(detail_call["headers"].get("nmsresponseformat"), "GEOJSON")

        checklist_query = parse_qs(urlsplit(str(checklist_call["url"])).query)
        self.assertEqual(checklist_query.get("classification"), ["DOMESTIC"])
        self.assertEqual(checklist_query.get("accountability"), ["ATL"])
        self.assertEqual(checklist_query.get("location"), ["KATL"])

    def test_fallback_payload_is_used_when_auth_fails(self) -> None:
        collector = NotamCollector(
            auth_url="https://api-staging.cgifederal-aim.com/v1/auth/token",
            api_base_url="https://api-staging.cgifederal-aim.com/nmsapi/v1",
            client_id="client-id",
            client_secret="client-secret",
        )

        with patch("src.collectors.notam.urlopen", side_effect=URLError("boom")):
            observation = collector.fetch_observation()

        self.assertEqual(observation.status, "degraded")
        self.assertEqual(len(observation.notices), 3)
        self.assertGreater(observation.notam_spike, 0.0)
        self.assertIn("upstream service", observation.fallback_reason or "")

    def test_checklist_only_mode_avoids_detail_requests(self) -> None:
        calls: list[dict[str, object]] = []

        def _fake_urlopen(request, timeout: int = 0):
            url = request.full_url
            calls.append({"url": url, "method": request.method})
            if url.endswith("/v1/auth/token"):
                return _FakeResponse(
                    {
                        "access_token": "test-access-token",
                        "expires_in": "1799",
                        "status": "approved",
                    }
                )
            if url.startswith("https://api-staging.cgifederal-aim.com/nmsapi/v1/notams/checklist"):
                return _FakeResponse(
                    {
                        "status": "Success",
                        "data": {
                            "checklist": [
                                {
                                    "id": "1757616312849974",
                                    "classification": "DOMESTIC",
                                    "accountId": "ATL",
                                    "number": "09/186",
                                    "location": "ATL",
                                    "icaoLocation": "KATL",
                                    "lastUpdated": "2026-04-05T10:21:00Z",
                                }
                            ]
                        },
                    }
                )
            raise AssertionError(f"Unexpected URL requested: {url}")

        collector = NotamCollector(
            auth_url="https://api-staging.cgifederal-aim.com/v1/auth/token",
            api_base_url="https://api-staging.cgifederal-aim.com/nmsapi/v1",
            client_id="client-id",
            client_secret="client-secret",
            detail_fetch_enabled=False,
        )

        with patch("src.collectors.notam.urlopen", side_effect=_fake_urlopen):
            observation = collector.fetch_observation()

        self.assertEqual(observation.status, "active")
        self.assertIsNone(observation.fallback_reason)
        self.assertEqual(len(observation.notices), 1)
        self.assertEqual(len(calls), 2)
        self.assertTrue(str(calls[1]["url"]).endswith("/nmsapi/v1/notams/checklist"))

    def test_access_token_is_cached_across_fetches(self) -> None:
        calls: list[str] = []

        def _fake_urlopen(request, timeout: int = 0):
            url = request.full_url
            calls.append(url)
            if url.endswith("/v1/auth/token"):
                return _FakeResponse(
                    {
                        "access_token": "test-access-token",
                        "expires_in": "1799",
                        "status": "approved",
                    }
                )
            if url.startswith("https://api-staging.cgifederal-aim.com/nmsapi/v1/notams/checklist"):
                return _FakeResponse(
                    {
                        "status": "Success",
                        "data": {
                            "checklist": [
                                {
                                    "id": "1757616312849974",
                                    "classification": "DOMESTIC",
                                    "accountId": "ATL",
                                    "number": "09/186",
                                    "location": "ATL",
                                    "icaoLocation": "KATL",
                                    "lastUpdated": "2026-04-05T10:21:00Z",
                                }
                            ]
                        },
                    }
                )
            raise AssertionError(f"Unexpected URL requested: {url}")

        collector = NotamCollector(
            auth_url="https://api-staging.cgifederal-aim.com/v1/auth/token",
            api_base_url="https://api-staging.cgifederal-aim.com/nmsapi/v1",
            client_id="client-id",
            client_secret="client-secret",
            detail_fetch_enabled=False,
        )

        with patch("src.collectors.notam.urlopen", side_effect=_fake_urlopen):
            first = collector.fetch_observation()
            second = collector.fetch_observation()

        self.assertEqual(first.status, "active")
        self.assertEqual(second.status, "active")
        self.assertEqual(sum(1 for url in calls if url.endswith("/v1/auth/token")), 1)
        self.assertEqual(
            sum(1 for url in calls if "/nmsapi/v1/notams/checklist" in url),
            2,
        )

    def test_legacy_initial_load_source_follows_content_url_and_parses_aixm_gzip(self) -> None:
        xml_payload = """
            <AIXMBasicMessage xmlns:event="urn:us:gov:faa:atm:nems:event"
                              xmlns:fnse="urn:us:gov:faa:atm:fnse"
                              xmlns:gml="http://www.opengis.net/gml/3.2">
              <hasMember>
                <event:Event>
                  <event:textNOTAM>
                    <event:NOTAM gml:id="NOTAM_1_1757609538792382">
                      <event:number>430</event:number>
                      <event:year>2025</event:year>
                      <event:location>8WC</event:location>
                      <event:effectiveStart>202508210234</event:effectiveStart>
                      <event:effectiveEnd>202510012359</event:effectiveEnd>
                      <event:text>RWY 20 RWY END ID LGT U/S</event:text>
                      <event:translation>
                        <event:NOTAMTranslation>
                          <event:simpleText>!STL 08/430 8WC RWY 20 RWY END ID LGT U/S</event:simpleText>
                        </event:NOTAMTranslation>
                      </event:translation>
                    </event:NOTAM>
                  </event:textNOTAM>
                  <event:extension>
                    <fnse:classification>DOM</fnse:classification>
                  </event:extension>
                </event:Event>
              </hasMember>
            </AIXMBasicMessage>
        """.strip()
        content_url = "https://api-staging.cgifederal-aim.com/faa-nms/initial-load.gz"
        gzipped_xml = gzip.compress(xml_payload.encode("utf-8"))

        def _fake_urlopen(request, timeout: int = 0):
            url = request.full_url
            if url.endswith("/notams/il?allowRedirect=false"):
                return _FakeResponse({"status": "Success", "data": {"url": "/faa-nms/initial-load.gz"}})
            if url == content_url:
                return _FakeResponse(gzipped_xml)
            raise AssertionError(f"Unexpected URL requested: {url}")

        collector = NotamCollector(
            source_url="https://api-staging.cgifederal-aim.com/nmsapi/v1/notams/il?allowRedirect=false",
        )

        with patch("src.collectors.notam.urlopen", side_effect=_fake_urlopen):
            observation = collector.fetch_observation()

        self.assertEqual(observation.status, "active")
        self.assertIsNone(observation.fallback_reason)
        self.assertEqual(len(observation.notices), 1)
        self.assertEqual(observation.notices[0].notice_id, "NOTAM_1_1757609538792382")
        self.assertEqual(observation.notices[0].classification, "DOM")
        self.assertIn("RWY 20", observation.notices[0].text)

    def test_notam_spike_highlights_restricted_activity(self) -> None:
        notices = parse_notices(BOOTSTRAP_NOTAM_RESPONSE)

        spike = compute_notam_spike(notices)

        self.assertGreaterEqual(spike, 0.6)


if __name__ == "__main__":
    unittest.main()

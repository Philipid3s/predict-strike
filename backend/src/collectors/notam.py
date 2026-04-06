from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import base64
import gzip
import json
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_MAX_ITEMS = 20
TOKEN_EXPIRY_SAFETY_SECONDS = 60
NOTAM_ALERT_KEYWORDS = (
    "AIRSPACE RESTRICTION",
    "MILITARY",
    "MISSILE",
    "RESTRICTED",
    "TFR",
)
BOOTSTRAP_NOTAM_RESPONSE: dict[str, Any] = {
    "notices": [
        {
            "id": "NOTAM-A1",
            "location": "KADW",
            "classification": "RESTRICTED AIRSPACE",
            "text": "TEMPORARY FLIGHT RESTRICTION FOR MILITARY EXERCISE IN EFFECT.",
            "effective_start": "2026-04-05T08:00:00Z",
            "effective_end": "2026-04-05T14:00:00Z",
        },
        {
            "id": "NOTAM-A2",
            "location": "PAMH",
            "classification": "MISSILE ACTIVITY",
            "text": "MISSILE TEST OPERATIONS. AIRSPACE RESTRICTION ACTIVE.",
            "effective_start": "2026-04-05T09:00:00Z",
            "effective_end": "2026-04-05T12:00:00Z",
        },
        {
            "id": "NOTAM-A3",
            "location": "EGTT",
            "classification": "RUNWAY",
            "text": "RUNWAY LIGHTING MAINTENANCE.",
            "effective_start": "2026-04-05T10:00:00Z",
            "effective_end": "2026-04-05T11:30:00Z",
        },
    ]
}
_TOKEN_CACHE: dict[tuple[str, str], tuple[str, float]] = {}


@dataclass(frozen=True)
class NotamNotice:
    notice_id: str
    location: str | None
    classification: str | None
    text: str
    effective_start: str | None
    effective_end: str | None


@dataclass(frozen=True)
class NotamObservation:
    collected_at: datetime
    status: str
    raw_payload: dict[str, Any]
    notices: list[NotamNotice]
    notam_spike: float
    fallback_reason: str | None = None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_url(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().rstrip("/")
    return normalized or None


def _request_json(request: Request, timeout_seconds: int) -> dict[str, Any]:
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _request_bytes(request: Request, timeout_seconds: int) -> bytes:
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def _auth_header_value(client_id: str, client_secret: str) -> str:
    encoded = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"


def _fallback_reason_from_payload(payload: dict[str, Any]) -> str | None:
    fallback_reason = payload.get("_fallback_reason")
    if isinstance(fallback_reason, str) and fallback_reason.strip():
        return fallback_reason.strip()
    return None


def _payload_for_storage(payload: dict[str, Any], fallback_reason: str | None) -> dict[str, Any]:
    stored_payload = dict(payload)
    if fallback_reason:
        stored_payload["_fallback_reason"] = fallback_reason
    else:
        stored_payload.pop("_fallback_reason", None)
    return stored_payload


def _extract_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _extract_content_url(payload: dict[str, Any]) -> str | None:
    data = payload.get("data")
    if isinstance(data, dict):
        content_url = _normalize_text(data.get("url"))
        if content_url is not None:
            return content_url
    return _normalize_text(payload.get("url"))


def _payload_from_content_bytes(content: bytes) -> dict[str, Any]:
    if content[:2] == b"\x1f\x8b":
        content = gzip.decompress(content)

    text = content.decode("utf-8").strip()
    if not text:
        return {}

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = text

    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        return {"data": {"aixm": parsed}}

    return {"status": "Success", "data": {"aixm": [parsed]}}


def _extract_notices_from_checklist_item(item: dict[str, Any]) -> list[NotamNotice]:
    notice_id = _normalize_text(item.get("id") or item.get("notice_id") or "unknown") or "unknown"
    location = _normalize_text(item.get("icaoLocation") or item.get("location"))
    classification = _normalize_text(item.get("classification"))
    number = _normalize_text(item.get("number"))
    account_id = _normalize_text(item.get("accountId"))
    text = _normalize_text(item.get("text") or item.get("message"))
    if text is None:
        text = " ".join(
            part
            for part in (
                classification,
                account_id,
                location,
                number,
            )
            if part
        )
    text = " ".join(
        part
        for part in (text,)
        if part
    )
    return [
        NotamNotice(
            notice_id=notice_id,
            location=location,
            classification=classification,
            text=text or notice_id,
            effective_start=_normalize_text(item.get("effectiveStart") or item.get("effective_start")),
            effective_end=_normalize_text(item.get("effectiveEnd") or item.get("effective_end")),
        )
    ]


def _first_text(element: ET.Element, *paths: str) -> str | None:
    for path in paths:
        value = element.findtext(path)
        normalized = _normalize_text(value)
        if normalized is not None:
            return normalized
    return None


def _first_descendant_text_by_local_name(
    element: ET.Element, *local_names: str
) -> str | None:
    targets = set(local_names)
    for descendant in element.iter():
        local_name = descendant.tag.rsplit("}", 1)[-1]
        if local_name not in targets:
            continue
        normalized = _normalize_text(descendant.text)
        if normalized is not None:
            return normalized
    return None


def _extract_notices_from_aixm_xml(xml_text: str) -> list[NotamNotice]:
    notices: list[NotamNotice] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return notices

    for notam_node in root.findall(".//{*}NOTAM"):
        notice_id = _normalize_text(
            notam_node.attrib.get("{http://www.opengis.net/gml/3.2}id")
            or notam_node.attrib.get("gml:id")
            or notam_node.attrib.get("id")
        )
        number = _first_text(notam_node, "./{*}number")
        year = _first_text(notam_node, "./{*}year")
        location = _first_text(notam_node, "./{*}location")
        classification = _first_text(
            notam_node,
            ".//{*}classification",
            ".//{*}classificationCode",
        )
        if classification is None:
            classification = _first_text(
                root,
                ".//{*}classification",
                ".//{*}classificationCode",
            )
        if classification is None:
            classification = _first_descendant_text_by_local_name(
                root,
                "classification",
                "classificationCode",
            )
        text = _first_text(
            notam_node,
            ".//{*}translation//{*}simpleText",
            "./{*}text",
        )
        effective_start = _first_text(notam_node, "./{*}effectiveStart")
        effective_end = _first_text(notam_node, "./{*}effectiveEnd")
        if notice_id is None:
            notice_id = "-".join(part for part in (number, year) if part) or "unknown"

        notices.append(
            NotamNotice(
                notice_id=notice_id,
                location=location,
                classification=classification,
                text=text or " ".join(part for part in (classification, location, number) if part)
                or notice_id,
                effective_start=effective_start,
                effective_end=effective_end,
            )
        )
    return notices


def _extract_notices_from_geojson_feature(feature: dict[str, Any]) -> list[NotamNotice]:
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        return []
    core = properties.get("coreNOTAMData")
    if not isinstance(core, dict):
        return []
    notam = core.get("notam")
    if not isinstance(notam, dict):
        return []
    translations = core.get("notamTranslation")

    notice_id = _normalize_text(notam.get("id") or notam.get("nmsId") or "unknown") or "unknown"
    location = _normalize_text(notam.get("icaoLocation") or notam.get("location"))
    classification = _normalize_text(notam.get("classification"))
    text = _normalize_text(notam.get("text"))
    if text is None:
        if isinstance(translations, list):
            for translation in translations:
                if not isinstance(translation, dict):
                    continue
                text = _normalize_text(
                    translation.get("domestic_message")
                    or translation.get("icao_message")
                    or translation.get("simpleText")
                )
                if text is not None:
                    break

    return [
        NotamNotice(
            notice_id=notice_id,
            location=location,
            classification=classification,
            text=text or " ".join(part for part in (classification, location, notice_id) if part)
            or notice_id,
            effective_start=_normalize_text(notam.get("effectiveStart")),
            effective_end=_normalize_text(notam.get("effectiveEnd")),
        )
    ]


def _parse_notices(payload: Any) -> list[NotamNotice]:
    notices: list[NotamNotice] = []

    if isinstance(payload, list):
        for item in payload:
            notices.extend(_parse_notices(item))
        return notices

    if not isinstance(payload, dict):
        return notices

    if isinstance(payload.get("notices"), list):
        for item in payload["notices"]:
            if isinstance(item, dict):
                notices.extend(_extract_notices_from_checklist_item(item))

    if isinstance(payload.get("details"), list):
        for detail in payload["details"]:
            notices.extend(_parse_notices(detail))
    elif isinstance(payload.get("details"), dict):
        notices.extend(_parse_notices(payload["details"]))

    if isinstance(payload.get("checklist"), list):
        for item in payload["checklist"]:
            if isinstance(item, dict):
                notices.extend(_extract_notices_from_checklist_item(item))
    elif isinstance(payload.get("checklist"), dict):
        notices.extend(_parse_notices(payload["checklist"]))

    data = payload.get("data")
    if isinstance(data, dict):
        notices.extend(_parse_notices(data))

    if isinstance(payload.get("geojson"), list):
        for feature in payload["geojson"]:
            if isinstance(feature, dict):
                notices.extend(_extract_notices_from_geojson_feature(feature))

    if isinstance(payload.get("aixm"), list):
        for xml_text in payload["aixm"]:
            if isinstance(xml_text, str) and xml_text.strip():
                notices.extend(_extract_notices_from_aixm_xml(xml_text))

    return notices


def _dedupe_notices(notices: list[NotamNotice]) -> list[NotamNotice]:
    seen: set[str] = set()
    deduped: list[NotamNotice] = []
    for notice in notices:
        if notice.notice_id in seen:
            continue
        seen.add(notice.notice_id)
        deduped.append(notice)
    return deduped


def parse_notices(payload: Any) -> list[NotamNotice]:
    return _dedupe_notices(_parse_notices(payload))


def compute_notam_spike(notices: list[NotamNotice]) -> float:
    flagged_count = 0
    for notice in notices:
        haystack = f"{notice.classification or ''} {notice.text}".upper()
        if any(keyword in haystack for keyword in NOTAM_ALERT_KEYWORDS):
            flagged_count += 1
    score = (len(notices) * 0.08) + (flagged_count * 0.18)
    return round(min(score, 1.0), 4)


class NotamCollector:
    def __init__(
        self,
        source_url: str | None = None,
        *,
        auth_url: str | None = None,
        api_base_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        classification: str | None = None,
        accountability: str | None = None,
        location: str | None = None,
        response_format: str = "GEOJSON",
        detail_fetch_enabled: bool = True,
        max_items: int = DEFAULT_MAX_ITEMS,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        payload_loader: Callable[[], dict[str, Any]] | None = None,
        fallback_payload: dict[str, Any] | None = None,
    ) -> None:
        self._legacy_source_url = _normalize_url(source_url)
        self._auth_url = _normalize_url(auth_url)
        self._api_base_url = _normalize_url(api_base_url)
        self._client_id = client_id.strip() if isinstance(client_id, str) and client_id.strip() else None
        self._client_secret = (
            client_secret.strip() if isinstance(client_secret, str) and client_secret.strip() else None
        )
        self._classification = (
            classification.strip().upper() if isinstance(classification, str) and classification.strip() else None
        )
        self._accountability = (
            accountability.strip().upper() if isinstance(accountability, str) and accountability.strip() else None
        )
        self._location = location.strip().upper() if isinstance(location, str) and location.strip() else None
        self._response_format = (
            response_format.strip().upper()
            if isinstance(response_format, str) and response_format.strip()
            else "GEOJSON"
        )
        self._detail_fetch_enabled = detail_fetch_enabled
        self._max_items = max(max_items, 1)
        self._timeout_seconds = max(timeout_seconds, 1)
        self._payload_loader = payload_loader
        self._fallback_payload = fallback_payload or BOOTSTRAP_NOTAM_RESPONSE

    def fetch_observation(self) -> NotamObservation:
        try:
            if self._payload_loader is not None:
                payload = self._payload_loader()
            else:
                payload = self._load_live_payload()
            notices = parse_notices(payload)
            fallback_reason = _fallback_reason_from_payload(payload)
            status = "degraded" if fallback_reason else "active"
            return NotamObservation(
                collected_at=_utc_now(),
                status=status,
                raw_payload=payload,
                notices=notices,
                notam_spike=compute_notam_spike(notices),
                fallback_reason=fallback_reason,
            )
        except Exception as exc:
            fallback_reason = f"{exc.__class__.__name__}: {exc}"
            payload = _payload_for_storage(self._fallback_payload, fallback_reason)
            notices = parse_notices(payload)
            return NotamObservation(
                collected_at=_utc_now(),
                status="degraded",
                raw_payload=payload,
                notices=notices,
                notam_spike=compute_notam_spike(notices),
                fallback_reason=fallback_reason,
            )

    def _load_live_payload(self) -> dict[str, Any]:
        if self._legacy_source_url is not None and not self._auth_flow_is_configured():
            request = Request(self._legacy_source_url, method="GET")
            payload = _request_json(request, self._timeout_seconds)
            content_url = _extract_content_url(payload)
            if content_url is None:
                return payload
            resolved_content_url = urljoin(self._legacy_source_url, content_url)
            return _payload_from_content_bytes(
                _request_bytes(Request(resolved_content_url, method="GET"), self._timeout_seconds)
            )

        if not self._auth_flow_is_configured():
            raise RuntimeError("NOTAM API base URL and OAuth credentials are not configured.")

        access_token = self._fetch_access_token()
        checklist_payload = self._fetch_checklist_payload(access_token)
        if not self._detail_fetch_enabled:
            return {
                "status": checklist_payload.get("status", "Success"),
                "data": {
                    "checklist": checklist_payload.get("data", checklist_payload),
                    "details": [],
                },
            }
        checklist_items = self._extract_checklist_items(checklist_payload)
        detail_payloads: list[dict[str, Any]] = []
        detail_failures: list[str] = []

        for item in checklist_items[: self._max_items]:
            notam_id = _normalize_text(item.get("id") or item.get("notice_id"))
            if notam_id is None:
                detail_failures.append("checklist_item_missing_id")
                continue
            try:
                detail_payloads.append(self._fetch_notam_detail_payload(access_token, notam_id))
            except Exception as exc:
                detail_failures.append(f"{notam_id}:{exc}")

        payload: dict[str, Any] = {
            "status": "Success",
            "data": {
                "checklist": checklist_payload.get("data", checklist_payload),
                "details": detail_payloads,
            },
        }
        if detail_failures:
            payload["_fallback_reason"] = "; ".join(detail_failures[:5])
        return payload

    def _auth_flow_is_configured(self) -> bool:
        return all(
            (
                self._auth_url,
                self._api_base_url,
                self._client_id,
                self._client_secret,
            )
        )

    def _fetch_access_token(self) -> str:
        if not self._auth_url or not self._client_id or not self._client_secret:
            raise RuntimeError("NOTAM OAuth credentials are not configured.")

        cache_key = (self._auth_url, self._client_id)
        cached = _TOKEN_CACHE.get(cache_key)
        if cached is not None:
            access_token, expires_at = cached
            if time.monotonic() < expires_at:
                return access_token

        request = Request(
            self._auth_url,
            data=urlencode({"grant_type": "client_credentials"}).encode("utf-8"),
            headers={
                "Authorization": _auth_header_value(self._client_id, self._client_secret),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )

        try:
            payload = _request_json(request, self._timeout_seconds)
        except HTTPError as exc:
            status_code = getattr(exc, "code", "unknown")
            raise RuntimeError(f"NOTAM auth request failed with HTTP {status_code}.") from exc
        except URLError as exc:
            raise RuntimeError(
                f"NOTAM auth request could not reach the upstream service: URLError: {exc.reason}."
            ) from exc

        access_token = _normalize_text(payload.get("access_token"))
        if access_token is None:
            raise RuntimeError("NOTAM auth response did not include an access_token.")
        expires_in_raw = _normalize_text(payload.get("expires_in"))
        expires_in_seconds = int(expires_in_raw) if expires_in_raw and expires_in_raw.isdigit() else 1800
        _TOKEN_CACHE[cache_key] = (
            access_token,
            time.monotonic() + max(expires_in_seconds - TOKEN_EXPIRY_SAFETY_SECONDS, 1),
        )
        return access_token

    def _fetch_checklist_payload(self, access_token: str) -> dict[str, Any]:
        if not self._api_base_url:
            raise RuntimeError("NOTAM API base URL is not configured.")

        query: dict[str, Any] = {}
        if self._classification is not None:
            query["classification"] = self._classification
        if self._accountability is not None:
            query["accountability"] = self._accountability
        if self._location is not None:
            query["location"] = self._location
        request = Request(
            f"{self._api_base_url}/notams/checklist{f'?{urlencode(query)}' if query else ''}",
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET",
        )
        return _request_json(request, self._timeout_seconds)

    def _fetch_notam_detail_payload(self, access_token: str, notam_id: str) -> dict[str, Any]:
        if not self._api_base_url:
            raise RuntimeError("NOTAM API base URL is not configured.")
        if self._response_format not in {"AIXM", "GEOJSON"}:
            raise RuntimeError(
                f"Unsupported NOTAM response format: {self._response_format!r}. Expected AIXM or GEOJSON."
            )

        query = urlencode(
            {
                "nmsId": notam_id,
            }
        )
        request = Request(
            f"{self._api_base_url}/notams?{query}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "nmsResponseFormat": self._response_format,
            },
            method="GET",
        )
        return _request_json(request, self._timeout_seconds)

    @staticmethod
    def _extract_checklist_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data")
        if isinstance(data, dict):
            checklist = data.get("checklist")
            if isinstance(checklist, list):
                return [item for item in checklist if isinstance(item, dict)]
        checklist = payload.get("checklist")
        if isinstance(checklist, list):
            return [item for item in checklist if isinstance(item, dict)]
        return []

from dataclasses import dataclass
import json
from pathlib import Path
import re


@dataclass(frozen=True)
class Airfield:
    name: str
    country: str
    operator: str
    latitude: float
    longitude: float


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _normalize_key(value: str) -> str:
    normalized = value.lower().replace("â€“", "-").replace("–", "-")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(normalized.split())


def _normalize_country(country: str) -> str:
    return {
        "USA": "United States",
        "UK": "United Kingdom",
    }.get(country, country)


def _operator_from_type(base_type: str) -> str:
    return {
        "US": "US military",
        "NATO": "NATO military",
    }.get(base_type, "Military")


CURATED_US_NATO_MILITARY_AIRFIELDS: tuple[Airfield, ...] = (
    Airfield("Ramstein AB", "Germany", "USAF", 49.4369, 7.6003),
    Airfield("Spangdahlem AB", "Germany", "USAF", 49.9727, 6.6925),
    Airfield("NATO Air Base Geilenkirchen", "Germany", "NATO", 50.9608, 6.0424),
    Airfield("RAF Lakenheath", "United Kingdom", "USAF", 52.4093, 0.5610),
    Airfield("RAF Mildenhall", "United Kingdom", "USAF", 52.3619, 0.4864),
    Airfield("RAF Akrotiri", "Cyprus", "RAF", 34.5904, 32.9879),
    Airfield("Aviano AB", "Italy", "USAF", 46.0319, 12.5965),
    Airfield("Naval Air Station Sigonella", "Italy", "US Navy", 37.4017, 14.9224),
    Airfield("Incirlik AB", "Turkey", "USAF/Turkish AF", 37.0019, 35.4259),
    Airfield("Naval Station Rota", "Spain", "US Navy", 36.6452, -6.3490),
    Airfield("Moron Air Base", "Spain", "Spanish AF/USAF", 37.1749, -5.6159),
    Airfield("Mihail Kogalniceanu Air Base", "Romania", "Romanian AF/NATO", 44.3622, 28.4883),
    Airfield("33rd Air Base Powidz", "Poland", "Polish AF/NATO", 52.3794, 17.8539),
    Airfield("Kleine Brogel Air Base", "Belgium", "Belgian AF/NATO", 51.1697, 5.4708),
    Airfield("Volkel Air Base", "Netherlands", "Royal Netherlands AF/NATO", 51.6564, 5.7086),
    Airfield("NAS Keflavik", "Iceland", "Iceland/NATO", 63.9850, -22.6056),
    Airfield("Souda Bay", "Greece", "Hellenic AF/NATO", 35.5317, 24.1497),
    Airfield("Al Udeid AB", "Qatar", "USAF", 25.1173, 51.3144),
    Airfield("Ali Al Salem Air Base", "Kuwait", "Kuwaiti AF/USAF", 29.3469, 47.5208),
    Airfield("Andersen AFB", "United States", "USAF", 13.5840, 144.9300),
    Airfield("Joint Base Pearl Harbor-Hickam", "United States", "USAF/US Navy", 21.3187, -157.9225),
    Airfield("Joint Base Langley-Eustis", "United States", "USAF", 37.0829, -76.3605),
    Airfield("Joint Base Andrews", "United States", "USAF", 38.8108, -76.8670),
    Airfield("MacDill AFB", "United States", "USAF", 27.8493, -82.5212),
    Airfield("Nellis AFB", "United States", "USAF", 36.2362, -115.0337),
)


def _load_reference_airfields() -> tuple[Airfield, ...]:
    path = _repo_root() / "docs" / "ref" / "bases.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    items: list[Airfield] = []
    for row in payload.get("bases", []):
        items.append(
            Airfield(
                name=str(row["name"]).replace("â€“", "-"),
                country=_normalize_country(str(row["country"])),
                operator=_operator_from_type(str(row.get("type", ""))),
                latitude=float(row["lat"]),
                longitude=float(row["lon"]),
            )
        )
    return tuple(items)


def _merge_airfields() -> tuple[Airfield, ...]:
    merged: dict[str, Airfield] = {}
    for airfield in _load_reference_airfields():
        merged[_normalize_key(airfield.name)] = airfield
    for airfield in CURATED_US_NATO_MILITARY_AIRFIELDS:
        merged[_normalize_key(airfield.name)] = airfield
    return tuple(sorted(merged.values(), key=lambda airfield: airfield.name))


US_NATO_MILITARY_AIRFIELDS: tuple[Airfield, ...] = _merge_airfields()

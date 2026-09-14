#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent

SOURCES = {
    "tram": BASE / "ostrava-tram-data-v2.json",
    "trolleybus": BASE / "ostrava-trolleybus-data.json",
    "bus": BASE / "ostrava-bus-data.json",
}

EXPECTED = {
    "tram": {"1","2","3","4","5","7","8","10","11","12","13","14","15","17","18","19"},
    "trolleybus": {"101","102","103","104","105","106","107","108","109","111","112","113"},
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def reverse_pair(patterns: list[dict]) -> bool:
    ends = {(p.get("from", "").casefold(), p.get("to", "").casefold()) for p in patterns}
    return any((b, a) in ends for a, b in ends)


def normalize_line(line: str, row: dict) -> dict:
    patterns = row.get("patterns") or row.get("directions") or []
    normalized = []
    for i, p in enumerate(patterns, 1):
        stops = [str(x).strip() for x in p.get("stops", []) if str(x).strip()]
        if not stops:
            continue
        normalized.append({
            "id": p.get("id") or f"p{i}",
            "from": p.get("from") or stops[0],
            "to": p.get("to") or stops[-1],
            "stops": stops,
        })

    row = dict(row)
    row["patterns"] = normalized
    row["directions"] = normalized
    row["hasVariants"] = len(normalized) != 2 or not reverse_pair(normalized)
    row["patternCount"] = len(normalized)
    return row


def patch_airport_express(bus: dict) -> None:
    """AE is a special two-stop airport express PDF, not the standard DPO table layout."""
    row = bus.setdefault("lines", {}).setdefault("AE", {})
    patterns = [
        {"id": "p1", "from": "Dubina", "to": "Mošnov,Airport nádraží", "stops": ["Dubina", "Mošnov,Airport nádraží"]},
        {"id": "p2", "from": "Mošnov,Airport nádraží", "to": "Dubina", "stops": ["Mošnov,Airport nádraží", "Dubina"]},
    ]
    row.update({
        "validFrom": row.get("validFrom") or "2026-09-04",
        "routeLabel": row.get("routeLabel") or "Mošnov,Airport nádraží – Dubina",
        "sourcePdf": row.get("sourcePdf") or "https://www.dpo.cz/jr/2026-09-04/AE.pdf",
        "hasVariants": False,
        "patternCount": 2,
        "patterns": patterns,
        "directions": patterns,
        "specialLayout": True,
    })


def main() -> int:
    modes = {mode: load(path) for mode, path in SOURCES.items()}

    # ND1/ND2 are replacement services, not regular tram lines for the PWA selector.
    modes["tram"]["lines"] = {
        k: v for k, v in modes["tram"].get("lines", {}).items() if k in EXPECTED["tram"]
    }
    modes["trolleybus"]["lines"] = {
        k: v for k, v in modes["trolleybus"].get("lines", {}).items() if k in EXPECTED["trolleybus"]
    }

    patch_airport_express(modes["bus"])

    for mode, doc in modes.items():
        doc["lines"] = {line: normalize_line(line, row) for line, row in doc.get("lines", {}).items()}

    # Explicitly preserve the known asymmetric route-5 model rather than forcing two reverse directions.
    if "5" in modes["tram"]["lines"]:
        modes["tram"]["lines"]["5"]["hasVariants"] = True
        modes["tram"]["lines"]["5"]["variantReason"] = "asymmetric/through-running timetable pattern"

    problems = []
    for mode in ("tram", "trolleybus"):
        actual = set(modes[mode]["lines"])
        if actual != EXPECTED[mode]:
            problems.append(f"{mode}: expected {sorted(EXPECTED[mode])}, got {sorted(actual)}")

    for mode, doc in modes.items():
        for line, row in doc["lines"].items():
            if not row.get("patterns"):
                problems.append(f"{mode} {line}: no patterns")
            for p in row.get("patterns", []):
                if len(p.get("stops", [])) < 2:
                    problems.append(f"{mode} {line} {p.get('id')}: fewer than two stops")

    combined = {
        "schemaVersion": 2,
        "source": "DPO official PDF timetables",
        "modes": {
            mode: {
                "source": doc.get("source"),
                "generatedAt": doc.get("generatedAt"),
                "lineCount": len(doc["lines"]),
                "lines": doc["lines"],
            }
            for mode, doc in modes.items()
        },
    }

    (BASE / "ostrava-transit-data.json").write_text(
        json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (BASE / "final-validation.json").write_text(
        json.dumps({
            "ok": not problems,
            "problems": problems,
            "lineCounts": {m: len(d["lines"]) for m, d in modes.items()},
            "variantLines": {
                m: [line for line, row in d["lines"].items() if row.get("hasVariants")]
                for m, d in modes.items()
            },
        }, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps(json.loads((BASE / "final-validation.json").read_text(encoding="utf-8")), ensure_ascii=False, indent=2))
    return 0 if not problems else 2


if __name__ == "__main__":
    raise SystemExit(main())

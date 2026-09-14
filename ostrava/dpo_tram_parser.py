#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import pymupdf
import requests
from bs4 import BeautifulSoup

INDEX_URL = "https://www.dpo.cz/jizdni-rady/jr-tram.html"
UA = "Mozilla/5.0 (compatible; DPO timetable parser/2.0)"
ICON_CHARS = set("")
DAY_LABELS = {"pracovni den", "sobota+nedele", "cely tyden"}


@dataclass
class Schedule:
    line: str
    route_label: str
    valid_from: dt.date
    pdf_url: str


def clean_space(s: str) -> str:
    s = s.replace("\xa0", " ")
    s = "".join(ch for ch in s if ch not in ICON_CHARS)
    s = re.sub(r"\s+", " ", s).strip()
    # DPO PDFs sometimes expose a standalone OCR marker "O" after a stop name.
    s = re.sub(r"\s+O$", "", s)
    return s


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.casefold()


def parse_date_cz(s: str) -> dt.date | None:
    m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", s)
    if not m:
        return None
    d, mo, y = map(int, m.groups())
    return dt.date(y, mo, d)


def fetch_index(session: requests.Session) -> list[Schedule]:
    r = session.get(INDEX_URL, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    schedules: list[Schedule] = []

    for heading in soup.find_all(["h3", "h4"]):
        line = clean_space(heading.get_text(" ", strip=True))
        if not re.fullmatch(r"\d{1,3}", line):
            continue

        texts: list[str] = []
        pdf_href = None
        node = heading
        for _ in range(16):
            node = node.find_next()
            if node is None:
                break
            if node.name in ("h3", "h4") and node is not heading:
                ntext = clean_space(node.get_text(" ", strip=True))
                if re.fullmatch(r"\d{1,3}|ND\d+", ntext):
                    break
            txt = clean_space(node.get_text(" ", strip=True))
            if txt:
                texts.append(txt)
            if node.name == "a":
                href = node.get("href")
                if href and re.search(r"\.pdf(?:$|\?)", href, re.I):
                    pdf_href = href
                    break

        if not pdf_href:
            a = heading.find_next("a", href=re.compile(r"\.pdf(?:$|\?)", re.I))
            if a:
                pdf_href = a.get("href")

        blob = " | ".join(dict.fromkeys(texts))
        valid = parse_date_cz(blob)
        if not valid or not pdf_href:
            continue

        route_label = ""
        for t in texts:
            if "Platí od" in t:
                break
            if t != line and not t.lower().startswith("jízdní řád"):
                route_label = t
                break

        schedules.append(Schedule(line, route_label, valid, urljoin(INDEX_URL, pdf_href)))

    uniq = {(s.line, s.valid_from, s.pdf_url): s for s in schedules}
    return sorted(uniq.values(), key=lambda s: (int(s.line), s.valid_from))


def choose_schedule_set(schedules: list[Schedule], effective_date: dt.date | None, latest_published: bool) -> list[Schedule]:
    by_line: dict[str, list[Schedule]] = defaultdict(list)
    for s in schedules:
        by_line[s.line].append(s)

    result = []
    for line, arr in sorted(by_line.items(), key=lambda kv: int(kv[0])):
        arr.sort(key=lambda s: s.valid_from)
        if latest_published:
            result.append(arr[-1])
            continue
        target = effective_date or dt.date.today()
        eligible = [s for s in arr if s.valid_from <= target]
        result.append(eligible[-1] if eligible else arr[0])
    return result


def download_pdf(session: requests.Session, s: Schedule, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = cache_dir / f"{int(s.line):03d}_{s.valid_from.isoformat()}.pdf"
    if p.exists() and p.stat().st_size > 1000:
        return p
    r = session.get(s.pdf_url, timeout=60)
    r.raise_for_status()
    if "pdf" not in r.headers.get("content-type", "").lower() and not r.content.startswith(b"%PDF"):
        raise RuntimeError(f"{s.line}: expected PDF, got {r.headers.get('content-type')}")
    p.write_bytes(r.content)
    return p


def looks_like_stop(text: str) -> bool:
    f = fold(text)
    if not text or not re.search(r"[A-Za-zÁ-ž]", text):
        return False
    if f in {"zona", "nazev zastavky", "min", "poznamky"} | DAY_LABELS:
        return False
    if f.startswith("plati od") or f.startswith("www.dpo.cz") or f.startswith("upraveno"):
        return False
    if f.startswith("bezbarier") or f.startswith("prestup na zeleznicni"):
        return False
    if re.fullmatch(r"[A-Z]{1,4}(?:\s+[A-Z]{1,4})*", text):
        return False
    return True


def extract_sequences_from_text(text: str, line: str) -> list[list[str]]:
    """
    DPO's PDF text layer is more reliable for stop names than spatial word coordinates.
    A route table contains a standalone line number followed by consecutive stop-name
    rows; the first minute/travel-time row marks the end of the stop list.
    """
    rows = text.splitlines()
    sequences: list[list[str]] = []

    for i, raw in enumerate(rows):
        if raw.strip() != line:
            continue
        seq: list[str] = []
        for raw2 in rows[i + 1:]:
            t = clean_space(raw2)
            if not t:
                continue
            # First travel-time row after the stop block.
            if re.fullmatch(r"\d+(?:-\d+)?", t):
                break
            if re.match(r"(?i)^plat[ií]\s+od", t):
                break
            if looks_like_stop(t):
                seq.append(t)
        # Suppress false hits where the same route number appears in timetable grids.
        if len(seq) >= 5:
            sequences.append(seq)

    return sequences


def normalize_sequence(seq: list[str]) -> list[str]:
    out: list[str] = []
    for s in seq:
        s = clean_space(s)
        if not looks_like_stop(s):
            continue
        if out and fold(out[-1]) == fold(s):
            # Keep consecutive duplicate stops only when the PDF explicitly has them
            # as different platforms/variants; for navigation data they are redundant.
            continue
        out.append(s)
    return out


def dedupe_sequences(sequences: list[list[str]]) -> list[list[str]]:
    unique: list[list[str]] = []
    seen = set()
    for seq in sequences:
        seq = normalize_sequence(seq)
        if len(seq) < 5:
            continue
        key = tuple(fold(x) for x in seq)
        if key not in seen:
            seen.add(key)
            unique.append(seq)
    return unique


def parse_pdf(pdf_path: Path, line: str, debug_path: Path | None = None) -> list[list[str]]:
    doc = pymupdf.open(pdf_path)
    raw_sequences: list[list[str]] = []
    debug = []

    for pno, page in enumerate(doc):
        plain = page.get_text("text")
        page_sequences = extract_sequences_from_text(plain, line)
        raw_sequences.extend(page_sequences)
        if debug_path is not None:
            debug.append({
                "page": pno + 1,
                "plain_text": plain,
                "candidate_sequences": page_sequences,
            })

    sequences = dedupe_sequences(raw_sequences)
    if debug_path is not None:
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")
    return sequences


def validate(line: str, sequences: list[list[str]]) -> dict:
    warnings = []
    if not sequences:
        warnings.append("no stop sequences extracted")
    if len(sequences) < 2:
        warnings.append("only one route direction/variant extracted")
    for i, s in enumerate(sequences):
        if len(s) < 8:
            warnings.append(f"sequence {i+1} unusually short ({len(s)} stops)")
        if len(s) != len(set(map(fold, s))):
            warnings.append(f"sequence {i+1} contains duplicate stop names")

    # Typical bidirectional lines should have at least one reverse endpoint pairing.
    endpoints = {(fold(s[0]), fold(s[-1])) for s in sequences if s}
    reverse_pair = any((b, a) in endpoints for a, b in endpoints)
    if len(sequences) >= 2 and not reverse_pair:
        warnings.append("no exact reverse endpoint pair; may be a branched/variant route")

    fatal = not sequences or any(len(s) < 5 for s in sequences)
    return {
        "ok": not fatal,
        "line": line,
        "sequence_count": len(sequences),
        "stop_counts": [len(s) for s in sequences],
        "endpoints": [{"from": s[0], "to": s[-1]} for s in sequences],
        "warnings": warnings,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--effective-date")
    ap.add_argument("--latest-published", action="store_true")
    ap.add_argument("--output", default="ostrava-tram-data.json")
    ap.add_argument("--report", default="tram-parser-report.json")
    ap.add_argument("--cache-dir", default=".cache/dpo-pdf")
    ap.add_argument("--debug-dir", default=None)
    args = ap.parse_args()

    eff = dt.date.fromisoformat(args.effective_date) if args.effective_date else None
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    schedules = fetch_index(session)
    if not schedules:
        raise SystemExit("No DPO tram timetables found on index page.")
    chosen = choose_schedule_set(schedules, eff, args.latest_published)

    data = {
        "source": INDEX_URL,
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "requestedEffectiveDate": eff.isoformat() if eff else None,
        "latestPublished": args.latest_published,
        "tram": {},
    }
    report = []

    for s in chosen:
        try:
            pdf = download_pdf(session, s, Path(args.cache_dir))
            dbg = Path(args.debug_dir) / f"line-{s.line}.json" if args.debug_dir else None
            seqs = parse_pdf(pdf, s.line, dbg)
            data["tram"][s.line] = {
                "validFrom": s.valid_from.isoformat(),
                "routeLabel": s.route_label,
                "sourcePdf": s.pdf_url,
                "directions": [{"from": seq[0], "to": seq[-1], "stops": seq} for seq in seqs],
            }
            v = validate(s.line, seqs)
            v.update({"sourcePdf": s.pdf_url, "validFrom": s.valid_from.isoformat()})
            report.append(v)
            print(f"{s.line:>3}: {len(seqs)} sequence(s), {[len(x) for x in seqs]} stops {'OK' if v['ok'] else 'FAIL'}")
            for warning in v["warnings"]:
                print(f"     warning: {warning}")
        except Exception as e:
            report.append({
                "ok": False,
                "line": s.line,
                "validFrom": s.valid_from.isoformat(),
                "sourcePdf": s.pdf_url,
                "error": repr(e),
            })
            print(f"{s.line:>3}: ERROR {e}", file=sys.stderr)

    Path(args.output).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for r in report if r.get("ok"))
    print(f"\nResult: {ok}/{len(report)} lines parsed without fatal error.")
    return 0 if ok == len(report) else 2


if __name__ == "__main__":
    raise SystemExit(main())

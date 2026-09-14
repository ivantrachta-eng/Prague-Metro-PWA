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

MODE_CONFIG = {
    "tram": {"index": "https://www.dpo.cz/jizdni-rady/jr-tram.html", "label": "tram"},
    "bus": {"index": "https://www.dpo.cz/jizdni-rady/jr-bus.html", "label": "bus"},
    "trolleybus": {"index": "https://www.dpo.cz/jizdni-rady/jr-trol.html", "label": "trolleybus"},
}
UA = "Mozilla/5.0 (compatible; DPO timetable parser/3.0)"
DAY_LABELS = {"pracovni den", "sobota+nedele", "cely tyden", "sobota", "nedele"}

@dataclass
class Schedule:
    line: str
    route_label: str
    valid_from: dt.date
    pdf_url: str


def clean_space(s: str) -> str:
    s = s.replace("\xa0", " ")
    # Keep normal text, drop DPO symbol-font/private-use glyphs.
    s = re.sub(r"[\ue000-\uf8ff]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
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


def line_sort_key(line: str):
    return (0, int(line)) if line.isdigit() else (1, line)


def is_line_id(text: str) -> bool:
    return bool(re.fullmatch(r"(?:\d{1,3}|[A-Z]{1,3}\d{0,2})", text))


def fetch_index(session: requests.Session, index_url: str) -> list[Schedule]:
    r = session.get(index_url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    schedules: list[Schedule] = []

    for heading in soup.find_all(["h3", "h4"]):
        line = clean_space(heading.get_text(" ", strip=True))
        if not is_line_id(line):
            continue

        texts: list[str] = []
        pdf_href = None
        node = heading
        for _ in range(20):
            node = node.find_next()
            if node is None:
                break
            if node.name in ("h3", "h4") and node is not heading:
                ntext = clean_space(node.get_text(" ", strip=True))
                if is_line_id(ntext):
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

        schedules.append(Schedule(line, route_label, valid, urljoin(index_url, pdf_href)))

    uniq = {(s.line, s.valid_from, s.pdf_url): s for s in schedules}
    return sorted(uniq.values(), key=lambda s: (line_sort_key(s.line), s.valid_from))


def choose_schedule_set(schedules: list[Schedule], effective_date: dt.date | None, latest_published: bool) -> list[Schedule]:
    by_line: dict[str, list[Schedule]] = defaultdict(list)
    for s in schedules:
        by_line[s.line].append(s)
    result = []
    for line, arr in sorted(by_line.items(), key=lambda kv: line_sort_key(kv[0])):
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
    safe_line = re.sub(r"[^A-Za-z0-9_-]", "_", s.line)
    p = cache_dir / f"{safe_line}_{s.valid_from.isoformat()}.pdf"
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
    if f.startswith(("plati od", "www.dpo.cz", "upraveno", "jizdni rad")):
        return False
    if "vsechny spoje" in f or "prestup na zeleznicni" in f or "zastavka na znameni" in f:
        return False
    if re.fullmatch(r"[A-Z]{1,4}(?:\s+[A-Z]{1,4})*", text):
        return False
    return True


def split_symbol_line(raw: str) -> list[str]:
    """Split a PDF text row when DPO symbol glyphs separate stop names."""
    parts = re.split(r"[\ue000-\uf8ff]+", raw)
    return [clean_space(p) for p in parts if clean_space(p)]


def extract_sequences_from_text(text: str, line: str) -> list[list[str]]:
    rows = text.splitlines()
    sequences: list[list[str]] = []

    for i, raw in enumerate(rows):
        if clean_space(raw) != line:
            continue
        seq: list[str] = []
        for raw2 in rows[i + 1:]:
            stripped = raw2.strip()
            t = clean_space(stripped)
            if not t:
                continue
            if re.fullmatch(r"\d+(?:-\d+)+|\d+", t):
                break
            if re.match(r"(?i)^plat[ií]\s+od", t):
                break

            # Usually PyMuPDF exposes one stop per text row. Bus PDFs may expose
            # a whole stop chain in one row separated by private-use symbol glyphs.
            pieces = split_symbol_line(stripped)
            good = [p for p in pieces if looks_like_stop(p)]
            if len(good) > 1:
                seq.extend(good)
            elif looks_like_stop(t):
                seq.append(t)

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
            debug.append({"page": pno + 1, "plain_text": plain, "candidate_sequences": page_sequences})
    sequences = dedupe_sequences(raw_sequences)
    if debug_path is not None:
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")
    return sequences


def classify_patterns(sequences: list[list[str]]) -> tuple[bool, list[dict]]:
    endpoints = {(fold(s[0]), fold(s[-1])) for s in sequences if s}
    reverse_pair = any((b, a) in endpoints for a, b in endpoints)
    has_variants = len(sequences) != 2 or not reverse_pair
    patterns = []
    for idx, seq in enumerate(sequences, start=1):
        patterns.append({
            "id": f"p{idx}",
            "from": seq[0],
            "to": seq[-1],
            "stops": seq,
        })
    return has_variants, patterns


def validate(line: str, sequences: list[list[str]]) -> dict:
    warnings = []
    if not sequences:
        warnings.append("no stop sequences extracted")
    if len(sequences) < 2:
        warnings.append("only one route direction/variant extracted")
    for i, s in enumerate(sequences):
        if len(s) < 5:
            warnings.append(f"sequence {i+1} too short ({len(s)} stops)")
        elif len(s) < 8:
            warnings.append(f"sequence {i+1} unusually short ({len(s)} stops)")
        if len(s) != len(set(map(fold, s))):
            warnings.append(f"sequence {i+1} contains duplicate stop names")
    endpoints = {(fold(s[0]), fold(s[-1])) for s in sequences if s}
    reverse_pair = any((b, a) in endpoints for a, b in endpoints)
    if len(sequences) >= 2 and not reverse_pair:
        warnings.append("no exact reverse endpoint pair; treated as route variants")
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
    ap.add_argument("--mode", choices=MODE_CONFIG, required=True)
    ap.add_argument("--effective-date")
    ap.add_argument("--latest-published", action="store_true")
    ap.add_argument("--output", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--cache-dir", default=".cache/dpo-pdf")
    ap.add_argument("--debug-dir", default=None)
    args = ap.parse_args()

    eff = dt.date.fromisoformat(args.effective_date) if args.effective_date else None
    cfg = MODE_CONFIG[args.mode]
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    schedules = fetch_index(session, cfg["index"])
    if not schedules:
        raise SystemExit(f"No DPO {args.mode} timetables found on index page.")
    chosen = choose_schedule_set(schedules, eff, args.latest_published)

    data = {
        "mode": args.mode,
        "source": cfg["index"],
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "requestedEffectiveDate": eff.isoformat() if eff else None,
        "latestPublished": args.latest_published,
        "lines": {},
    }
    report = []

    for s in chosen:
        try:
            pdf = download_pdf(session, s, Path(args.cache_dir) / args.mode)
            dbg = Path(args.debug_dir) / args.mode / f"line-{s.line}.json" if args.debug_dir else None
            seqs = parse_pdf(pdf, s.line, dbg)
            has_variants, patterns = classify_patterns(seqs)
            data["lines"][s.line] = {
                "validFrom": s.valid_from.isoformat(),
                "routeLabel": s.route_label,
                "sourcePdf": s.pdf_url,
                "hasVariants": has_variants,
                "patterns": patterns,
                # compatibility alias for the PWA layer
                "directions": patterns,
            }
            v = validate(s.line, seqs)
            v.update({"sourcePdf": s.pdf_url, "validFrom": s.valid_from.isoformat(), "hasVariants": has_variants})
            report.append(v)
            print(f"{s.line:>4}: {len(seqs)} pattern(s), {[len(x) for x in seqs]} stops {'OK' if v['ok'] else 'FAIL'}")
            for warning in v["warnings"]:
                print(f"      warning: {warning}")
        except Exception as e:
            report.append({"ok": False, "line": s.line, "validFrom": s.valid_from.isoformat(), "sourcePdf": s.pdf_url, "error": repr(e)})
            print(f"{s.line:>4}: ERROR {e}", file=sys.stderr)

    Path(args.output).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for r in report if r.get("ok"))
    print(f"\n{args.mode}: {ok}/{len(report)} lines parsed without fatal error.")
    return 0 if ok == len(report) else 2


if __name__ == "__main__":
    raise SystemExit(main())

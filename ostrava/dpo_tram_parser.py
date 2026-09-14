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
from typing import Iterable
from urllib.parse import urljoin

import fitz
import requests
from bs4 import BeautifulSoup

INDEX_URL = "https://www.dpo.cz/jizdni-rady/jr-tram.html"
UA = "Mozilla/5.0 (compatible; DPO timetable parser/1.0)"
ICON_CHARS = set("")
NOISE_WORDS = {
    "zóna", "zona", "název", "nazev", "zastávky", "zastavky", "min",
    "platí", "plati", "od", "www.dpo.cz", "upraveno", "pracovní", "pracovni",
    "den", "sobota+neděle", "celý", "cely", "týden", "tyden", "poznámky", "poznamky",
}

@dataclass
class Schedule:
    line: str
    route_label: str
    valid_from: dt.date
    pdf_url: str


def clean_space(s: str) -> str:
    s = s.replace("\xa0", " ")
    s = "".join(ch for ch in s if ch not in ICON_CHARS)
    return re.sub(r"\s+", " ", s).strip()


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.casefold()


def is_noise(s: str) -> bool:
    f = fold(clean_space(s))
    if not f or f in NOISE_WORDS:
        return True
    if re.fullmatch(r"[\d\s\-–—./:+]+", f):
        return True
    if f.startswith("plati od ") or f.startswith("www.dpo.cz") or f.startswith("upraveno"):
        return True
    if "bezbarier" in f or "prestup na zeleznicni" in f:
        return True
    return False


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

        texts = []
        pdf_href = None
        node = heading
        for _ in range(12):
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
                if href and href.lower().endswith(".pdf"):
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


def _words_by_lines(page: fitz.Page):
    rows = defaultdict(list)
    for w in page.get_text("words"):
        rows[(w[5], w[6])].append(w)
    packed = []
    for ws in rows.values():
        ws.sort(key=lambda w: w[0])
        text = clean_space(" ".join(w[4] for w in ws))
        packed.append((min(w[1] for w in ws), min(w[0] for w in ws), max(w[2] for w in ws), max(w[3] for w in ws), text, ws))
    packed.sort(key=lambda r: (r[0], r[1]))
    return packed


def _extract_stop_columns(page: fitz.Page) -> list[list[str]]:
    words = page.get_text("words")
    if not words:
        return []

    headers = []
    for w in words:
        if fold(w[4]) == "nazev":
            neighbors = [q for q in words if abs(q[1] - w[1]) < 5 and 0 < q[0] - w[0] < 140]
            if any(fold(q[4]).startswith("zastav") for q in neighbors):
                headers.append((w[0], w[1], w[2]))

    if not headers:
        for y0, x0, x1, y1, text, _ in _words_by_lines(page):
            if "nazev zastavky" in fold(text):
                headers.append((x0, y0, x1))

    columns = []
    page_width = page.rect.width

    for hx0, hy, _ in headers:
        left = max(0, hx0 - 15)
        right = min(page_width, hx0 + 230)
        candidates = [w for w in words if w[1] > hy + 8 and left <= w[0] <= right and clean_space(w[4])]
        if not candidates:
            continue

        candidates.sort(key=lambda w: (w[1], w[0]))
        by_y = []
        current = []
        cy = None
        for w in candidates:
            if cy is None or abs(w[1] - cy) <= 3.0:
                current.append(w)
                cy = w[1] if cy is None else (cy + w[1]) / 2
            else:
                by_y.append(current)
                current = [w]
                cy = w[1]
        if current:
            by_y.append(current)

        stops = []
        for row in by_y:
            row.sort(key=lambda w: w[0])
            text = clean_space(" ".join(w[4] for w in row))
            if re.search(r"plat[ií]\s+od", text, re.I):
                break
            if is_noise(text):
                continue
            f = fold(text)
            if re.fullmatch(r"\d{1,3}", text):
                continue
            if f.startswith("poznam"):
                break
            if any(x in f for x in ("pracovni den", "sobota", "nedele", "cely tyden")):
                continue
            if len(text) >= 2:
                stops.append(text)

        merged = []
        i = 0
        while i < len(stops):
            cur = stops[i]
            if i + 1 < len(stops):
                nxt = stops[i + 1]
                if (cur.endswith(".") or len(cur) <= 12) and len(nxt) <= 20 and not any(ch.isdigit() for ch in nxt) and nxt[:1].isupper():
                    cur = f"{cur} {nxt}"
                    i += 1
            merged.append(cur)
            i += 1

        if len(merged) >= 3:
            columns.append(merged)
    return columns


def normalize_sequence(seq: list[str]) -> list[str]:
    out = []
    for s in seq:
        s = clean_space(s)
        s = re.sub(r"^[A-Z]\s*-\s*", "", s)
        s = re.sub(r"\s+[A-Z]$", "", s)
        if is_noise(s):
            continue
        if out and fold(out[-1]) == fold(s):
            continue
        out.append(s)
    return out


def dedupe_sequences(sequences: Iterable[list[str]]) -> list[list[str]]:
    unique = []
    seen = set()
    for seq in sequences:
        seq = normalize_sequence(seq)
        if len(seq) < 3:
            continue
        key = tuple(fold(x) for x in seq)
        if key not in seen:
            seen.add(key)
            unique.append(seq)

    keep = []
    keys = [tuple(fold(x) for x in s) for s in unique]
    for i, seq in enumerate(unique):
        k = keys[i]
        subset = False
        for j, other in enumerate(keys):
            if i == j or len(other) <= len(k):
                continue
            if any(other[start:start + len(k)] == k for start in range(len(other) - len(k) + 1)):
                subset = True
                break
        if not subset:
            keep.append(seq)
    return keep


def parse_pdf(pdf_path: Path, debug_path: Path | None = None) -> list[list[str]]:
    doc = fitz.open(pdf_path)
    sequences = []
    debug = []
    for pno, page in enumerate(doc):
        cols = _extract_stop_columns(page)
        sequences.extend(cols)
        if debug_path is not None:
            debug.append({"page": pno + 1, "plain_text": page.get_text("text"), "candidate_columns": cols})
    sequences = dedupe_sequences(sequences)
    if debug_path is not None:
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_text(json.dumps(debug, ensure_ascii=False, indent=2), encoding="utf-8")
    return sequences


def endpoints_from_label(label: str) -> list[str]:
    if not label:
        return []
    return [clean_space(p) for p in re.split(r"\s+[–-]\s+|\s+/\s+", label) if clean_space(p)]


def validate(line: str, route_label: str, sequences: list[list[str]]) -> dict:
    warnings = []
    if not sequences:
        warnings.append("no stop sequences extracted")
    for i, s in enumerate(sequences):
        if len(s) < 5:
            warnings.append(f"sequence {i+1} suspiciously short ({len(s)} stops)")
    expected = endpoints_from_label(route_label)
    observed_ends = {fold(s[0]) for s in sequences if s} | {fold(s[-1]) for s in sequences if s}
    unmatched = [e for e in expected if fold(e) not in observed_ends]
    if unmatched:
        warnings.append("route-label endpoints not seen at extracted sequence ends: " + ", ".join(unmatched))
    return {
        "ok": bool(sequences) and not any("no stop" in w for w in warnings),
        "line": line,
        "route_label": route_label,
        "sequence_count": len(sequences),
        "stop_counts": [len(s) for s in sequences],
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
            seqs = parse_pdf(pdf, dbg)
            data["tram"][s.line] = {
                "validFrom": s.valid_from.isoformat(),
                "routeLabel": s.route_label,
                "sourcePdf": s.pdf_url,
                "directions": [{"from": seq[0], "to": seq[-1], "stops": seq} for seq in seqs],
            }
            v = validate(s.line, s.route_label, seqs)
            v.update({"sourcePdf": s.pdf_url, "validFrom": s.valid_from.isoformat()})
            report.append(v)
            print(f"{s.line:>3}: {len(seqs)} sequence(s), {[len(x) for x in seqs]} stops {'OK' if v['ok'] else 'FAIL'}")
        except Exception as e:
            report.append({
                "ok": False,
                "line": s.line,
                "route_label": s.route_label,
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

#!/usr/bin/env python3
"""Fail packaged Kibana/ES|QL that can hang Elasticsearch.

This is a query-shape gate for any integration (logs, metrics, API, traces).
It does not require syslog, PAM, or a 1-hour dashboard.

Usage:
  python3 production_ship_gate.py <package-dir-or-kibana-dir>

Exit 0 = PASS (warnings allowed). Exit 1 = do not zip.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

VALUES_ROW = re.compile(r"VALUES\s*\(\s*row\s*\)", re.I)
VALUES_CONCAT = re.compile(r"VALUES\s*\(\s*CONCAT\s*\(", re.I)
METADATA_ID = re.compile(r"METADATA\s+_id\b", re.I)
MV_EXPAND_EVENTS = re.compile(r"MV_EXPAND\s+events\b", re.I)
FROM_ALL_LOGS = re.compile(r"\bFROM\s+logs-\*(?:\s|,|$)", re.I)
FROM_ALL_METRICS = re.compile(r"\bFROM\s+metrics-\*(?:\s|,|$)", re.I)
FROM_STAR = re.compile(r"\bFROM\s+\*(?:\s|,|$)", re.I)
FROM_CLAUSE = re.compile(r"\bFROM\s+([^\n|]+)", re.I)
CONCAT = re.compile(r"\bCONCAT\s*\(", re.I)
VALUES_ANY = re.compile(r"\bVALUES\s*\(", re.I)
KEEP_STAR = re.compile(r"\bKEEP\s+\*", re.I)
VERY_WIDE_TIME = re.compile(r"now-(7d|15d|30d|90d)\b")


def collect_text(path: Path) -> str:
    raw = path.read_text(errors="replace")
    chunks = [raw]
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    walk_strings(obj, chunks)
    return "\n".join(chunks)


def walk_strings(obj: object, chunks: list[str]) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            walk_strings(v, chunks)
    elif isinstance(obj, list):
        for v in obj:
            walk_strings(v, chunks)
    elif isinstance(obj, str):
        chunks.append(obj)
        s = obj.strip()
        if s[:1] in "{[":
            try:
                walk_strings(json.loads(s), chunks)
            except json.JSONDecodeError:
                pass


def from_index_count(text: str) -> int:
    n = 0
    for m in FROM_CLAUSE.finditer(text):
        clause = m.group(1)
        clause = re.split(r"\bMETADATA\b", clause, flags=re.I)[0]
        parts = [p.strip() for p in clause.split(",") if p.strip()]
        n = max(n, len(parts))
    return n


def iter_scan_files(root: Path) -> list[Path]:
    kibana = root / "kibana" if (root / "kibana").is_dir() else root
    files: list[Path] = []
    for pattern in (
        "dashboard/*.json",
        "search/*.json",
        "visualization/*.json",
        "lens/*.json",
        "map/*.json",
        "security_rule/*.json",
        "*.ndjson",
        "import.ndjson",
    ):
        files.extend(kibana.glob(pattern))
    files.extend(root.glob("docs/*.ndjson"))
    files.extend(root.glob("docs/**/*.ndjson"))
    seen: set[Path] = set()
    out: list[Path] = []
    for p in files:
        if not p.is_file():
            continue
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        out.append(p)
    return out


def relpath(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def check_kibana(root: Path) -> tuple[list[str], list[str]]:
    fails: list[str] = []
    warns: list[str] = []
    for path in iter_scan_files(root):
        text = collect_text(path)
        rel = relpath(path, root)
        if VALUES_ROW.search(text) or VALUES_CONCAT.search(text):
            fails.append(f"{rel}: VALUES of a full/concatenated event — unbounded per bucket")
        if METADATA_ID.search(text):
            fails.append(f"{rel}: METADATA _id — do not rebuild hit lists in a packaged query")
        if MV_EXPAND_EVENTS.search(text):
            fails.append(f"{rel}: MV_EXPAND events — do not expand VALUES-packed events")
        if FROM_ALL_LOGS.search(text) or FROM_ALL_METRICS.search(text) or FROM_STAR.search(text):
            fails.append(f"{rel}: FROM logs-* / metrics-* / * — scope to the integration data stream")
        if KEEP_STAR.search(text):
            fails.append(f"{rel}: KEEP * — KEEP only fields needed for the agg/join")
        if CONCAT.search(text) and VALUES_ANY.search(text):
            fails.append(f"{rel}: CONCAT + VALUES — packing events into VALUES hangs the cluster")
        if from_index_count(text) >= 3:
            fails.append(f"{rel}: one ES|QL FROM lists ≥3 index patterns — split panels")
        if VERY_WIDE_TIME.search(text):
            warns.append(f"{rel}: packaged default is now-7d or wider — confirm this matches data volume")
    return fails, warns


def check_inputs(root: Path) -> list[str]:
    """Only when the stream actually has listen_* vars (tcp/udp/syslog)."""
    fails: list[str] = []
    for path in root.glob("data_stream/*/manifest.yml"):
        text = path.read_text(errors="replace")
        rel = relpath(path, root)
        if re.search(r"listen_address[\s\S]{0,240}default:\s*[\"']?(localhost|127\.0\.0\.1)", text):
            fails.append(f"{rel}: listen_address defaults to loopback — use 0.0.0.0 for remote senders")
        if re.search(r"name:\s*listen_port[\s\S]{0,120}default:\s*514\b", text):
            fails.append(f"{rel}: listen_port default 514 often collides with rsyslog — use a high port")
    return fails


def resolve_root(arg: Path) -> Path:
    if (arg / "manifest.yml").is_file() or (arg / "kibana").is_dir() or (arg / "data_stream").is_dir():
        return arg
    if arg.name == "kibana" or (arg / "dashboard").is_dir():
        return arg.parent if arg.name == "kibana" else arg
    return arg


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: production_ship_gate.py <package-dir>", file=sys.stderr)
        return 2
    root = resolve_root(Path(sys.argv[1]).resolve())
    if not root.exists():
        print(f"FAIL: path does not exist: {root}", file=sys.stderr)
        return 2

    fails, warns = check_kibana(root)
    fails.extend(check_inputs(root))
    print(f"production_ship_gate: {root}")
    for w in warns:
        print(f"  WARN: {w}")
    if fails:
        print("RESULT: FAIL")
        for f in fails:
            print(f"  - {f}")
        print("Do not zip. Fix query shape (see references/kibana-queries.md).")
        return 1
    print("RESULT: PASS")
    print("  no VALUES-of-event / MV_EXPAND-events / METADATA _id / FROM logs-*|metrics-*|*")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

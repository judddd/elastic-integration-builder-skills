#!/usr/bin/env python3
"""production_ship_gate.py: killer ES|QL FAILs; 24h metrics dashboard + safe query PASSes."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

GATE = Path(__file__).resolve().parent / "production_ship_gate.py"

KILLER = """FROM logs-system.auth-*, logs-system.security-*, logs-windows.security-*, logs-jumpserver.log-* METADATA _id
| EVAL row = CONCAT(host.name, user.name, source.ip)
| STATS events = VALUES(row) BY source.ip
| MV_EXPAND events"""

SAFE = """FROM logs-system.auth-*
| WHERE @timestamp >= ?_tstart AND @timestamp <= ?_tend
| KEEP @timestamp, host.name, user.name, source.ip, event.action
| STATS login_count = COUNT_DISTINCT(user.name), login_type = VALUES(event.action)
    BY ts = DATE_TRUNC(30 seconds, @timestamp), host.name, user.name, source.ip"""


def run_gate(pkg: Path) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(GATE), str(pkg)], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def write_pkg(query: str, time_from: str) -> Path:
    root = Path(tempfile.mkdtemp()) / "pkg"
    (root / "kibana" / "search").mkdir(parents=True)
    (root / "kibana" / "dashboard").mkdir(parents=True)
    (root / "kibana" / "search" / "q.json").write_text(
        json.dumps({"attributes": {"title": "q", "query": {"query": query, "language": "esql"}}})
    )
    (root / "kibana" / "dashboard" / "d.json").write_text(
        json.dumps(
            {
                "attributes": {
                    "title": "d",
                    "timeFrom": time_from,
                    "timeTo": "now",
                    "timeRestore": True,
                    "refreshInterval": {"pause": True, "value": 60000},
                    "panelsJSON": "[]",
                }
            }
        )
    )
    return root


def main() -> int:
    code, out = run_gate(write_pkg(KILLER, "now-1h"))
    assert code == 1, out
    for needle in ("VALUES", "METADATA _id", "MV_EXPAND", "CONCAT + VALUES"):
        assert needle in out, f"missing {needle} in:\n{out}"

    # Metrics-style 24h dashboard + safe query must PASS (not syslog-only 1h rule)
    code, out = run_gate(write_pkg(SAFE, "now-24h"))
    assert code == 0, out
    assert "RESULT: PASS" in out
    print("production_ship_gate tests ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

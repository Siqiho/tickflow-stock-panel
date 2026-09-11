#!/usr/bin/env python3
"""Read-only baseline SHA check + patch dry-apply onto copies (never main tree)."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

TASK = Path("/Users/simon/Trading/one-trading/docs/investigations/2026-09-07-industry-fflow-daily-roll")
REVIEW = TASK / "review"
SANDBOX = REVIEW / "patch-sandbox"
ONE = Path("/Users/simon/Trading/one-trading")

FILES = {
    "fund_flow.py": ONE / "backend/app/services/free_sources/fund_flow.py",
    "daily_pipeline.py": ONE / "backend/app/jobs/daily_pipeline.py",
    "SectorFundFlowPanel.tsx": ONE / "frontend/src/components/SectorFundFlowPanel.tsx",
    "api.ts": ONE / "frontend/src/lib/api.ts",
}
EXPECTED = {
    "fund_flow.py": "87ef39074dd2aae76f99b4c913b120c30947bf66f0ccca00722cdbce8a548e0b",
    "daily_pipeline.py": "7003b64ca634a230a588ffca43e3ddaba89529ce32e33ccecfdb600acd0bba58",
    "SectorFundFlowPanel.tsx": "4163d9f8c75e9f42d42c78e8f663de89bc351fe1945894a2e6550447343f31a8",
    "api.ts": "32055dd67d8065674d14d45554f4f1179dfcf2f8ac291fb9cbe55c2996cba957",
}
LOGS = {
    "data-platform-development-log.md": (
        ONE / "docs/data-platform-development-log.md",
        "f511f5090449add910068898caa2c8a5c804b61f70145b607383457d9cbe074b",
    ),
    "workbench-development-log.md": (
        ONE / "docs/workbench-development-log.md",
        "842c90d7894832f5e67ba87fdd849d9c97c9572d6bccf0bfec6d43bb1057e57f",
    ),
}
OVERLAY = {
    "fund_flow.py": TASK / "overlay/backend/app/services/free_sources/fund_flow.py",
    "daily_pipeline.py": TASK / "overlay/backend/app/jobs/daily_pipeline.py",
    "SectorFundFlowPanel.tsx": TASK / "overlay/frontend/src/components/SectorFundFlowPanel.tsx",
    "api.ts": TASK / "overlay/frontend/src/lib/api.ts",
}
PATCH = TASK / "patches/phase-b-industry-fflow-daily-roll.diff"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    lines: list[str] = []
    ok = True

    lines.append("=== four source files: disk vs baseline SHA ===")
    for name, path in FILES.items():
        actual = sha256(path)
        match = actual == EXPECTED[name]
        ok = ok and match
        lines.append(f"{name} match={match}")
        lines.append(f"  disk     {actual}")
        lines.append(f"  expected {EXPECTED[name]}")

    lines.append("\n=== official logs vs APPLY backup SHA (not source files) ===")
    for name, (path, expected) in LOGS.items():
        actual = sha256(path)
        lines.append(f"{name} match={actual == expected}")
        lines.append(f"  disk     {actual}")
        lines.append(f"  expected {expected}")

    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)
    sandbox_root = SANDBOX / "tree"
    for rel, src in {
        "backend/app/services/free_sources/fund_flow.py": FILES["fund_flow.py"],
        "backend/app/jobs/daily_pipeline.py": FILES["daily_pipeline.py"],
        "frontend/src/components/SectorFundFlowPanel.tsx": FILES["SectorFundFlowPanel.tsx"],
        "frontend/src/lib/api.ts": FILES["api.ts"],
    }.items():
        dest = sandbox_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    dry = subprocess.run(
        ["patch", "--dry-run", "-p1"],
        cwd=sandbox_root,
        input=PATCH.read_text(),
        text=True,
        capture_output=True,
    )
    lines.append("\n=== patch --dry-run on copies of current four files ===")
    lines.append(f"exit={dry.returncode}")
    lines.append((dry.stdout or "") + (dry.stderr or ""))
    ok = ok and dry.returncode == 0

    applied = subprocess.run(
        ["patch", "-p1"],
        cwd=sandbox_root,
        input=PATCH.read_text(),
        text=True,
        capture_output=True,
    )
    lines.append("=== patch apply on sandbox copies only ===")
    lines.append(f"exit={applied.returncode}")
    lines.append((applied.stdout or "") + (applied.stderr or ""))
    ok = ok and applied.returncode == 0

    lines.append("=== patched copies vs overlay ===")
    mapping = {
        "fund_flow.py": sandbox_root / "backend/app/services/free_sources/fund_flow.py",
        "daily_pipeline.py": sandbox_root / "backend/app/jobs/daily_pipeline.py",
        "SectorFundFlowPanel.tsx": sandbox_root / "frontend/src/components/SectorFundFlowPanel.tsx",
        "api.ts": sandbox_root / "frontend/src/lib/api.ts",
    }
    for name, patched in mapping.items():
        same = sha256(patched) == sha256(OVERLAY[name])
        ok = ok and same
        lines.append(f"{name} patched==overlay {same}")

    text = "\n".join(lines) + "\n"
    out = REVIEW / "results" / "baseline-and-patch.txt"
    out.write_text(text)
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Verify six-file disk baselines and patch apply/reverse on copies only."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

TASK = Path("/Users/simon/Trading/one-trading/docs/investigations/2026-09-07-industry-fflow-daily-roll")
REVIEW = TASK / "review" / "round2"
SANDBOX = REVIEW / "patch-sandbox"
ONE = Path("/Users/simon/Trading/one-trading")
PATCH = TASK / "patches/phase-b-industry-fflow-daily-roll.diff"

FILES = {
    "fund_flow.py": (
        ONE / "backend/app/services/free_sources/fund_flow.py",
        TASK / "overlay/backend/app/services/free_sources/fund_flow.py",
        "87ef39074dd2aae76f99b4c913b120c30947bf66f0ccca00722cdbce8a548e0b",
        "backend/app/services/free_sources/fund_flow.py",
    ),
    "daily_pipeline.py": (
        ONE / "backend/app/jobs/daily_pipeline.py",
        TASK / "overlay/backend/app/jobs/daily_pipeline.py",
        "7003b64ca634a230a588ffca43e3ddaba89529ce32e33ccecfdb600acd0bba58",
        "backend/app/jobs/daily_pipeline.py",
    ),
    "pipeline.py": (
        ONE / "backend/app/api/pipeline.py",
        TASK / "overlay/backend/app/api/pipeline.py",
        "af18dda3422879dfdaea4b251cd7257cd506dec6267a9e058325f6391686ed70",
        "backend/app/api/pipeline.py",
    ),
    "ext_data.py": (
        ONE / "backend/app/services/ext_data.py",
        TASK / "overlay/backend/app/services/ext_data.py",
        "3b0e5b43b1c54c39b62ffea9a0b5871fb5c2d318d755876ba137dbeb106a8137",
        "backend/app/services/ext_data.py",
    ),
    "SectorFundFlowPanel.tsx": (
        ONE / "frontend/src/components/SectorFundFlowPanel.tsx",
        TASK / "overlay/frontend/src/components/SectorFundFlowPanel.tsx",
        "4163d9f8c75e9f42d42c78e8f663de89bc351fe1945894a2e6550447343f31a8",
        "frontend/src/components/SectorFundFlowPanel.tsx",
    ),
    "api.ts": (
        ONE / "frontend/src/lib/api.ts",
        TASK / "overlay/frontend/src/lib/api.ts",
        "32055dd67d8065674d14d45554f4f1179dfcf2f8ac291fb9cbe55c2996cba957",
        "frontend/src/lib/api.ts",
    ),
}
HUNK = "\n# ROUND2_UNRELATED_HUNK_KEEP_ON_REVERSE\n"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def run_patch(cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["patch", *args],
        cwd=cwd,
        input=PATCH.read_text(),
        text=True,
        capture_output=True,
    )


def main() -> int:
    lines: list[str] = []
    ok = True
    lines.append("=== six target files: disk vs baseline SHA ===")
    for name, (disk, _overlay, expected, _rel) in FILES.items():
        actual = sha256(disk)
        match = actual == expected
        ok = ok and match
        lines.append(f"{name} match={match}")
        lines.append(f"  disk     {actual}")
        lines.append(f"  expected {expected}")

    api_v02_disk = ONE / "frontend/src/lib/api-v02.ts"
    api_v02_base = TASK / "baseline/api-v02.ts"
    api_v02_over = TASK / "overlay/frontend/src/lib/api-v02.ts"
    lines.append("\n=== api-v02 (not in patch) ===")
    lines.append(f"disk==baseline {sha256(api_v02_disk) == sha256(api_v02_base)}")
    lines.append(f"overlay==baseline {sha256(api_v02_over) == sha256(api_v02_base)}")
    lines.append(f"disk==overlay {sha256(api_v02_disk) == sha256(api_v02_over)}")

    patch_text = PATCH.read_text()
    lines.append("\n=== patch markers ===")
    for token in ("INDUSTRY_FFLOW_WINDOW_CONTRACT", "pytest", "__test__", "TEST_ONLY", "round2"):
        lines.append(f"contains {token!r}: {token in patch_text}")

    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)
    tree = SANDBOX / "tree"
    for _name, (disk, _overlay, _expected, rel) in FILES.items():
        dest = tree / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(disk, dest)

    dry = run_patch(tree, ["--dry-run", "-p1"])
    lines.append("\n=== dry-run apply ===")
    lines.append(f"exit={dry.returncode}")
    lines.append((dry.stdout or "") + (dry.stderr or ""))
    ok = ok and dry.returncode == 0

    applied = run_patch(tree, ["-p1"])
    lines.append("=== apply on copies ===")
    lines.append(f"exit={applied.returncode}")
    lines.append((applied.stdout or "") + (applied.stderr or ""))
    ok = ok and applied.returncode == 0

    lines.append("=== patched copies vs overlay ===")
    for name, (_disk, overlay, _expected, rel) in FILES.items():
        same = sha256(tree / rel) == sha256(overlay)
        ok = ok and same
        lines.append(f"{name} patched==overlay {same}")

    extra = tree / "backend/app/services/ext_data.py"
    extra.write_text(extra.read_text() + HUNK)
    rev_dry = run_patch(tree, ["--dry-run", "-R", "-p1"])
    lines.append("\n=== reverse dry-run with unrelated hunk ===")
    lines.append(f"exit={rev_dry.returncode}")
    lines.append((rev_dry.stdout or "") + (rev_dry.stderr or ""))
    ok = ok and rev_dry.returncode == 0

    reversed_p = run_patch(tree, ["-R", "-p1"])
    lines.append("=== reverse apply ===")
    lines.append(f"exit={reversed_p.returncode}")
    lines.append((reversed_p.stdout or "") + (reversed_p.stderr or ""))
    ok = ok and reversed_p.returncode == 0

    lines.append("=== after reverse: originals restored except extra hunk ===")
    for name, (disk, _overlay, _expected, rel) in FILES.items():
        copy = tree / rel
        if name == "ext_data.py":
            restored = copy.read_text() == disk.read_text() + HUNK
            kept = HUNK.strip() in copy.read_text()
            ok = ok and restored and kept
            lines.append(f"{name} baseline+hunk={restored} hunk_kept={kept}")
        else:
            same = sha256(copy) == sha256(disk)
            ok = ok and same
            lines.append(f"{name} back_to_disk {same}")

    text = "\n".join(lines) + "\n"
    out = REVIEW / "results" / "six-files-and-patch.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

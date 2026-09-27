"""Generate a leaderboard strata file (abrupt vs. gradual sheet switches) from an abruptness-exploration
results JSON, reusing that exploration's own sheet-frame classification -- no re-derivation, no
approximation.

In plain English: some sheet switches are sudden (the trace jumps sideways in one step); others are
gradual (it drifts over many steps). "Strata" here means splitting the corpus's confirmed events into
those two groups so a leaderboard can show a detector's recall on each separately. The grouping itself
was already worked out, event by event, by the exploratory abruptness study
(tools/switchbench/explore_abruptness.py, field `abrupt_primary_sf`: the event's maximum single-step
offset **measured in the sheet's own local frame**, thresholded at ABRUPT_VX = 8.0 voxels -- see that
module's `event_level()`); this script only reads that field back out and reshapes it into the format
`tools.switchbench_kit.leaderboard` expects.

    python -m tools.switchbench_kit.strata_gen --explore results/switchbench_explore.json \
        --out strata.json

Output: {"<patch>|<x>,<y>,<z>": "abrupt" | "gradual", ...}, one entry per confirmed event that has a
sheet-frame classification (xyz rounded to 0.1 voxel, matching leaderboard.strata_recall's own key
rounding, so every entry matches).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FIELD = "abrupt_primary_sf"  # tools.switchbench.explore_abruptness.event_level: sheet-frame abruptness


def _key(patch: str, xyz) -> str:
    return f"{patch}|" + ",".join(f"{round(v, 1):.1f}" for v in xyz)


def build(explore: dict) -> dict:
    per_event = explore.get("results", {}).get("per_event")
    if per_event is None:
        raise ValueError("expected results.per_event in the exploration JSON (explore_abruptness.py stage 'report')")
    strata = {}
    skipped = 0
    for r in per_event:
        flag = r.get(FIELD)
        if flag is None:
            skipped += 1
            continue
        strata[_key(r["patch"], r["xyz"])] = "abrupt" if flag else "gradual"
    return strata, skipped


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--explore", required=True, help="switchbench_explore.json (or a v1-run equivalent with the "
                    "same results.per_event.abrupt_primary_sf field)")
    ap.add_argument("--out", required=True, help="strata JSON to write")
    a = ap.parse_args(argv)

    explore = json.loads(Path(a.explore).read_text())
    strata, skipped = build(explore)
    n_abrupt = sum(1 for v in strata.values() if v == "abrupt")
    n_gradual = sum(1 for v in strata.values() if v == "gradual")
    Path(a.out).write_text(json.dumps(strata, indent=1, sort_keys=True) + "\n")
    print(f"wrote {a.out}: {n_abrupt} abrupt, {n_gradual} gradual"
          + (f" ({skipped} event(s) with no {FIELD}, skipped)" if skipped else ""), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

import os
"""seamcheck (hwkim3330/seamcheck @6d6bc2d) on one tifxyz patch, default parameters (secondary detector,
added after the v1 freeze on Scout Report #8; reported in C2 only, never in C1).

Run with seamcheck's own interpreter:
  $SWITCHBENCH_EXT (default ./ext)/seamcheck/.venv/bin/python seamcheck_run.py <patch_dir> <out_json>

seamcheck.py: neighbour-step test (steps > 5x the patch median are flagged; verdict REVIEW / WATCH / OK,
SPARSE = no verdict below 50% grid coverage). Its `spots` list is capped at 40; the complete flagged set
is recomputed here with the tool's own neighbour_steps() and its default threshold (k_flag = 5), and
the capped spots must be a subset of it. Its companion winding check (seamcheck's windcheck.py) returns
a patch-level verdict only (no locations) and is recorded as such. Numeric output only.
"""
import json
import sys

import numpy as np

sys.path.insert(0, os.environ.get("SWITCHBENCH_EXT", "ext") + "/seamcheck")
import seamcheck as sc  # noqa: E402
import windcheck as scw  # noqa: E402  (seamcheck's winding check, not joe-carr-data/windcheck)

K_FLAG = 5.0  # seamcheck.check default


def main(d, out):
    P, valid = sc.load_xyz(d)
    r = sc.check(P, valid)
    v = sc.verdict(r)
    full = []
    for axis, name in ((0, "v"), (1, "u")):
        dd, m = sc.neighbour_steps(P, valid, axis)
        if not m.any():
            continue
        med = float(np.median(dd[m]))
        hit = m & (dd > med * K_FLAG)
        for y, x in zip(*np.nonzero(hit)):
            y2, x2 = (y + 1, x) if axis == 0 else (y, x + 1)
            full.append(dict(axis=name, y=int(y), x=int(x), times=float(dd[y, x] / med),
                             xyz=((P[y, x] + P[y2, x2]) / 2).tolist()))
    spots = {(s["axis"], s["y"], s["x"]) for s in r["spots"]}
    assert spots <= {(s["axis"], s["y"], s["x"]) for s in full}, "capped spots not in the full flagged set"
    assert len(full) == r["flagged"], (len(full), r["flagged"])
    w = scw.check(P, valid)
    rec = dict(tool="seamcheck", commit="6d6bc2d", verdict=v, coverage=r["coverage"], ratio=r["ratio"],
               flagged=r["flagged"], severe=r["severe"], spots_capped=len(r["spots"]), flagged_steps=full,
               winding_verdict=scw.verdict(w), winding=w)
    json.dump(rec, open(out, "w"))


if __name__ == "__main__":
    main(*sys.argv[1:3])

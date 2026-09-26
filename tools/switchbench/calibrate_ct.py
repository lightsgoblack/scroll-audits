"""Validity of the CT adjacent-wrap rule, measured on human winding ladders (relative_windings.json).

Ladder points are human clicks on consecutive wraps (wind_a, wind_a + 1) along one line. Controls:
  adjacent  (w, w+1)          -> rule should PASS   (sensitivity)
  two-apart (w, w+2)          -> rule should FAIL   (false pass = a 2-wrap jump confirmed as 1)
  same-wrap (w, w + 0.4 gap)  -> rule should FAIL   (false pass = a duplicate trace confirmed as a switch)
This uses no unverified patch and no event, so it cannot tune the rule to the corpus.
Usage: python -m tools.switchbench.calibrate_ct [n_pairs]
"""
from __future__ import annotations

import json
import sys

import numpy as np

from . import confirm, geom

OUT = geom.REPO / "vault" / "results" / "switchbench_ct_calibration.json"
SEED = 20260925


def ladder_pairs():
    r = json.load(open(geom.DATA / "relative_windings.json"))["collections"]
    adj, two = [], []
    for c in r.values():
        pts = sorted(((p["wind_a"], np.array(p["p"], float)) for p in c["points"].values()), key=lambda x: x[0])
        for i in range(len(pts) - 1):
            if pts[i + 1][0] - pts[i][0] == 1:
                adj.append((pts[i][1], pts[i + 1][1]))
                if i + 2 < len(pts) and pts[i + 2][0] - pts[i][0] == 2:
                    two.append((pts[i][1], pts[i + 2][1], pts[i + 1][1]))
    return adj, two


def check(a, b, s=None):
    d = b - a
    L = float(np.linalg.norm(d))
    return confirm.event_profile_check(a, d / L, L, s if s is not None else L)


def main(n=150):
    rng = np.random.default_rng(SEED)
    adj, two = ladder_pairs()
    ia = rng.choice(len(adj), min(n, len(adj)), replace=False)
    it = rng.choice(len(two), min(n, len(two)), replace=False)
    res = {"adjacent": [], "two_apart": [], "same_wrap": []}
    for k, i in enumerate(ia):
        a, b = adj[i]
        ok, _ = check(a, b)
        res["adjacent"].append(ok)
        L = np.linalg.norm(b - a)
        ok2, _ = check(a, a + 0.4 * (b - a), s=L)  # a within-sheet offset of 0.4 spacing
        res["same_wrap"].append(ok2)
        if k % 25 == 0:
            print("adj", k, flush=True)
    for k, i in enumerate(it):
        a, c, b = two[i]
        s = float(min(np.linalg.norm(b - a), np.linalg.norm(c - b)))
        d = c - a
        L = float(np.linalg.norm(d))
        ok, _ = confirm.event_profile_check(a, d / L, L, s)
        res["two_apart"].append(ok)

    def rate(x):
        d = [v for v in x if v is not None]
        return dict(n=len(x), decided=len(d), pass_rate=(sum(d) / len(d)) if d else None)
    out = {k: rate(v) for k, v in res.items()}
    out["rule"] = dict(sigma=confirm.SIGMA, min_dark=confirm.MIN_DARK, end_zone=confirm.END_ZONE)
    out["source"] = "relative_windings.json ladders (human), seed 20260925"
    json.dump(out, open(OUT, "w"), indent=1)
    print(json.dumps(out))
    return out


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:]))

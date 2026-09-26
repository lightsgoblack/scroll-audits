"""Choose the CT adjacent-wrap rule parameters on human ladder controls only (no corpus data).

Profiles along ladder lines (relative_windings.json) are sampled once; rule variants are scored by
Youden-style margin = pass(adjacent) - max(pass(two-apart), pass(same-wrap)). Seeded (20260925).
Same-wrap control: from a - 0.2 d to a + 0.2 d around a human click a (both ends on one sheet).
"""
from __future__ import annotations

import itertools
import json

import numpy as np
from scipy.ndimage import gaussian_filter1d

from . import ct, geom
from .calibrate_ct import ladder_pairs

OUT = geom.REPO / "vault" / "results" / "switchbench_ct_calibration.json"


def runs(mask):
    out, i = [], 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j < len(mask) and mask[j]:
                j += 1
            out.append((i, j)); i = j
        else:
            i += 1
    return out


def rule(t, v, t0, t1, s, sigma, ez, min_dark, q, step=0.5):
    lo_t, hi_t = min(t0, t1), max(t0, t1)
    vs = gaussian_filter1d(v, sigma / step)
    lo, hi = np.percentile(vs, q), np.percentile(vs, 100 - q)
    if hi - lo < 15:
        return None
    thr = (lo + hi) / 2
    e = ez * s
    bl = vs[(t >= lo_t - e) & (t <= lo_t + e)].max() > thr
    bh = vs[(t >= hi_t - e) & (t <= hi_t + e)].max() > thr
    inside = (t >= lo_t) & (t <= hi_t)
    ti, vi = t[inside], vs[inside]
    dark = [(a, b) for a, b in runs(vi < thr) if (b - a) * step >= min_dark]
    mid = [(a, b) for a, b in runs(vi >= thr) if ti[a] > lo_t + e and ti[b - 1] < hi_t - e]
    return bool(bl and bh and len(dark) == 1 and not mid)


def main(n=150, level=2):
    ct.set_level(level)
    rng = np.random.default_rng(20260925)
    adj, two = ladder_pairs()
    two = [x for x in two]
    ia = rng.choice(len(adj), min(n, len(adj)), replace=False)
    it = rng.choice(len(two), min(n, len(two)), replace=False)
    prof = {"adjacent": [], "two_apart": [], "same_wrap": []}
    for i in ia:
        a, b = adj[i]
        d = b - a; L = float(np.linalg.norm(d)); u = d / L
        t = np.arange(-3 * L, 4 * L + 1e-9, 0.5)
        v = ct.sample(a[None] + t[:, None] * u[None])
        if np.isnan(v).mean() > 0.1:
            continue
        v = np.nan_to_num(v, nan=np.nanmedian(v))
        prof["adjacent"].append((t, v, 0.0, L, L))
        prof["same_wrap"].append((t, v, -0.2 * L, 0.2 * L, L))
    for i in it:
        a, c, b = two[i]
        s = float(min(np.linalg.norm(b - a), np.linalg.norm(c - b)))
        d = c - a; L = float(np.linalg.norm(d)); u = d / L
        t = np.arange(-3 * s, L + 3 * s + 1e-9, 0.5)
        v = ct.sample(a[None] + t[:, None] * u[None])
        if np.isnan(v).mean() > 0.1:
            continue
        v = np.nan_to_num(v, nan=np.nanmedian(v))
        prof["two_apart"].append((t, v, 0.0, L, s))
    grid = list(itertools.product([1.0, 1.5, 2.0, 3.0], [0.1, 0.15, 0.2, 0.3], [1.0, 2.0, 3.0], [10, 20, 30]))
    table = []
    for sigma, ez, md, q in grid:
        rates = {}
        for k, lst in prof.items():
            r = [rule(t, v, t0, t1, s, sigma, ez, md, q) for t, v, t0, t1, s in lst]
            d = [x for x in r if x is not None]
            rates[k] = sum(d) / len(d) if d else 0.0
        table.append(dict(sigma=sigma, end_zone=ez, min_dark=md, q=q, **rates,
                          margin=rates["adjacent"] - max(rates["two_apart"], rates["same_wrap"])))
    table.sort(key=lambda r: -r["margin"])
    out = dict(source="relative_windings.json ladders (human), seed 20260925",
               n={k: len(v) for k, v in prof.items()}, best=table[0], top10=table[:10],
               initial_rule=[r for r in table if r["sigma"] == 1.5 and r["end_zone"] == 0.3 and r["min_dark"] == 2.0 and r["q"] == 10])
    out["level"] = level
    grid_all = table
    out["grid_size"] = len(grid_all)
    if level == 2:
        json.dump(out, open(OUT, "w"), indent=1)
    else:
        j = json.load(open(OUT)); j[f"level{level}_trial"] = out; json.dump(j, open(OUT, "w"), indent=1)
    print(json.dumps(out["best"]), json.dumps(out["initial_rule"]))


if __name__ == "__main__":
    import sys
    main(*(int(a) for a in sys.argv[1:]))

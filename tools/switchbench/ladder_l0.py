"""SwitchBench v1: numeric CT profiles on human ladder controls (relative_windings.json) only.

No unverified patch, no event and no corpus data are read here (protocol P1 (prereg/switchbench_v1.md): rule constants are tuned
only on human ladder controls). Ladder collections are split by collection into a tuning half and a
held-out half (seed 20260925), so the reported ladder rates of the chosen rule are out-of-sample.

Controls (as v0 tune_ct.py):
  adjacent   (w, w+1) clicks a -> b, spacing s = |b - a|, ends t0=0, t1=s      -> rule should PASS
  same_sheet around click a: ends -0.2 s .. +0.2 s (one sheet)                 -> rule should FAIL
  two_apart  (w, w+2) clicks a -> c (b between), s = min(|b-a|, |c-b|)         -> rule should FAIL
Every profile is sampled once at level 0 (2.4 um, step 0.25 level-2 vx = 1 level-0 voxel) and once at
level 2 (9.6 um, step 0.5 vx, the v0 setting) over a range that covers the rule window
[min(t0,t1) - 3 s, max(t0,t1) + 3 s] of every control drawn from it. Output: data/switchbench_v1/
ladder_profiles.npz (numeric profiles only; no images).
Usage: python -m tools.switchbench.ladder_l0 [threads]
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import geom
from .ct0 import Sampler

SEED = 20260925
V1 = geom.REPO / "data" / "switchbench_v1"
OUT = V1 / "ladder_profiles.npz"
STEP = {0: 0.25, 2: 0.5}


def controls():
    """Profiles to sample and controls drawn from them, split by ladder collection (seeded)."""
    r = json.load(open(geom.DATA / "relative_windings.json"))["collections"]
    cids = sorted(r)
    perm = np.random.default_rng(SEED).permutation(len(cids))
    split = {cids[i]: ("tune" if k < len(cids) // 2 else "test") for k, i in enumerate(perm)}
    profs, ctrls = [], []
    for cid in cids:
        pts = sorted(((p["wind_a"], np.array(p["p"], float)) for p in r[cid]["points"].values()),
                     key=lambda x: x[0])
        for i in range(len(pts) - 1):
            if pts[i + 1][0] - pts[i][0] != 1:
                continue
            a, b = pts[i][1], pts[i + 1][1]
            L = float(np.linalg.norm(b - a))
            if L < 1e-6:
                continue
            j = len(profs)
            profs.append(dict(coll=cid, split=split[cid], p0=a, d=(b - a) / L, t_lo=-3.2 * L, t_hi=4.0 * L))
            ctrls.append(dict(kind="adjacent", prof=j, t0=0.0, t1=L, s=L))
            ctrls.append(dict(kind="same_sheet", prof=j, t0=-0.2 * L, t1=0.2 * L, s=L))
            if i + 2 < len(pts) and pts[i + 2][0] - pts[i][0] == 2:
                c = pts[i + 2][1]
                s = float(min(L, np.linalg.norm(c - b)))
                Lc = float(np.linalg.norm(c - a))
                if Lc < 1e-6:
                    continue
                k = len(profs)
                profs.append(dict(coll=cid, split=split[cid], p0=a, d=(c - a) / Lc, t_lo=-3 * s, t_hi=Lc + 3 * s))
                ctrls.append(dict(kind="two_apart", prof=k, t0=0.0, t1=Lc, s=s))
    return profs, ctrls


def main(threads=4):
    V1.mkdir(parents=True, exist_ok=True)
    profs, ctrls = controls()
    print(f"{len(profs)} profiles, {len(ctrls)} controls", flush=True)
    samplers = {0: Sampler(0, max_chunks=400), 2: Sampler(2, max_chunks=200)}
    vals = {0: [None] * len(profs), 2: [None] * len(profs)}
    by_coll = {}
    for j, p in enumerate(profs):
        by_coll.setdefault(p["coll"], []).append(j)
    t_start = time.time()
    done = [0]

    def work(cid):
        for j in by_coll[cid]:
            p = profs[j]
            for lev in (0, 2):
                _, v = samplers[lev].profile(p["p0"], p["d"], p["t_lo"], p["t_hi"], STEP[lev])
                vals[lev][j] = v.astype(np.float32)
        done[0] += 1
        if done[0] % 20 == 0:
            s0 = samplers[0].stats
            print(f"  {done[0]}/{len(by_coll)} ladders, level-0 {s0['fetched']} chunks "
                  f"{s0['bytes']/1e9:.1f} GB, {time.time()-t_start:.0f}s", flush=True)

    with ThreadPoolExecutor(threads) as ex:
        list(ex.map(work, sorted(by_coll)))
    out = dict(
        coll=np.array([p["coll"] for p in profs]), split=np.array([p["split"] for p in profs]),
        p0=np.array([p["p0"] for p in profs]), d=np.array([p["d"] for p in profs]),
        t_lo=np.array([p["t_lo"] for p in profs]), t_hi=np.array([p["t_hi"] for p in profs]),
        c_kind=np.array([c["kind"] for c in ctrls]), c_prof=np.array([c["prof"] for c in ctrls]),
        c_t0=np.array([c["t0"] for c in ctrls]), c_t1=np.array([c["t1"] for c in ctrls]),
        c_s=np.array([c["s"] for c in ctrls]))
    for lev in (0, 2):
        off = np.cumsum([0] + [len(v) for v in vals[lev]])
        out[f"v{lev}"] = np.concatenate(vals[lev])
        out[f"off{lev}"] = off
        out[f"step{lev}"] = np.array(STEP[lev])
    np.savez_compressed(OUT, **out)
    print(json.dumps(dict(profiles=len(profs), controls=len(ctrls), elapsed_s=time.time() - t_start,
                          l0=samplers[0].stats, l2=samplers[2].stats)), flush=True)


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:]))

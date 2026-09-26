"""Pre-registered sanity checks for the SwitchBench-natural labeler (failure = harness bug).

S1  verified patch vs itself (itself in the reference set) = 0 events.
S2  synthetic one-wrap jump planted into a verified patch = exactly 1 event, at the planted place.
S3  labeler on verified patches (reference = all other verified, same-lineage excluded):
    > 5% of patches with events means the labeler is broken.
Usage: python -m tools.switchbench.sanity [n_s3]
"""
from __future__ import annotations

import json
import re
import sys
import time

import numpy as np

from . import geom, label
from .geom import MM

SEED = 20260925
OUT = geom.REPO / "vault" / "results" / "switchbench_sanity.json"


def lineage(name: str) -> str:
    m = re.match(r"^(auto_grown_\d+|auto_trace_\d+|auto_grown_w\d+)", name)
    if m:
        return m.group(1)
    return name.split("_sel_")[0]


def same_lineage(vi, name):
    key = lineage(name)
    return {n for n in vi.names if lineage(n) == key}


def run_patch(vi, P, N, exclude=(), pad=160.0):
    lo = np.nanmin(P.reshape(-1, 3), 0)
    hi = np.nanmax(P.reshape(-1, 3), 0)
    cl = vi.local_cloud(lo, hi, pad=pad, exclude=set(exclude))
    return label.label_patch(P, N, cl), cl


def s1(vi, names):
    res = []
    for nm in names:
        P, N, _ = vi.patch(nm)
        r, _ = run_patch(vi, P, N)
        res.append(dict(patch=nm, events=len(r["events"]), multi=len(r["multi"]),
                        assigned_frac=r["stats"]["n_assigned"] / max(1, r["stats"]["n_valid"])))
    return dict(passed=all(x["events"] == 0 for x in res), patches=res)


def plant(vi, nm):
    """Move the part of patch nm right of column c* onto the next outward verified sheet.

    Target offset per vertex = distance to the next outward sheet in its stack (gap within
    0.5-1.5 x spacing), median-smoothed over a 7x7 grid window so the planted part is one coherent
    surface; vertices whose own offset disagrees with the smoothed one by > 3 vx are dropped."""
    from scipy.ndimage import generic_filter
    P, N, _ = vi.patch(nm)
    H, W, _ = P.shape
    lo = np.nanmin(P.reshape(-1, 3), 0)
    hi = np.nanmax(P.reshape(-1, 3), 0)
    cl = vi.local_cloud(lo, hi, pad=160.0)
    st = label.stacks(P, N, cl)
    cstar = W // 2
    T = np.full((H, W), np.nan)
    for (r, c), s in st.items():
        if c < cstar:
            continue
        k, sp, d = label.assign(s)
        if k is None or k + 1 >= len(s):
            continue
        gap = s[k + 1]["t"] - s[k]["t"]
        if 0.5 * sp <= gap <= 1.5 * sp:
            T[r, c] = s[k + 1]["t"]
    Ts = generic_filter(T, np.nanmedian, size=7, mode="constant", cval=np.nan)
    moved = np.isfinite(T) & np.isfinite(Ts) & (np.abs(T - Ts) <= 3.0)
    Q = P.copy()
    Q[:, cstar:] = np.nan
    Q[moved] = P[moved] + Ts[moved][:, None] * N[moved]
    return Q, moved, cstar


def s2(vi, candidates, want=5):
    res = []
    for nm in candidates:
        P, N, _ = vi.patch(nm)
        if P.shape[1] < 30 or P.shape[0] < 5:
            continue
        Q, moved, cstar = plant(vi, nm)
        left = np.isfinite(P[:, :cstar]).all(-1)
        good = [moved[r, cstar:cstar + 12].all() and left[r, cstar - 12:].all() for r in range(P.shape[0])]
        # longest contiguous block of rows with a clean plant (>= 12 vertices, ~2.3 mm, each side)
        best, cur = (0, 0), None
        for r, g in enumerate(good + [False]):
            if g and cur is None:
                cur = r
            elif not g and cur is not None:
                if r - cur > best[1] - best[0]:
                    best = (cur, r)
                cur = None
        if best[1] - best[0] < 3:
            continue
        rows = list(range(*best))
        keep = np.zeros(P.shape[:2], bool)
        keep[rows, cstar - 12:cstar + 12] = True
        Q[~keep] = np.nan
        NQ = geom.orient_outward(Q, geom.grid_normals(Q))
        lo = np.nanmin(Q.reshape(-1, 3), 0)
        hi = np.nanmax(Q.reshape(-1, 3), 0)
        cl = vi.local_cloud(lo, hi, pad=160.0)
        r = label.label_patch(Q, NQ, cl)
        truth = np.nanmean(np.concatenate([Q[rows, cstar - 1], Q[rows, cstar]]), 0)
        ev = r["events"]
        dists = [float(np.linalg.norm(np.array(e["xyz"]) - truth) / MM) for e in ev]
        near_col = [all(abs(m["rc_a"][1] - (cstar - 1)) <= 2 and abs(m["rc_b"][1] - cstar) <= 2
                        for m in e["members"]) for e in ev]
        ok = len(ev) == 1 and near_col[0] and ev[0]["delta_signs"] == [1]
        res.append(dict(patch=nm, rows=[rows[0], rows[-1]], cstar=cstar, n_events=len(ev),
                        event_dist_mm=dists, at_planted_column=near_col,
                        delta_signs=[e["delta_signs"] for e in ev], multi=len(r["multi"]), passed=ok))
        if len(res) >= want:
            break
    return dict(passed=bool(res) and all(x["passed"] for x in res), n=len(res), cases=res)


def s3(vi, names):
    """Events on verified patches. An event needs two references (criteria), so the pass/fail count
    uses CT-confirmed events; the geometry-only (single-reference) rate is reported alongside."""
    from . import confirm
    res = []
    for nm in names:
        P, N, _ = vi.patch(nm)
        r, _ = run_patch(vi, P, N, exclude=same_lineage(vi, nm))
        conf = []
        for e in r["events"]:
            ok, det = confirm.confirm_event(P, N, e, r["stacks"], r["asg"])
            conf.append(ok)
        res.append(dict(patch=nm, events_geom=len(r["events"]), events_confirmed=sum(1 for c in conf if c),
                        events_contradicted=sum(1 for c in conf if c is False),
                        events_undecided=sum(1 for c in conf if c is None), multi=len(r["multi"]),
                        negatives=len(r["negatives"]), n_valid=r["stats"]["n_valid"],
                        n_assigned=r["stats"]["n_assigned"],
                        both_sides_1mm=[any(m["both_sides_1mm"] for m in e["members"]) for e in r["events"]],
                        event_xyz=[e["xyz"] for e in r["events"]]))
        print("  S3", nm, res[-1]["events_geom"], res[-1]["events_confirmed"], flush=True)
    ev = [x for x in res if x["n_assigned"] > 0]
    frac_c = sum(1 for x in ev if x["events_confirmed"] > 0) / max(1, len(ev))
    frac_g = sum(1 for x in ev if x["events_geom"] > 0) / max(1, len(ev))
    return dict(passed=frac_c <= 0.05, frac_with_confirmed_events=frac_c, frac_with_geometry_only_events=frac_g,
                n=len(res), n_evaluable=len(ev), patches=res)


def main(n3=100):
    t0 = time.time()
    vi = geom.VerifiedIndex()
    rng = np.random.default_rng(SEED)
    sizes = {p.split("/")[-2]: sz for p, sz in json.load(open(geom.DATA / "verified_files.json"))
             if p.endswith("/x.tif") and "/backups/" not in p}
    # keep patches up to 15k grid vertices (x.tif <= 60 kB) so a sanity pass stays within minutes
    order = [n for n in rng.permutation(vi.names) if sizes.get(n, 1e9) <= 60_000]
    out = {"seed": SEED}
    out["S1"] = s1(vi, order[:10])
    print("S1", out["S1"]["passed"], [x["events"] for x in out["S1"]["patches"]], flush=True)
    out["S2"] = s2(vi, order[10:400])
    print("S2", out["S2"]["passed"], [(c["n_events"], c["at_planted_column"], c["delta_signs"]) for c in out["S2"]["cases"]], flush=True)
    out["S3"] = s3(vi, order[400:400 + n3])
    print("S3", out["S3"]["passed"], out["S3"]["frac_with_confirmed_events"], out["S3"]["frac_with_geometry_only_events"], out["S3"]["n_evaluable"], flush=True)
    out["elapsed_s"] = time.time() - t0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    return out


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 100)

"""Score one detector's alarms on a SwitchBench corpus.

Rules (SwitchBench-natural v0: results md D10 and tools/switchbench/evaluate.py, reproduced exactly):
  hit     A confirmed event is hit if ANY alarm of its patch lies within match_mm (3D Euclidean) of
          any of its points: each transition point, and the event centre.
  FA      The patch's alarms are first de-duplicated greedily in input order (an alarm within
          fa_dedup_mm of an alarm already kept is dropped; v0 dedup_alarms / v1 fast_dedup). Every kept
          alarm within match_mm of a vertex of a confirmed negative run counts one false alarm for that
          run, unless it lies within match_mm of a point of ANY candidate event of the patch (confirmed
          or not). Rate = 100 x false alarms / summed length of confirmed negative runs (mm).
  verdict A scored patch absent from the alarms has no verdict: its events count as misses (as in v0)
          and it can raise no false alarm; coverage reports how much of the corpus had a verdict.
  cap     Optional per-patch cap N (v1): at most N confirmed events per patch count toward recall,
          picked by one RNG (seed) over patches sorted by name, events sorted by centre (v1 cap_selection).
  CIs     Wilson score 95% interval, and a patch-block bootstrap: resample the patches that carry
          counted events with replacement, B times, recall = pooled hits / pooled events per draw,
          2.5 and 97.5 percentiles (numpy linear). A fresh RNG seeded with `seed` per detector.
          False alarms per 100 mm get the same patch-block bootstrap treatment (same B, same seed,
          one block per scored patch), reported as false_alarms.bootstrap95 -- a separate RNG stream
          so it never perturbs a shared multi-detector recall bootstrap.
  scope   coverage.limited_scope is true when under half of scored patches got a verdict from the
          detector: a plain-English flag, not a penalty -- see the leaderboard's "limited scope" badge.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.spatial import cKDTree

from . import __version__
from .alarms import AlarmSet
from .corpus import CONFIRMED, Benchmark

DEFAULTS = dict(match_mm=1.0, per_patch_cap=None, bootstrap=2000, seed=20260925, fa_dedup_mm=0.5)
Z95 = 1.959963984540054


def resolve_settings(bench: Benchmark, **given) -> tuple[dict, dict]:
    """Effective settings and where each came from: argument > corpus 'scoring' block > kit default."""
    st, src = dict(DEFAULTS), {k: "kit default" for k in DEFAULTS}
    for k, v in bench.scoring_defaults.items():
        if k in st:
            st[k], src[k] = v, "corpus file"
    for k, v in given.items():
        if v is not None:
            st[k], src[k] = v, "argument"
    if st["per_patch_cap"] is not None and int(st["per_patch_cap"]) <= 0:
        st["per_patch_cap"] = None
    if st["per_patch_cap"] is not None:
        st["per_patch_cap"] = int(st["per_patch_cap"])
    st["match_mm"], st["fa_dedup_mm"] = float(st["match_mm"]), float(st["fa_dedup_mm"])
    st["bootstrap"], st["seed"] = int(st["bootstrap"]), int(st["seed"])
    if st["match_mm"] <= 0 or st["fa_dedup_mm"] < 0 or st["bootstrap"] < 0:
        raise ValueError("match_mm must be > 0, fa_dedup_mm >= 0 and bootstrap >= 0")
    return st, src


# ----------------------------------------------------------------------------- primitives
def wilson(k: int, n: int, z: float = Z95):
    """(p, lo, hi) Wilson score interval; (None, None, None) if n == 0 (v0 metrics.wilson)."""
    if n == 0:
        return (None, None, None)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (p, max(0.0, c - h), min(1.0, c + h))


def near(X: np.ndarray, A: np.ndarray, r_vx: float) -> np.ndarray:
    """Boolean per row of A: within r_vx voxels of any point of X (v0 evaluate.near)."""
    if len(X) == 0 or len(A) == 0:
        return np.zeros(len(A), bool)
    d, _ = cKDTree(X).query(A)
    return d <= r_vx


def dedup(A: np.ndarray, r_vx: float) -> np.ndarray:
    """Greedy de-duplication in input order: drop an alarm within r_vx of an alarm already kept.

    Same result as v0 evaluate.dedup_alarms (keep a iff norm(a - b) > r for every kept b), with a
    k-d tree for candidates; pairs within 1e-9 relative of the radius are decided by v0's own
    np.linalg.norm call, so the result is identical down to the last bit."""
    A = np.asarray(A, dtype=np.float64).reshape(-1, 3)
    if len(A) < 2 or r_vx <= 0:
        return A
    cand = cKDTree(A).query_ball_point(A, r_vx * (1 + 1e-9))
    dropped = np.zeros(len(A), bool)
    keep = []
    for i in range(len(A)):
        if dropped[i]:
            continue
        keep.append(i)
        js = np.array([j for j in cand[i] if j > i and not dropped[j]], dtype=np.int64)
        if not len(js):
            continue
        d = np.linalg.norm(A[js] - A[i], axis=1)
        close = d <= r_vx
        edge = np.abs(d - r_vx) <= 1e-9 * r_vx
        for k in np.nonzero(edge)[0]:
            close[k] = np.linalg.norm(A[js[k]] - A[i]) <= r_vx
        dropped[js[close]] = True
    return A[keep]


def patch_bootstrap(hits_by_patch: list, B: int, rng: np.random.Generator):
    """[lo, hi] 95% patch-block bootstrap of pooled recall (v0 report.py / v1 recall_stats).

    hits_by_patch: one list of booleans per patch, patches sorted by name."""
    n = len(hits_by_patch)
    if n == 0 or B == 0:
        return None
    vals = []
    for _ in range(B):
        pick = rng.choice(n, n, replace=True)
        h = [x for i in pick for x in hits_by_patch[i]]
        if h:
            vals.append(sum(h) / len(h))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if vals else None


def fa_bootstrap(fa_by_patch: list, mm_by_patch: list, B: int, rng: np.random.Generator):
    """[lo, hi] 95% patch-block bootstrap of pooled false alarms per 100 mm (red-team SHOULD FIX 4).

    Same block/B/seed convention as `patch_bootstrap`: resample patches with replacement B times and
    pool false_alarms / negative_mm per draw. `fa_by_patch` and `mm_by_patch` are one entry per patch
    (same patches, same order as `patch_bootstrap`'s recall blocks), so the two CIs are computed on
    the same patch-block structure even though they use independent RNG streams (this bootstrap never
    consumes from a shared multi-detector recall stream, so adding it changes no existing recall
    numbers). A resample with zero pooled negative_mm contributes no draw (undefined rate)."""
    n = len(fa_by_patch)
    if n == 0 or B == 0:
        return None
    vals = []
    for _ in range(B):
        pick = rng.choice(n, n, replace=True)
        fa = sum(fa_by_patch[i] for i in pick)
        mm = sum(mm_by_patch[i] for i in pick)
        if mm > 0:
            vals.append(100 * fa / mm)
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if vals else None


def cap_selection(bench: Benchmark, cap: int | None, seed: int):
    """Corpus indices of the confirmed events that count toward recall under a per-patch cap."""
    if cap is None:
        return None
    rng = np.random.default_rng(seed)
    sel = set()
    for p in bench.patches:
        conf = sorted([e for e in bench.events[p] if e.status == CONFIRMED], key=lambda e: tuple(e.centre.tolist()))
        if len(conf) > cap:
            sel |= {conf[j].index for j in sorted(rng.choice(len(conf), cap, replace=False).tolist())}
        else:
            sel |= {e.index for e in conf}
    return sel


def _valid_tree(bench: Benchmark, p: str) -> cKDTree:
    cache = bench.__dict__.setdefault("_valid_trees", {})
    if p not in cache:
        P = bench.geometry[p]
        cache[p] = cKDTree(P[np.isfinite(P).all(-1)])
    return cache[p]


# ----------------------------------------------------------------------------- scoring
def score(bench: Benchmark, alarms: AlarmSet, *, match_mm=None, per_patch_cap=None, bootstrap=None, seed=None,
          fa_dedup_mm=None, rng: np.random.Generator | None = None) -> dict:
    """Score an AlarmSet. Returns a JSON-ready dict (see README, 'Output').

    rng: optional Generator for the bootstrap (default: a fresh one seeded with `seed`); pass one
    shared Generator only to reproduce a multi-detector report that drew from a single stream."""
    st, src = resolve_settings(bench, match_mm=match_mm, per_patch_cap=per_patch_cap, bootstrap=bootstrap,
                               seed=seed, fa_dedup_mm=fa_dedup_mm)
    r_vx = st["match_mm"] * bench.mm
    dd_vx = st["fa_dedup_mm"] * bench.mm
    counted = cap_selection(bench, st["per_patch_cap"], st["seed"])
    ev_rows, patch_rows = [], []
    fa_total, neg_mm = 0, 0.0
    n_alarms = n_kept = off_surface = 0
    for p in bench.patches:
        A = alarms.by_patch.get(p)
        verdict = A is not None
        A = A if verdict else np.zeros((0, 3))
        Ad = dedup(A, dd_vx) if dd_vx > 0 else A
        n_alarms += len(A)
        n_kept += len(Ad)
        if len(A):
            d, _ = _valid_tree(bench, p).query(A)
            off_surface += int((d > r_vx).sum())
        evs = bench.events[p]
        all_ev = np.concatenate([e.points for e in evs]).reshape(-1, 3) if evs else np.zeros((0, 3))
        prow = dict(patch=p, verdict=verdict, alarms=int(len(A)), alarms_after_dedup=int(len(Ad)), events=0, hits=0,
                    negative_mm=0.0, false_alarms=0)
        for e in evs:
            if e.status != CONFIRMED:
                continue
            is_counted = counted is None or e.index in counted
            if len(A):
                d, _ = cKDTree(e.points).query(A)
                hit, nearest = bool((d <= r_vx).any()), float(d.min()) / bench.mm
            else:
                hit, nearest = False, None
            ev_rows.append(dict(event_index=e.index, patch=p, xyz=[round(float(v), 1) for v in e.centre],
                                transitions=e.n_transitions, counted=is_counted, verdict=verdict, hit=hit,
                                nearest_alarm_mm=nearest))
            if is_counted:
                prow["events"] += 1
                prow["hits"] += int(hit)
        for ng in bench.negatives[p]:
            if ng.status != CONFIRMED:
                continue
            if len(Ad):
                on_run = near(ng.verts, Ad, r_vx)
                off_ev = ~near(all_ev, Ad, r_vx) if len(all_ev) else np.ones(len(Ad), bool)
                k = int((on_run & off_ev).sum())
                prow["false_alarms"] += k
                fa_total += k
            neg_mm += ng.length_mm
            prow["negative_mm"] += ng.length_mm
        patch_rows.append(prow)

    rows = [x for x in ev_rows if x["counted"]]
    k, n = sum(x["hit"] for x in rows), len(rows)
    p_, lo, hi = wilson(k, n)
    pats = sorted({x["patch"] for x in rows})
    by = {q: [] for q in pats}
    for x in rows:
        by[x["patch"]].append(x["hit"])
    boot = patch_bootstrap([by[q] for q in pats], st["bootstrap"],
                           rng if rng is not None else np.random.default_rng(st["seed"]))
    # FA CI: same B, seed and one-block-per-patch convention as recall's bootstrap above, over every
    # scored patch (FA's natural domain -- not just patches carrying a counted event); a fresh RNG so
    # this never perturbs a shared multi-detector recall stream (see fa_bootstrap docstring).
    fa_boot = fa_bootstrap([q["false_alarms"] for q in patch_rows], [q["negative_mm"] for q in patch_rows],
                          st["bootstrap"], np.random.default_rng(st["seed"]))
    cov_rows = [x for x in rows if x["verdict"]]
    kc, nc = sum(x["hit"] for x in cov_rows), len(cov_rows)
    cov_mm = sum(x["negative_mm"] for x in patch_rows if x["verdict"])
    return dict(
        kit=dict(name="switchbench_kit", version=__version__),
        corpus=dict(path=str(bench.path), sha256=bench.sha256, scroll=bench.scroll, frame=bench.frame,
                    voxel_mm=bench.voxel_mm, patches_dir=str(bench.patches_dir), scored_patches=len(bench.patches),
                    confirmed_events=sum(1 for x in ev_rows), counted_events=n, event_patches=len(pats),
                    confirmed_negative_runs=sum(1 for q in bench.patches for g in bench.negatives[q] if g.status == CONFIRMED),
                    negative_mm=neg_mm, geometry_sha256=bench.geometry_sha256, geometry_check=bench.geometry_check),
        detector=dict(name=alarms.detector, source=alarms.source, sha256=alarms.sha256, format=alarms.format,
                      patches_in_input=alarms.n_in_input, patches_with_verdict=sum(1 for x in patch_rows if x["verdict"]),
                      alarms_on_scored_patches=n_alarms, alarms_after_dedup=n_kept, alarms_off_surface=off_surface,
                      dropped_invalid_vertices=alarms.dropped_invalid, unscored_patches_ignored=sorted(alarms.unscored),
                      unknown_patch_ids=sorted(alarms.unknown)),
        settings=dict(st, settings_source=src),
        recall=dict(hits=int(k), events=n, recall=p_, wilson95=[lo, hi], bootstrap95=boot, bootstrap_patches=len(pats)),
        false_alarms=dict(count=int(fa_total), negative_mm=neg_mm,
                          per_100mm=(100 * fa_total / neg_mm) if neg_mm else None,
                          bootstrap95=fa_boot, bootstrap_patches=len(patch_rows)),
        coverage=dict(patches=[sum(1 for x in patch_rows if x["verdict"]), len(patch_rows)], events=[nc, n],
                      negative_mm=[cov_mm, neg_mm],
                      recall_where_verdict=dict(hits=int(kc), events=nc, recall=(kc / nc) if nc else None),
                      limited_scope=(len(patch_rows) > 0 and
                                     sum(1 for x in patch_rows if x["verdict"]) / len(patch_rows) < 0.5)),
        events=ev_rows,
        patches=patch_rows,
    )

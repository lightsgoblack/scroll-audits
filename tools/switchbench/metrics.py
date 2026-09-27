"""Metrics for SwitchBench-natural (criteria: protocol A (prereg/switchbench_natural.md)).

Recall on confirmed natural events with 95% Wilson CI; false alarms per 100 mm on confirmed negative
runs; gap vs each tool's published planted recall; gen_avg_cost AUROC (event vs negative windows)
with a patch-block bootstrap (B = 2000, seed 20260925); random baseline.
An alarm matches an event if it lies within MATCH_MM (3D) of the event location.
"""
from __future__ import annotations

import json
import math

import numpy as np

from . import geom
from .geom import MM

MATCH_MM = 1.0
SEED = 20260925
B = 2000

# Published planted-switch recall, fixed before any detector output was read (see results md).
PUBLISHED = {
    "tifxyz-doctor": dict(value=124 / 128, text="124/128 abrupt 8-voxel normal-offset proxies (sealed holdout)",
                          source="https://github.com/aviad12g/tifxyz-doctor/blob/main/docs/reviewed-same-wrap-benchmark.md",
                          other="16 vx abrupt: 128/128; 8 vx over 4 cells: 0/128; 16 vx over 12 cells: 8/128 (all cues)"),
    "windcheck": dict(value=None, text="none published for the released self-crossing census",
                      source="https://github.com/joe-carr-data/windcheck/blob/main/docs/HISTORY.md (sec. 3.4: planted-defect "
                             "precision/recall belong to the retired proximity-era detector and are not release claims)"),
    "windaudit": dict(value=55 / 96, text="55/96 planted sheet switches raise an alarm (annotation corpus)",
                      source="https://github.com/sergeievland/windaudit/blob/main/README.md (sec. 4)"),
    "sheet-topo-bench": dict(value=0.667, text="frozen v1, switch family S, recall@N 0.667 [0.48-0.86] on held-out A (Paris 4 bands >= 100)",
                             source="https://github.com/tonclap/sheet-topo-bench/blob/main/pipeline/HELDOUT_RESULTS.md"),
}


def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return (None, None, None)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (p, max(0.0, c - h), min(1.0, c + h))


def cells_to_xyz(P, cells):
    out = []
    H, W, _ = P.shape
    for r, c in cells:
        # alarms are cells (quads) or vertices; use the mean of the valid corners
        pts = [P[rr, cc] for rr in (r, r + 1) for cc in (c, c + 1) if rr < H and cc < W and np.isfinite(P[rr, cc]).all()]
        if pts:
            out.append(np.mean(pts, 0))
    return np.array(out).reshape(-1, 3)


def auroc(pos, neg):
    pos = np.asarray(pos, float); neg = np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return None
    allv = np.concatenate([pos, neg])
    ranks = allv.argsort().argsort().astype(float)
    # average ranks for ties
    for v in np.unique(allv):
        m = allv == v
        if m.sum() > 1:
            ranks[m] = ranks[m].mean()
    rp = ranks[:len(pos)].sum()
    return float((rp - len(pos) * (len(pos) - 1) / 2) / (len(pos) * len(neg)))


def block_bootstrap_auroc(items, B=B, seed=SEED):
    """items: list of (patch, label, score). Resample patches with replacement."""
    rng = np.random.default_rng(seed)
    patches = sorted({p for p, _, _ in items})
    by = {p: [(l, s) for pp, l, s in items if pp == p] for p in patches}
    point = auroc([s for _, l, s in items if l == 1], [s for _, l, s in items if l == 0])
    vals = []
    for _ in range(B):
        pick = rng.choice(len(patches), len(patches), replace=True)
        pos, neg = [], []
        for i in pick:
            for l, s in by[patches[i]]:
                (pos if l == 1 else neg).append(s)
        a = auroc(pos, neg)
        if a is not None:
            vals.append(a)
    if not vals:
        return dict(point=point, lo=None, hi=None, n_boot=0)
    return dict(point=point, lo=float(np.percentile(vals, 2.5)), hi=float(np.percentile(vals, 97.5)), n_boot=len(vals))


def gen_estimate(P, seed):
    """Generation proxy: Euclidean distance to the GrowPatch seed / 20 vx grid step (validated on the
    verified full runs that ship generations.tif: Pearson 0.81-0.92)."""
    return np.linalg.norm(P - np.asarray(seed), axis=-1) / 20.0


def window_score(gac, gens):
    g = np.clip(np.round(gens).astype(int), 1, len(gac))
    return float(np.max(np.asarray(gac)[g - 1]))

"""Synthetic tifxyz patches and corpus files for the kit's unit tests (no scan data needed).

Patch "pA" is a flat 30 x 80 grid in the plane y = 2000 with a 20 voxel step:
    P[r, c] = (1000 + 20 c, 2000, 3000 + 20 r)
Its bottom-right corner (rows 26-29, cols 70-79) is masked out by mask.tif and vertex (0, 79) is -1.
Patch "pB" is a flat 60 x 20 grid in the plane x = 9000 carrying only a negative run.
Patch "pC" appears in the corpus with an unconfirmed event only (not scored).

Corpus (1 mm = 104.1667 voxels at 9.6 um):
  events[0]    pA confirmed     transition (5, 10) -> (5, 11): point (1210, 2000, 3100)
  events[1]    pA contradicted  transition (19, 40) -> (19, 41): point (1810, 2000, 3380), next to run 0
  events[2]    pC unconfirmed
  negatives[0] pA confirmed     row 20, cols 0-60: 1200 voxels = 11.52 mm, z = 3400
  negatives[1] pB confirmed     col 5, rows 0-59: 1180 voxels = 11.328 mm
  negatives[2] pA unconfirmed   row 22, cols 0-60 (never counted)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import tifffile

VX_MM = 0.0096


def grid_a():
    r, c = np.mgrid[0:30, 0:80].astype(np.float64)
    return np.stack([1000 + 20 * c, np.full_like(r, 2000.0), 3000 + 20 * r], -1)


def grid_b():
    r, c = np.mgrid[0:60, 0:20].astype(np.float64)
    return np.stack([np.full_like(r, 9000.0), 500 + 20 * c, 100 + 20 * r], -1)


def write_patch(d: Path, P: np.ndarray, mask: np.ndarray | None = None, minus_one=()):
    d.mkdir(parents=True, exist_ok=True)
    P = P.astype(np.float32).copy()
    for rc in minus_one:
        P[rc] = -1
    for i, f in enumerate(("x.tif", "y.tif", "z.tif")):
        tifffile.imwrite(d / f, np.ascontiguousarray(P[..., i]))
    if mask is not None:
        tifffile.imwrite(d / "mask.tif", mask.astype(np.uint8) * 255)


def mask_a():
    m = np.ones((30, 80), bool)
    m[26:30, 70:80] = False
    return m


def make_patches(root: Path) -> Path:
    write_patch(root / "pA", grid_a(), mask_a(), minus_one=[(0, 79)])
    write_patch(root / "pB", grid_b())
    write_patch(root / "pC", grid_b())
    return root


def _r1(v):
    return [round(float(x), 1) for x in v]


def corpus_dict(extra_events=(), scoring=None):
    A, B = grid_a(), grid_b()
    ev = [
        dict(patch="pA", status="confirmed", xyz=_r1((A[5, 10] + A[5, 11]) / 2), delta_signs=[1],
             transitions=[dict(axis="row", rc_a=[5, 10], rc_b=[5, 11], len_a_mm=1.5, len_b_mm=1.5)]),
        dict(patch="pA", status="contradicted", xyz=_r1((A[19, 40] + A[19, 41]) / 2), delta_signs=[1],
             transitions=[dict(axis="row", rc_a=[19, 40], rc_b=[19, 41], len_a_mm=1.5, len_b_mm=1.5)]),
        dict(patch="pC", status="unconfirmed", xyz=_r1((B[3, 3] + B[3, 4]) / 2), delta_signs=[1],
             transitions=[dict(axis="row", rc_a=[3, 3], rc_b=[3, 4], len_a_mm=1.5, len_b_mm=1.5)]),
    ] + list(extra_events)
    neg = [
        dict(patch="pA", status="confirmed", axis="row", rc0=[20, 0], rc1=[20, 60], len_mm=round(1200 * VX_MM, 2),
             xyz0=_r1(A[20, 0]), xyz1=_r1(A[20, 60])),
        dict(patch="pB", status="confirmed", axis="col", rc0=[0, 5], rc1=[59, 5], len_mm=round(1180 * VX_MM, 2),
             xyz0=_r1(B[0, 5]), xyz1=_r1(B[59, 5])),
        dict(patch="pA", status="unconfirmed", axis="row", rc0=[22, 0], rc1=[22, 60], len_mm=round(1200 * VX_MM, 2),
             xyz0=_r1(A[22, 0]), xyz1=_r1(A[22, 60])),
    ]
    d = dict(scroll="synthetic", frame="level-2 voxels (x, y, z), 9.6 um/vx", events=ev, negatives=neg, multi_wrap=[])
    if scoring is not None:
        d["scoring"] = scoring
    return d


def write_corpus(path: Path, **kw) -> Path:
    path.write_text(json.dumps(corpus_dict(**kw)))
    return path


def write_alarms(path: Path, obj) -> Path:
    path.write_text(json.dumps(obj))
    return path

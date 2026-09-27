"""Patch geometry for the SwitchBench scorer kit.

The corpus was labeled on tifxyz patches (x.tif, y.tif, z.tif and an optional mask.tif, one vertex
every 20 voxels). Every number the kit needs is recomputed from those grids with the exact arithmetic
the v0 labeler used, so scores are bit-identical to v0:

  load_tifxyz        = tools/switchbench/geom.py load_tifxyz (same invalid-vertex and mask rules)
  transition_point   = label.py: (P[rc_a] + P[rc_b]) / 2
  event centre       = label.py dedup(): mean of the event's transition points
  run length (mm)    = label.py _arc() / MM: summed 3D edge length along the run

Kept separate from tools/switchbench so the kit does not change when that package does; the
equivalence tests (tests/test_v0_equivalence.py) check that both give identical results.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import tifffile

VOXEL_MM = 0.0096          # level-2 voxel of PHercParis4 volume 20260411134726 (2.4 um x 4)
GRID_FILES = ("x.tif", "y.tif", "z.tif")
MASK_FILE = "mask.tif"


def vx_per_mm(voxel_mm: float = VOXEL_MM) -> float:
    """Voxels per mm, computed as v0 did (geom.MM = 1.0 / VOXEL_MM)."""
    return 1.0 / voxel_mm


def load_tifxyz(d: Path | str, use_mask: bool = True) -> np.ndarray:
    """(H, W, 3) float64 grid of (x, y, z) voxel coordinates; invalid vertices are NaN.

    A vertex is invalid if any coordinate is -1 or non-finite, if all three are <= 0, or if
    mask.tif (when present) is 0 there. A mask with a multiple of the grid shape is subsampled.
    """
    d = Path(d)
    x = tifffile.imread(d / "x.tif").astype(np.float64)
    y = tifffile.imread(d / "y.tif").astype(np.float64)
    z = tifffile.imread(d / "z.tif").astype(np.float64)
    P = np.stack([x, y, z], -1)
    bad = (x == -1) | (y == -1) | (z == -1) | ~np.isfinite(P).all(-1) | (x <= 0) & (y <= 0) & (z <= 0)
    m = d / MASK_FILE
    if use_mask and m.exists():
        mk = tifffile.imread(m)
        if mk.ndim == 3:
            mk = mk[..., 0]
        if mk.shape == x.shape:
            bad |= mk == 0
        elif mk.shape[0] % x.shape[0] == 0 and mk.shape[1] % x.shape[1] == 0:
            k0, k1 = mk.shape[0] // x.shape[0], mk.shape[1] // x.shape[1]
            bad |= mk[::k0, ::k1] == 0
    P[bad] = np.nan
    return P


def valid_mask(P: np.ndarray) -> np.ndarray:
    return np.isfinite(P).all(-1)


def transition_point(P: np.ndarray, rc_a, rc_b) -> np.ndarray:
    """Midpoint of the last vertex on the old wrap and the first vertex on the new wrap."""
    return (P[tuple(rc_a)] + P[tuple(rc_b)]) / 2


def event_points(P: np.ndarray, transitions) -> tuple[np.ndarray, np.ndarray]:
    """(points, centre): the event's transition points followed by their mean (v0 event_points)."""
    tp = [transition_point(P, t["rc_a"], t["rc_b"]).tolist() for t in transitions]
    centre = np.mean(tp, 0)
    return np.array(tp + [centre.tolist()]), centre


def run_vertices(axis: str, rc0, rc1) -> list[tuple[int, int]]:
    """Grid vertices of a negative run, from rc0 to rc1 inclusive, along one grid row or column."""
    (r0, c0), (r1, c1) = (int(v) for v in rc0), (int(v) for v in rc1)
    if axis == "row":
        if r0 != r1 or c1 < c0:
            raise ValueError(f"row run must keep its row and run left to right: {rc0} -> {rc1}")
        return [(r0, c) for c in range(c0, c1 + 1)]
    if axis == "col":
        if c0 != c1 or r1 < r0:
            raise ValueError(f"col run must keep its column and run top to bottom: {rc0} -> {rc1}")
        return [(r, c0) for r in range(r0, r1 + 1)]
    raise ValueError(f"axis must be 'row' or 'col', got {axis!r}")


def arc_mm(P: np.ndarray, verts, mm: float) -> float:
    """Summed 3D edge length along the vertices, in mm (v0 label._arc(P, verts) / MM)."""
    if len(verts) < 2:
        return 0.0 / mm
    X = np.array([P[r, c] for r, c in verts])
    return float(np.linalg.norm(np.diff(X, axis=0), axis=1).sum()) / mm


def fingerprint(geoms: dict[str, np.ndarray]) -> str:
    """SHA-256 over the loaded grids (patch name, shape, validity, coordinates), patches sorted.

    Two machines that score on the same patch files get the same value; a missing mask.tif or a
    re-exported patch changes it."""
    h = hashlib.sha256()
    for name in sorted(geoms):
        P = geoms[name]
        ok = valid_mask(P)
        h.update(name.encode())
        h.update(np.asarray(P.shape[:2], "<i8").tobytes())
        h.update(ok.astype("u1").tobytes())
        h.update(np.where(ok[..., None], P, -1.0).astype("<f8").tobytes())
    return h.hexdigest()

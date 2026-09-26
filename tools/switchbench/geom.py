"""Geometry primitives for SwitchBench-natural: tifxyz loading, normals, umbilicus, verified index.

Coordinates are PHercParis4 level-2 voxels of volume 20260411134726 (2.4 um x 4 = 9.6 um/vx);
evidence: meta.json area_cm2/area_vx2 = (9.6e-4 cm)^2 in every patch, and the level-2 zarr shape
(18946, 8174, 8174) bounds every patch coordinate. Points are stored (x, y, z).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import tifffile
from scipy.spatial import cKDTree

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data" / "paris4"
VOXEL_MM = 0.0096
MM = 1.0 / VOXEL_MM  # voxels per mm (104.17)


# ----------------------------------------------------------------------------- tifxyz
def load_tifxyz(d: Path | str, use_mask: bool = True) -> np.ndarray:
    """(H, W, 3) float64 grid of (x, y, z); invalid vertices are NaN."""
    d = Path(d)
    x = tifffile.imread(d / "x.tif").astype(np.float64)
    y = tifffile.imread(d / "y.tif").astype(np.float64)
    z = tifffile.imread(d / "z.tif").astype(np.float64)
    P = np.stack([x, y, z], -1)
    bad = (x == -1) | (y == -1) | (z == -1) | ~np.isfinite(P).all(-1) | (x <= 0) & (y <= 0) & (z <= 0)
    m = d / "mask.tif"
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


def grid_normals(P: np.ndarray) -> np.ndarray:
    """Unit normals from central (fallback one-sided) differences; NaN where undefined."""
    H, W, _ = P.shape
    du = np.full_like(P, np.nan)
    dv = np.full_like(P, np.nan)
    if W >= 3:
        du[:, 1:-1] = P[:, 2:] - P[:, :-2]
    if W >= 2:
        fwd = P[:, 1:] - P[:, :-1]
        du[:, :-1] = np.where(np.isnan(du[:, :-1]), fwd, du[:, :-1])
        du[:, 1:] = np.where(np.isnan(du[:, 1:]), fwd, du[:, 1:])
    if H >= 3:
        dv[1:-1] = P[2:] - P[:-2]
    if H >= 2:
        fwd = P[1:] - P[:-1]
        dv[:-1] = np.where(np.isnan(dv[:-1]), fwd, dv[:-1])
        dv[1:] = np.where(np.isnan(dv[1:]), fwd, dv[1:])
    n = np.cross(du, dv)
    nn = np.linalg.norm(n, axis=-1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        n = n / nn
    n[~np.isfinite(n).all(-1)] = np.nan
    return n


# ----------------------------------------------------------------------------- umbilicus
@lru_cache(maxsize=1)
def _umb():
    u = json.load(open(DATA / "umbilicus.json"))["control_points"]
    u = sorted(u, key=lambda c: c["z"])
    z = np.array([c["z"] for c in u], float)
    return z, np.array([c["x"] for c in u], float), np.array([c["y"] for c in u], float)


def umbilicus_xy(z):
    zz, xx, yy = _umb()
    return np.interp(z, zz, xx), np.interp(z, zz, yy)


def theta(P: np.ndarray) -> np.ndarray:
    cx, cy = umbilicus_xy(P[..., 2])
    return np.arctan2(P[..., 1] - cy, P[..., 0] - cx)


def radial_dir(P: np.ndarray) -> np.ndarray:
    cx, cy = umbilicus_xy(P[..., 2])
    e = np.stack([P[..., 0] - cx, P[..., 1] - cy, np.zeros_like(cx)], -1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return e / np.linalg.norm(e, axis=-1, keepdims=True)


def orient_outward(P: np.ndarray, n: np.ndarray) -> np.ndarray:
    """Flip each normal so that it points away from the umbilicus (n . e_r >= 0)."""
    s = np.sign(np.nansum(n * radial_dir(P), -1))
    s[s == 0] = 1
    return n * s[..., None]


def unwrap_theta(P: np.ndarray) -> np.ndarray:
    """BFS-unwrapped umbilicus angle over the valid grid (per 4-connected component)."""
    th = theta(P)
    H, W = th.shape
    ok = np.isfinite(th)
    out = np.full_like(th, np.nan)
    seen = np.zeros_like(ok)
    from collections import deque
    for r0, c0 in zip(*np.nonzero(ok)):
        if seen[r0, c0]:
            continue
        seen[r0, c0] = True
        out[r0, c0] = th[r0, c0]
        q = deque([(r0, c0)])
        while q:
            r, c = q.popleft()
            for rr, cc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if 0 <= rr < H and 0 <= cc < W and ok[rr, cc] and not seen[rr, cc]:
                    seen[rr, cc] = True
                    d = th[rr, cc] - th[r, c]
                    d = (d + np.pi) % (2 * np.pi) - np.pi
                    out[rr, cc] = out[r, c] + d
                    q.append((rr, cc))
    return out


# ----------------------------------------------------------------------------- verified index
class VerifiedIndex:
    """Lazy spatial index over verified patches (top-level dirs only; backups/ excluded)."""

    def __init__(self, root: Path = DATA / "verified_patches", exclude=()):
        self.root = root
        cache = DATA / "verified_bboxes.json"
        if cache.exists():
            bb = json.load(open(cache))
        else:
            bb = {}
            for d in sorted(root.iterdir()):
                if d.name == "backups" or not (d / "x.tif").exists():
                    continue
                P = load_tifxyz(d)
                if np.isnan(P).all():
                    continue
                bb[d.name] = [np.nanmin(P.reshape(-1, 3), 0).tolist(), np.nanmax(P.reshape(-1, 3), 0).tolist()]
            json.dump(bb, open(cache, "w"))
        self.names = sorted(n for n in bb if n not in set(exclude))
        self.lo = np.array([bb[n][0] for n in self.names])
        self.hi = np.array([bb[n][1] for n in self.names])
        self._cache: dict[str, tuple] = {}

    def patch(self, name: str):
        """(P, normals_outward, unwrapped theta) for a verified patch (cached)."""
        if name not in self._cache:
            if len(self._cache) > 400:
                self._cache.pop(next(iter(self._cache)))
            P = load_tifxyz(self.root / name)
            n = orient_outward(P, grid_normals(P))
            self._cache[name] = (P, n, None)
        return self._cache[name]

    def theta_u(self, name: str):
        P, n, tu = self.patch(name)
        if tu is None:
            tu = unwrap_theta(P)
            self._cache[name] = (P, n, tu)
        return tu

    def overlapping(self, lo, hi, pad=0.0):
        m = ((self.lo <= np.asarray(hi) + pad) & (self.hi >= np.asarray(lo) - pad)).all(1)
        return [self.names[i] for i in np.nonzero(m)[0]]

    def local_cloud(self, lo, hi, pad=160.0, exclude=()):
        """Verified vertices inside the padded box: points, normals, patch idx, (r, c), names, tree."""
        lo = np.asarray(lo) - pad
        hi = np.asarray(hi) + pad
        pts, nrm, pid, rc, names = [], [], [], [], []
        for nm in self.overlapping(lo, hi):
            if nm in exclude:
                continue
            P, n, _ = self.patch(nm)
            ok = np.isfinite(P).all(-1) & np.isfinite(n).all(-1)
            ok &= (P >= lo).all(-1) & (P <= hi).all(-1)
            if not ok.any():
                continue
            r, c = np.nonzero(ok)
            names.append(nm)
            pts.append(P[r, c]); nrm.append(n[r, c])
            pid.append(np.full(len(r), len(names) - 1)); rc.append(np.stack([r, c], 1))
        if not pts:
            return None
        pts = np.concatenate(pts); nrm = np.concatenate(nrm)
        return dict(pts=pts, nrm=nrm, pid=np.concatenate(pid), rc=np.concatenate(rc),
                    names=names, tree=cKDTree(pts))

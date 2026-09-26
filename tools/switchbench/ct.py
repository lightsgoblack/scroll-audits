"""Numeric-only CT sampling from the public PHercParis4 78 keV 2.4 um volume at OME-Zarr level 2 (9.6 um).

Chunks (128^3 uint8, uncompressed) are fetched over HTTPS into an in-memory LRU and never written to
disk. Only scalar intensity profiles leave this module. No images are produced (text rule a).
"""
from __future__ import annotations

import time
import urllib.request
from collections import OrderedDict

import numpy as np

ROOT = ("https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com/"
        "PHercParis4/volumes/20260411134726-2.400um-0.2m-78keV-masked.zarr")
SHAPES = {2: (18946, 8174, 8174), 1: (37892, 16347, 16347)}  # z, y, x per OME-Zarr level
LEVEL = 2   # sampling level; input coordinates are always level-2 voxels
BASE = f"{ROOT}/{LEVEL}"
SHAPE = SHAPES[LEVEL]


def set_level(level: int):
    global LEVEL, BASE, SHAPE
    LEVEL, BASE, SHAPE = level, f"{ROOT}/{level}", SHAPES[level]
    _cache.clear()
CH = 128
_cache: "OrderedDict[tuple, np.ndarray]" = OrderedDict()
MAX_CHUNKS = 256
STATS = {"fetched": 0, "bytes": 0, "missing": 0}


def _chunk(cz, cy, cx) -> np.ndarray:
    k = (cz, cy, cx)
    if k in _cache:
        _cache.move_to_end(k)
        return _cache[k]
    url = f"{BASE}/{cz}/{cy}/{cx}"  # BASE reflects LEVEL
    arr = None
    for i in range(5):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                b = r.read()
            arr = np.frombuffer(b, np.uint8).reshape(CH, CH, CH)
            STATS["fetched"] += 1
            STATS["bytes"] += len(b)
            break
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                arr = np.zeros((CH, CH, CH), np.uint8)
                STATS["missing"] += 1
                break
            time.sleep(2 ** (i + 1))
        except Exception:
            time.sleep(2 ** (i + 1))
    if arr is None:
        raise RuntimeError(f"CT chunk fetch failed: {url}")
    _cache[k] = arr
    if len(_cache) > MAX_CHUNKS:
        _cache.popitem(last=False)
    return arr


def prefetch(keys, workers=16):
    from concurrent.futures import ThreadPoolExecutor
    miss = [k for k in set(keys) if k not in _cache]
    if len(miss) > 1:
        global MAX_CHUNKS
        MAX_CHUNKS = min(600, max(MAX_CHUNKS, len(miss) + 64))
        with ThreadPoolExecutor(min(workers, len(miss))) as ex:
            list(ex.map(lambda k: _chunk(*k), miss))


def sample(pts: np.ndarray) -> np.ndarray:
    """Trilinear intensity at (N, 3) points given as (x, y, z) level-2 voxels. NaN outside the volume."""
    pts = np.asarray(pts, float)
    out = np.full(len(pts), np.nan)
    zyx = pts[:, ::-1] * (2 ** (2 - LEVEL))
    ok = np.isfinite(zyx).all(1) & (zyx >= 0).all(1) & (zyx < np.array(SHAPE) - 1).all(1)
    if not ok.any():
        return out
    q = zyx[ok]
    f = np.floor(q).astype(int)
    w = q - f
    prefetch([tuple(k) for k in np.unique(np.concatenate([f // CH, (f + 1) // CH]), axis=0)])
    vals = np.zeros(len(q))
    for dz in (0, 1):
        for dy in (0, 1):
            for dx in (0, 1):
                g = f + np.array([dz, dy, dx])
                wt = ((w[:, 0] if dz else 1 - w[:, 0]) * (w[:, 1] if dy else 1 - w[:, 1])
                      * (w[:, 2] if dx else 1 - w[:, 2]))
                c = g // CH
                l = g % CH
                code = (c[:, 0] * 1000 + c[:, 1]) * 1000 + c[:, 2]
                v = np.empty(len(g))
                for cc in np.unique(code):
                    m = code == cc
                    key = (int(cc // 1000000), int(cc // 1000 % 1000), int(cc % 1000))
                    a = _chunk(*key)
                    ll = l[m]
                    v[m] = a[ll[:, 0], ll[:, 1], ll[:, 2]]
                vals += wt * v
    out[ok] = vals
    return out


def profile(p0: np.ndarray, d: np.ndarray, t0: float, t1: float, step: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    """Intensity along p0 + t*d for t in [t0, t1]."""
    t = np.arange(t0, t1 + 1e-9, step)
    return t, sample(p0[None] + t[:, None] * d[None])

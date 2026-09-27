"""SwitchBench v1: numeric-only CT sampling at any OME-Zarr level of the public PHercParis4 volume.

Level 0 is the full 2.4 um resolution (protocol P1 (prereg/switchbench_v1.md) "Labels: 2.4 um CT"). Input coordinates are always
level-2 voxels (x, y, z), the frame of every patch and annotation; they are scaled by 2**(2 - level)
to the sampled level, following the multiscale metadata (scale 1/2/4, no translation).
Chunks (128^3 uint8, uncompressed) are fetched over HTTPS into an in-memory LRU and never written to
disk. Only scalar 1-D intensity profiles leave this module. No images are produced.
This module is separate from ct.py so that the v0 harness stays byte-identical and reproducible.
"""
from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import numpy as np

ROOT = ("https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com/"
        "PHercParis4/volumes/20260411134726-2.400um-0.2m-78keV-masked.zarr")
SHAPES = {0: (75784, 32693, 32693), 1: (37892, 16347, 16347), 2: (18946, 8174, 8174)}  # z, y, x
CH = 128


class Sampler:
    """Trilinear sampler at one pyramid level with a bounded chunk LRU (max_chunks x 2 MiB)."""

    def __init__(self, level: int = 0, max_chunks: int = 320, workers: int = 16):
        self.level = level
        self.base = f"{ROOT}/{level}"
        self.shape = np.array(SHAPES[level])
        self.scale = 2.0 ** (2 - level)
        self.max_chunks = max_chunks
        self.workers = workers
        self._cache: "OrderedDict[tuple, np.ndarray]" = OrderedDict()
        self._lock = threading.Lock()
        self.stats = {"fetched": 0, "bytes": 0, "missing": 0}

    def _fetch(self, k):
        url = f"{self.base}/{k[0]}/{k[1]}/{k[2]}"
        for i in range(6):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    b = r.read()
                a = np.frombuffer(b, np.uint8).reshape(CH, CH, CH)
                with self._lock:
                    self.stats["fetched"] += 1
                    self.stats["bytes"] += len(b)
                return a
            except urllib.error.HTTPError as e:
                if e.code in (403, 404):
                    with self._lock:
                        self.stats["missing"] += 1
                    return np.zeros((CH, CH, CH), np.uint8)
                time.sleep(2 ** (i + 1))
            except Exception:
                time.sleep(2 ** (i + 1))
        raise RuntimeError(f"CT chunk fetch failed: {url}")

    def _put(self, k, a):
        with self._lock:
            self._cache[k] = a
            self._cache.move_to_end(k)
            while len(self._cache) > self.max_chunks:
                self._cache.popitem(last=False)

    def ensure(self, keys):
        keys = list(dict.fromkeys(keys))
        with self._lock:
            miss = [k for k in keys if k not in self._cache]
            for k in keys:
                if k in self._cache:
                    self._cache.move_to_end(k)
        if len(keys) > self.max_chunks:
            raise RuntimeError(f"profile needs {len(keys)} chunks > LRU size {self.max_chunks}")
        if miss:
            with ThreadPoolExecutor(min(self.workers, len(miss))) as ex:
                for k, a in zip(miss, ex.map(self._fetch, miss)):
                    self._put(k, a)
        with self._lock:
            return {k: self._cache[k] for k in keys}

    def sample(self, pts_l2: np.ndarray) -> np.ndarray:
        """Trilinear intensity at (N, 3) level-2 (x, y, z) points. NaN outside the volume."""
        pts = np.asarray(pts_l2, float)
        out = np.full(len(pts), np.nan)
        zyx = pts[:, ::-1] * self.scale
        ok = np.isfinite(zyx).all(1) & (zyx >= 0).all(1) & (zyx < self.shape - 1).all(1)
        if not ok.any():
            return out
        q = zyx[ok]
        f = np.floor(q).astype(np.int64)
        w = q - f
        corners = [(dz, dy, dx) for dz in (0, 1) for dy in (0, 1) for dx in (0, 1)]
        allg = np.concatenate([f + np.array(c) for c in corners])
        keys = [tuple(k) for k in np.unique(allg // CH, axis=0)]
        arrs = self.ensure(keys)
        vals = np.zeros(len(q))
        for dz, dy, dx in corners:
            g = f + np.array([dz, dy, dx])
            wt = ((w[:, 0] if dz else 1 - w[:, 0]) * (w[:, 1] if dy else 1 - w[:, 1])
                  * (w[:, 2] if dx else 1 - w[:, 2]))
            c = g // CH
            l = g % CH
            v = np.empty(len(g))
            cu, inv = np.unique(c, axis=0, return_inverse=True)
            inv = inv.reshape(-1)
            for j, cc in enumerate(cu):
                m = inv == j
                a = arrs[tuple(cc)]
                ll = l[m]
                v[m] = a[ll[:, 0], ll[:, 1], ll[:, 2]]
            vals += wt * v
        out[ok] = vals
        return out

    def profile(self, p0, d, t0: float, t1: float, step: float):
        """Intensity along p0 + t*d (level-2 units) for t in [t0, t1] with the given step."""
        t = np.arange(t0, t1 + 1e-9, step)
        p0 = np.asarray(p0, float)
        d = np.asarray(d, float)
        return t, self.sample(p0[None] + t[:, None] * d[None])

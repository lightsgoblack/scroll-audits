"""The kit's replicas of v0 helpers give identical results to tools/switchbench (skipped without it)."""
from __future__ import annotations

import numpy as np
import pytest

from _synth import make_patches
from tools.switchbench_kit import geometry, scoring

v0 = pytest.importorskip("tools.switchbench.evaluate", reason="v0 package tools/switchbench not importable")
from tools.switchbench import geom, label, metrics  # noqa: E402


def test_units():
    assert geometry.VOXEL_MM == geom.VOXEL_MM and geometry.vx_per_mm() == geom.MM


def test_load_tifxyz_identical(tmp_path):
    make_patches(tmp_path)
    for p in ("pA", "pB"):
        for use_mask in (True, False):
            np.testing.assert_array_equal(geometry.load_tifxyz(tmp_path / p, use_mask),
                                          geom.load_tifxyz(tmp_path / p, use_mask))


def test_wilson_identical():
    for n in (0, 1, 2, 7, 54, 200):
        for k in range(n + 1):
            assert scoring.wilson(k, n) == metrics.wilson(k, n)


def test_near_and_dedup_identical():
    rng = np.random.default_rng(7)
    for trial in range(20):
        X = rng.uniform(0, 600, (rng.integers(1, 30), 3))
        A = rng.uniform(0, 600, (rng.integers(0, 200), 3))
        np.testing.assert_array_equal(scoring.near(X, A, 1.0 * geom.MM), v0.near(X, A))
        np.testing.assert_array_equal(scoring.dedup(A, 0.5 * geom.MM), v0.dedup_alarms(A).reshape(-1, 3))
    grid = np.array([[i, j, 0] for i in range(0, 300, 26) for j in range(0, 300, 26)], float)  # 0.25 mm lattice
    np.testing.assert_array_equal(scoring.dedup(grid, 0.5 * geom.MM), v0.dedup_alarms(grid))


def test_arc_length_identical():
    rng = np.random.default_rng(3)
    P = np.cumsum(rng.normal(0, 8, (5, 40, 3)), axis=1) + 1000
    verts = [(2, c) for c in range(3, 37)]
    assert geometry.arc_mm(P, verts, geom.MM) == label._arc(P, verts) / geom.MM


def test_fetch_uses_the_v0_bucket_layout():
    from tools.switchbench import pull
    from tools.switchbench_kit.fetch import patch_source
    assert patch_source({}) == (pull.BUCKET, f"{pull.ROOT}/unverified_patches")

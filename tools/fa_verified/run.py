"""P7 (prereg/fa_verified.md): detector false alarms on the human-verified spiral-fit patches.

In plain English: the Vesuvius team treats these patches as switch-free, so every alarm a detector raises on
them is a false alarm. This runs the detectors on them (numbers only, no CT, no images) and scores the rate.

    python -m tools.fa_verified.run detect [--limit N] [--workers 3]   # seeded order, resumable
    python -m tools.fa_verified.run score                              # -> results/fa_verified.{md,json}
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from tools.switchbench import doctor_v1, geom, metrics
from tools.switchbench_kit.scoring import dedup

REPO = Path(__file__).resolve().parents[2]
VER = REPO / "data" / "paris4" / "verified_patches"
OUT = REPO / "data" / "fa_verified"
DOC_OUT = OUT / "detect" / "tifxyz_doctor"
SEED = 20260930
VOXEL_MM = 0.0096
DEDUP_MM = 0.5
V1_CI = (0.14, 0.83)
V1_POINT = 0.43


def order() -> list[str]:
    names = sorted(p.name for p in VER.iterdir() if p.is_dir())
    return [names[i] for i in np.random.default_rng(SEED).permutation(len(names))]


def parent(nm: str) -> str:
    return nm.split("_sel_")[0]


def _one(nm: str) -> tuple[str, str, float]:
    doctor_v1.OUT = DOC_OUT
    t = time.time()
    try:
        r = doctor_v1.run(nm, VER / nm)
        v = r.get("verdict", "error")
    except Exception as e:  # recorded, never retried with other settings
        DOC_OUT.mkdir(parents=True, exist_ok=True)
        json.dump(dict(patch=nm, verdict="error", error=str(e)[-300:]), open(DOC_OUT / f"{nm}.json", "w"))
        v = "error"
    return nm, v, time.time() - t


def detect(limit: int | None, workers: int) -> None:
    names = order()[:limit] if limit else order()
    todo = [n for n in names if not (DOC_OUT / f"{n}.json").exists()]
    print(f"{len(names)} in scope, {len(todo)} to run", flush=True)
    t0, done = time.time(), 0
    with ProcessPoolExecutor(workers) as ex:
        for nm, v, dt in ex.map(_one, todo):
            done += 1
            if done % 25 == 0 or done == len(todo):
                el = time.time() - t0
                print(f"{done}/{len(todo)} elapsed {el/60:.1f} min, projected total for all "
                      f"{len(order())}: {el/done*len(order())/3600:.2f} h", flush=True)


def grid_area_cm2(P: np.ndarray) -> float:
    """Surface area from the patch's own vertex grid: valid quads split into two triangles (D2 secondary)."""
    a, b, c, d = P[:-1, :-1], P[:-1, 1:], P[1:, :-1], P[1:, 1:]
    ok = np.isfinite(a).all(-1) & np.isfinite(b).all(-1) & np.isfinite(c).all(-1) & np.isfinite(d).all(-1)
    t1 = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=-1)
    t2 = 0.5 * np.linalg.norm(np.cross(b - d, c - d), axis=-1)
    vx2 = float(np.where(ok, t1 + t2, 0).sum())
    return vx2 * (VOXEL_MM ** 2) / 100.0


def _summary(rows: list[dict], area_key: str) -> dict:
    rows = [r for r in rows if r.get(area_key)]
    area = sum(r[area_key] for r in rows)
    parents = sorted({r["parent"] for r in rows})
    ix = {p: i for i, p in enumerate(parents)}
    A = np.zeros(len(parents)); C = np.zeros(len(parents)); Y = np.zeros(len(parents))
    for r in rows:
        i = ix[r["parent"]]; A[i] += r[area_key]; C[i] += r["cns"]; Y[i] += r["any"]
    rng = np.random.default_rng(SEED)
    boots = {"cns": [], "any": []}
    for _ in range(2000):
        i = rng.integers(0, len(parents), len(parents))
        boots["cns"].append(C[i].sum() / A[i].sum()); boots["any"].append(Y[i].sum() / A[i].sum())
    out = dict(n_patches=len(rows), n_parents=len(parents), area_cm2=area)
    for col in ("cns", "any"):
        tot = int(sum(r[col] for r in rows)); m1 = tot / area
        lo, hi = (float(v) for v in np.percentile(boots[col], [2.5, 97.5]))
        out[col] = dict(alarms=tot, patches_with_alarm=int(sum(r[col] > 0 for r in rows)), M1_per_cm2=m1,
                        M1_ci=[lo, hi], M2_per_100mm=2 * m1, M2_ci=[2 * lo, 2 * hi])
    lo2, hi2 = out["cns"]["M2_ci"]
    out["verdict"] = ("V1_FA_OVERSTATED" if hi2 < V1_CI[0] else
                      "V1_FA_UNDERSTATED_ON_CLEAN_SURFACE" if lo2 > V1_CI[1] else "V1_FA_CONSISTENT")
    return out


def score() -> dict:
    names = order()
    rows, skipped, errors, missing = [], 0, [], 0
    r_vx = DEDUP_MM / VOXEL_MM
    for nm in names:
        f = DOC_OUT / f"{nm}.json"
        if not f.exists():
            missing += 1
            continue
        rec = json.load(open(f))
        if rec.get("verdict") == "error":
            errors.append(nm)
            continue
        P = geom.load_tifxyz(VER / nm)
        if not np.isfinite(P).all(-1).any():
            skipped += 1
            continue
        meta = json.load(open(VER / nm / "meta.json"))
        row = dict(patch=nm, parent=parent(nm), meta_area_cm2=meta.get("area_cm2"), grid_area_cm2=grid_area_cm2(P))
        for key, col in (("alarms_primary", "cns"), ("alarms_any", "any")):
            X = metrics.cells_to_xyz(P, rec.get(key, []))
            row[col] = int(len(dedup(X, r_vx)))
        rows.append(row)
    both = [r for r in rows if r["meta_area_cm2"]]
    ratio = [r["grid_area_cm2"] / r["meta_area_cm2"] for r in both if r["meta_area_cm2"] > 0]
    out = dict(n_scope=len(names), n_scored=len(rows), n_skipped_no_valid=skipped, n_errors=len(errors),
               errors=errors, n_not_run=missing,
               area_check=dict(n=len(ratio), grid_over_meta_median=float(np.median(ratio)),
                               p05=float(np.percentile(ratio, 5)), p95=float(np.percentile(ratio, 95))),
               primary_frozen_meta_area=_summary(rows, "meta_area_cm2"),
               secondary_grid_area_all=_summary(rows, "grid_area_cm2"))
    out["verdict"] = out["primary_frozen_meta_area"]["verdict"]
    json.dump(out, open(REPO / "results/fa_verified.json", "w"), indent=1)
    json.dump(rows, open(OUT / "per_patch.json", "w"))
    print(json.dumps({k: v for k, v in out.items() if k != "errors"}, indent=1))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    d = sp.add_parser("detect"); d.add_argument("--limit", type=int); d.add_argument("--workers", type=int, default=3)
    sp.add_parser("score")
    a = ap.parse_args()
    detect(a.limit, a.workers) if a.cmd == "detect" else score()

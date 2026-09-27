"""Regression: the kit reproduces the SwitchBench-natural v0 detector table exactly.

The six v0 alarm sets are rebuilt from the stored v0 detector outputs with v0's own harness code
(tools/switchbench, read-only): tifxyz-doctor cells -> metrics.cells_to_xyz -> evaluate.dedup_alarms;
windcheck / windaudit stored alarms_xyz -> dedup_alarms, on patches with a verdict only; the
#1621-style check recomputed with annot.check_1621 (20 points per alarm segment, patches with >= 1
annotation pair only); random alarms re-drawn with v0's seeded procedure (density from the doctor's
any-cue alarms). Each set is written as a kit alarms file and scored through the kit's public path
(load_alarms + score, and once through the CLI); every number is compared with
results/switchbench_natural_v0.json, including the per-event hit table.

Two runs are reported. "v0 semantics" counts the alarms exactly as v0's harness passed them to its
scorer (fa_dedup_mm=0) and draws the six bootstrap intervals from one stream in table order, as v0's
report.py did: it must match v0 exactly. "Kit defaults" (v1 rules: 0.5 mm false-alarm de-dup for
every detector, a fresh bootstrap stream per detector) is listed with every difference explained.

Usage: python -m tools.switchbench_kit.regression [--out results/switchbench_kit_regression.json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from . import __version__
from .alarms import load_alarms
from .corpus import REPO, sha256_file, load_benchmark
from .scoring import score

CORPUS = REPO / "vault" / "results" / "switchbench_natural_events.json"
V0_RESULTS = REPO / "vault" / "results" / "switchbench_natural.json"
OUT_JSON = REPO / "vault" / "results" / "switchbench_kit_regression.json"
WORK = REPO / "data" / "switchbench_kit" / "regression_v0"     # rebuilt alarm files (gitignored)
TOOLS = ["tifxyz-doctor (coherent-normal-step)", "tifxyz-doctor (any cue)", "windcheck", "windaudit",
         "#1621-style annotation check", "random"]
FILES = {"tifxyz-doctor (coherent-normal-step)": "doctor_cns_xyz.json", "tifxyz-doctor (any cue)": "doctor_any_xyz.json",
         "windcheck": "windcheck_xyz.json", "windaudit": "windaudit_xyz.json",
         "#1621-style annotation check": "annot1621_xyz.json", "random": "random_grid.json"}
ADAPTERS = {
    "tifxyz-doctor (coherent-normal-step)": "stored alarms_primary cells -> v0 metrics.cells_to_xyz (mean of valid quad "
                                            "corners) -> v0 evaluate.dedup_alarms (0.5 mm) -> format (a) xyz; all patches",
    "tifxyz-doctor (any cue)": "stored alarms_any cells -> cells_to_xyz -> dedup_alarms -> format (a) xyz; all patches",
    "windcheck": "stored alarms_xyz -> dedup_alarms -> format (a); only patches with verdict clean/alarm "
                 "(the others are absent = no verdict)",
    "windaudit": "stored alarms_xyz -> dedup_alarms -> format (a); only patches with verdict clean/alarm",
    "#1621-style annotation check": "annot.check_1621 recomputed (v0 code) -> evaluate.segment_points (20 per alarm "
                                    "segment, not de-duplicated, as v0) -> format (a); only patches with >= 1 pair",
    "random": "v0 procedure re-run (Poisson at the doctor's any-cue density, seed 20260925, patches sorted) -> picked "
              "grid vertices -> format (b) [row, col]; also written as format (a) and (c) for a cross-format check",
}


def _rel(p: Path) -> str:
    p = Path(p)
    return str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p)  # noqa


def _dump(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))
    return path


def build_v0_alarm_files(bench, work: Path = WORK) -> dict:
    """Write the six v0 alarm sets as kit alarm files; returns {tool: path} plus extras."""
    from tools.switchbench import annot, evaluate, geom, metrics   # v0 harness, read-only
    det = geom.DATA / "detect"
    j = lambda tool, nm: json.load(open(det / tool / f"{nm}.json"))
    geoms, dens = {}, []
    for nm in bench.patches:                        # v0 'scored' order = corpus files sorted by patch name
        P = geom.load_tifxyz(geom.DATA / "unverified_patches" / nm)
        geoms[nm] = (P, geom.orient_outward(P, geom.grid_normals(P)))
        area = np.isfinite(P).all(-1).sum() * (20 / geom.MM) ** 2
        td = j("tifxyz_doctor", nm)
        dens.append(len(evaluate.dedup_alarms(metrics.cells_to_xyz(P, td.get("alarms_any", [])))) / max(area, 1e-9))
    density = float(np.mean(dens)) if dens else 0.0
    rng = np.random.default_rng(metrics.SEED)
    sets = {t: {} for t in TOOLS}
    rand_xyz, masks = {}, {}
    for nm in bench.patches:
        P, N = geoms[nm]
        td, wc, wa = j("tifxyz_doctor", nm), j("windcheck", nm), j("windaudit", nm)
        a = annot.check_1621(P, N)
        sets[TOOLS[0]][nm] = evaluate.dedup_alarms(metrics.cells_to_xyz(P, td.get("alarms_primary", []))).tolist()
        sets[TOOLS[1]][nm] = evaluate.dedup_alarms(metrics.cells_to_xyz(P, td.get("alarms_any", []))).tolist()
        if wc.get("verdict") in ("clean", "alarm"):
            sets["windcheck"][nm] = evaluate.dedup_alarms(np.array(wc.get("alarms_xyz", [])).reshape(-1, 3)).tolist()
        if wa.get("verdict") in ("clean", "alarm"):
            sets["windaudit"][nm] = evaluate.dedup_alarms(np.array(wa.get("alarms_xyz", [])).reshape(-1, 3)).tolist()
        if a["pairs"] > 0:
            seg = [evaluate.segment_points(x["xyz_p"], x["xyz_q"]) for x in a["alarms"]]
            sets[TOOLS[4]][nm] = (np.concatenate(seg).reshape(-1, 3) if seg else np.zeros((0, 3))).tolist()
        valid = np.argwhere(np.isfinite(P).all(-1))
        area = len(valid) * (20 / geom.MM) ** 2
        k = rng.poisson(density * area)
        pick = valid[rng.choice(len(valid), min(k, len(valid)), replace=False)] if k else np.zeros((0, 2), int)
        sets["random"][nm] = pick.tolist()
        rand_xyz[nm] = np.array([P[tuple(x)] for x in pick]).reshape(-1, 3).tolist()
        m = np.zeros(P.shape[:2], bool)
        m[tuple(pick.T)] = True
        masks[nm] = m
    paths = {t: _dump({"format": "grid" if t == "random" else "xyz", "detector": t, "alarms": sets[t]}, work / FILES[t])
             for t in TOOLS}
    paths["random (format a)"] = _dump({"format": "xyz", "detector": "random", "alarms": rand_xyz}, work / "random_xyz.json")
    mdir = work / "random_masks"
    mdir.mkdir(parents=True, exist_ok=True)
    for old in mdir.glob("*.npz"):
        old.unlink()
    for nm, m in masks.items():
        np.savez_compressed(mdir / f"{nm}.npz", mask=m)
    paths["random (format c)"] = mdir
    return dict(paths=paths, density=density)


def _v0_numbers(v0: dict, t: str) -> dict:
    D = v0["evaluation"]["detectors"][t]
    return dict(hits=D["hits"], events=D["n_events"], recall=D["recall"], wilson95=D["recall_ci95"],
                bootstrap95=v0["recall_patch_block_bootstrap_ci95"][t], false_alarms=D["false_alarms"],
                negative_mm=D["negative_mm"], fa_per_100mm=D["fa_per_100mm"],
                patches_with_verdict=D["patches_with_verdict"], scored_patches=D["n_patches"])


def _kit_numbers(r: dict) -> dict:
    R, F, C = r["recall"], r["false_alarms"], r["coverage"]
    return dict(hits=R["hits"], events=R["events"], recall=R["recall"], wilson95=R["wilson95"],
                bootstrap95=R["bootstrap95"], false_alarms=F["count"], negative_mm=F["negative_mm"],
                fa_per_100mm=F["per_100mm"], patches_with_verdict=C["patches"][0], scored_patches=C["patches"][1])


def _headline(r: dict) -> dict:
    x = _kit_numbers(r)
    return {k: x[k] for k in ("hits", "events", "false_alarms", "negative_mm", "patches_with_verdict", "wilson95",
                              "bootstrap95")}


def _close_pairs(A, mm_vx, lim_mm=0.5):
    from scipy.spatial import cKDTree
    if A is None or len(A) < 2:
        return []
    return [round(float(np.linalg.norm(A[i] - A[j])) / mm_vx, 4)
            for i, j in sorted(cKDTree(A).query_pairs(lim_mm * mm_vx * (1 + 1e-9)))]


def _explained(tool: str, field: str) -> bool:
    """Which kit-default vs v0 differences have a known cause (anything else is a defect)."""
    if field == "bootstrap95":        # v0's shared stream: only the first row drew it from the start
        return tool != TOOLS[0]
    if field in ("false_alarms", "fa_per_100mm"):   # v0 never de-duplicated these two sets
        return tool in ("random", "#1621-style annotation check")
    return False


def run(out: Path | None = OUT_JSON, work: Path = WORK, cli: bool = True, log=print) -> dict:
    t0 = time.time()
    v0 = json.load(open(V0_RESULTS))
    bench = load_benchmark(CORPUS)
    built = build_v0_alarm_files(bench, work)
    paths = built["paths"]
    alarm_sets = {t: load_alarms(paths[t], bench, detector=t) for t in TOOLS}
    # v0 semantics: every alarm counted as given (v0's harness had already de-duplicated the doctor,
    # windcheck and windaudit sets, which the adapters reproduce), one bootstrap stream in table order
    shared = np.random.default_rng(20260925)
    v0sem = {t: score(bench, alarm_sets[t], fa_dedup_mm=0, rng=shared) for t in TOOLS}
    default = {t: score(bench, alarm_sets[t]) for t in TOOLS}          # kit defaults (v1 rules)

    v0_rows = v0["scored_events"]
    conf = bench.confirmed_events()
    rows_aligned = len(v0_rows) == len(conf) and all(
        r["patch"] == e.patch and r["xyz"] == e.centre.tolist() for r, e in zip(v0_rows, conf))
    reasons = {"false_alarms": "v0 never de-duplicated random alarms; the kit's uniform 0.5 mm de-dup (v1 rule) merges "
                              "one pair of random alarms that both lie on a negative run",
               "fa_per_100mm": "follows false_alarms",
               "bootstrap95": "v0 drew this row's bootstrap from a stream shared with the rows above it; the kit "
                              "default draws a fresh stream seeded 20260925 per detector"}
    det, exact = {}, rows_aligned
    for t in TOOLS:
        kv, vv, kd = _kit_numbers(v0sem[t]), _v0_numbers(v0, t), _kit_numbers(default[t])
        match = {k: kv[k] == vv[k] for k in vv}
        ev_mis = [dict(event=i, patch=r["patch"], v0=r[t], kit=k["hit"])
                  for i, (r, k) in enumerate(zip(v0_rows, v0sem[t]["events"])) if r[t] != k["hit"]]
        ev_mis_default = sum(r[t] != k["hit"] for r, k in zip(v0_rows, default[t]["events"]))
        ok = all(match.values()) and not ev_mis
        exact &= ok
        diffs = {k: dict(kit_default=kd[k], v0=vv[k], why=reasons[k] if _explained(t, k) else "UNEXPLAINED")
                 for k in vv if kd[k] != vv[k]}
        det[t] = dict(alarms_file=_rel(paths[t]), format=alarm_sets[t].format, adapter=ADAPTERS[t],
                      v0=vv, kit_v0_semantics=kv, match=match, per_event_hit_mismatches=ev_mis, exact_match=ok,
                      kit_default=kd, kit_default_differences=diffs,
                      kit_default_per_event_hit_mismatches=int(ev_mis_default))
        log(f"{t:38s} v0-semantics: hits {kv['hits']}/{kv['events']} FA {kv['false_alarms']} verdict "
            f"{kv['patches_with_verdict']}/{kv['scored_patches']} -> {'EXACT' if ok else 'MISMATCH'}; "
            f"kit default differs in: {sorted(diffs) or 'nothing'}")
    unexplained = [f"{t}.{k}" for t, d in det.items() for k, x in d["kit_default_differences"].items()
                   if x["why"] == "UNEXPLAINED"]
    unexplained += [f"{t}.per_event_hits" for t, d in det.items() if d["kit_default_per_event_hit_mismatches"]]

    # random through all three input formats (order-free with de-dup off; with de-dup the order decides
    # which alarm of a close pair is kept, and a mask lists alarms row by row)
    fmt = {"b grid [row, col]": paths["random"], "a xyz": paths["random (format a)"],
           "c masks (.npz)": paths["random (format c)"]}
    fsets = {k: load_alarms(v, bench, detector="random") for k, v in fmt.items()}
    as_given = {k: score(bench, a, fa_dedup_mm=0) for k, a in fsets.items()}
    dflt = {k: score(bench, a) for k, a in fsets.items()}
    same = lambda a, b: _headline(a) == _headline(b) and [e["hit"] for e in a["events"]] == [e["hit"] for e in b["events"]]
    ref = as_given["b grid [row, col]"]
    formats = dict(as_given={k: _headline(v) for k, v in as_given.items()},
                   identical_as_given=all(same(v, ref) for v in as_given.values()),
                   kit_default={k: _headline(v) for k, v in dflt.items()},
                   random_alarm_pairs_closer_than_0p5mm_mm={p: _close_pairs(A, bench.mm)
                                                            for p, A in alarm_sets["random"].by_patch.items()
                                                            if _close_pairs(A, bench.mm)})
    exact &= formats["identical_as_given"]
    dens_ok = built["density"] == v0["evaluation"]["random_density_per_mm2"]
    exact &= dens_ok

    cli_check = None
    if cli:
        tmp = work / "cli_doctor_cns.json"
        p = subprocess.run([sys.executable, "-m", "tools.switchbench_kit", "score", "--corpus", str(CORPUS),
                            "--alarms", str(paths[TOOLS[0]]), "--json", str(tmp)], capture_output=True, text=True,
                           cwd=REPO)
        cj = json.load(open(tmp)) if p.returncode == 0 and tmp.exists() else None
        cli_check = dict(command=f"python -m tools.switchbench_kit score --corpus {_rel(CORPUS)} --alarms "
                                 f"{_rel(paths[TOOLS[0]])} --json ...",
                         returncode=p.returncode,
                         identical_to_api=bool(cj) and _kit_numbers(cj) == _kit_numbers(default[TOOLS[0]])
                         and cj["events"] == default[TOOLS[0]]["events"],
                         table=p.stdout.strip().splitlines()[5:13] if p.returncode == 0 else p.stderr[-500:])
        exact &= cli_check["identical_to_api"]

    verdict = ("EXACT MATCH: all six v0 rows, every field and every per-event hit, under v0 semantics"
               if exact else "MISMATCH (see detectors.*.match)")
    res = dict(
        what="SwitchBench scorer kit vs the SwitchBench-natural v0 detector table",
        generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        kit_version=__version__,
        verdict=verdict,
        exact_match_v0_semantics=exact,
        kit_default_differences_all_explained=not unexplained,
        kit_default_unexplained=unexplained,
        v0_semantics=("score(..., fa_dedup_mm=0, rng=<one Generator seeded 20260925 shared by the six rows in v0 table "
                      "order>): alarms counted exactly as the v0 harness passed them to its scorer"),
        kit_defaults=("match 1.0 mm, false-alarm de-dup 0.5 mm for every detector, no per-patch cap, B = 2000, a "
                      "fresh bootstrap stream seeded 20260925 per detector (v1 rules)"),
        corpus=dict(path=_rel(CORPUS), sha256=bench.sha256, geometry_sha256=bench.geometry_sha256,
                    scored_patches=len(bench.patches), confirmed_events=len(conf),
                    confirmed_negative_runs=len(bench.confirmed_negatives()),
                    negative_mm=default[TOOLS[0]]["false_alarms"]["negative_mm"]),
        v0_source=dict(results=_rel(V0_RESULTS), sha256=sha256_file(V0_RESULTS),
                       detector_outputs="data/paris4/detect/{tifxyz_doctor,windcheck,windaudit}/<patch>.json (stored v0 "
                                        "runs); #1621 recomputed with tools/switchbench/annot.py; random re-drawn",
                       v0_code="tools/switchbench/{evaluate,metrics,geom,annot}.py, unchanged since 7cef187"),
        per_event_rows_aligned=rows_aligned,
        detectors=det,
        random_density_per_mm2=dict(kit_rebuild=built["density"], v0=v0["evaluation"]["random_density_per_mm2"],
                                    match=dens_ok),
        random_across_formats=formats,
        notes=[
            "Bootstrap: v0 (tools/switchbench/report.py) drew all six recall bootstrap intervals from ONE stream seeded "
            "20260925 in table order, so an interval depended on its row position: any-cue has exactly the same "
            "per-event hits as coherent-normal-step yet v0 printed [0.038, 0.191] against [0.024, 0.189]. The kit "
            "gives each detector a fresh stream (as v1 does), so identical hits give identical intervals; "
            "score(..., rng=shared) reproduces v0's stream exactly.",
            "False-alarm de-dup: v0's harness de-duplicated the doctor, windcheck and windaudit alarms (0.5 mm, greedy) "
            "before matching and counting, never the random or #1621 alarms. The kit applies the 0.5 mm de-dup to "
            "every detector before counting false alarms only (hits use every submitted alarm), as frozen for v1. "
            "On v0 this changes one number: random false alarms 82 -> 81 (auto_grown_w20231031143852 holds three "
            "random pairs < 0.5 mm apart; one pair lies on a negative run). --fa-dedup-mm 0 restores v0's 82.",
        ],
        cli_check=cli_check,
        elapsed_s=round(time.time() - t0, 1),
    )
    if out is not None:
        out = Path(out)
        out.write_text(json.dumps(res, indent=1) + "\n")
        log(f"wrote {out}  verdict: {res['verdict']}")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(OUT_JSON))
    ap.add_argument("--no-cli", action="store_true")
    a = ap.parse_args(argv)
    r = run(Path(a.out), cli=not a.no_cli)
    return 0 if r["exact_match_v0_semantics"] and r["kit_default_differences_all_explained"] else 1


if __name__ == "__main__":
    sys.exit(main())

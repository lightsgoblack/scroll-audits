"""SwitchBench v1: run every detector, both modes, on the scored patches (protocol P1 (prereg/switchbench_v1.md)).

primary (defaults at the pinned commits, as v0; doctor uncapped):
  tifxyz-doctor 5ca0444   doctor_v1.run (uncapped: API mask UNION CLI examples)
  windcheck 2b0fb2f       v0 detectors.windcheck (`check`; refuses < 5,000 valid cells = no verdict)
  windaudit aba5633       run_windaudit_v1 mode "default" (v0 harness, WIDE_ATTACHMENT_GAP=1, 2.5 vx)
  #1621-style check       annot.check_1621 (ours, as v0)
secondary ("author-intended mode", reported beside defaults, never replacing them):
  windcheck patch mode    wc_patchmode.py (bench/patch_audit.py audit_one: engine with no cell floor)
  windaudit widened       run_windaudit_v1 mode "intended" (attachment tolerance 0.45 D = 10.485 vx)
  seamcheck 6d6bc2d       seamcheck_run.py (added after the freeze on Scout Report #8; C2 only)
  sheet-topo-bench        not run (input contract; see results md)
All outputs under data/switchbench_v1/detect/ (gitignored). Numeric only; no images.
Usage: python -m tools.switchbench.detectors_v1 [names...]   (default: all scored patches, evaluate_v1)
"""
from __future__ import annotations

import os

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from . import annot, detectors, doctor_v1, geom, run_windaudit_v1

V1 = geom.REPO / "data" / "switchbench_v1"
DET = V1 / "detect"
WC = Path(os.environ.get("SWITCHBENCH_EXT", "ext") + "/windcheck")
SC_PY = Path(os.environ.get("SWITCHBENCH_EXT", "ext") + "/seamcheck/.venv/bin/python")
HERE = Path(__file__).resolve().parent


def windcheck_default(nm):
    detectors.OUT = DET  # v0 function, outputs redirected to the v1 directory
    return detectors.windcheck(nm)


def windcheck_patchmode(nm):
    f = DET / "windcheck_patchmode" / f"{nm}.json"
    if f.exists():
        return json.load(open(f))
    f.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="wc_", dir=V1))
    try:
        p = subprocess.run(["uv", "run", "--project", str(WC), "python", str(HERE / "wc_patchmode.py"),
                            str(geom.DATA / "unverified_patches" / nm), str(work), str(f.with_suffix(".raw.json"))],
                           capture_output=True, text=True, cwd=WC)
        rec = dict(tool="windcheck", mode="patch_audit (no cell floor)", patch=nm, returncode=p.returncode,
                   stderr=p.stderr.strip()[-300:])
        if f.with_suffix(".raw.json").exists():
            r = json.load(open(f.with_suffix(".raw.json")))
            f.with_suffix(".raw.json").unlink()
            al = [c[k] for c in r["contacts"] for k in ("xyz1", "xyz2") if c.get(k) is not None]
            rec.update(n_valid=r["n_valid"], transverse_both=r["transverse_both"], alarms_xyz=al,
                       verdict="alarm" if r["transverse_both"] else "clean")
        else:
            rec.update(verdict="error", alarms_xyz=[])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    json.dump(rec, open(f, "w"))
    return rec


def seamcheck(nm):
    f = DET / "seamcheck" / f"{nm}.json"
    if f.exists():
        return json.load(open(f))
    f.parent.mkdir(parents=True, exist_ok=True)
    raw = f.with_suffix(".raw.json")
    p = subprocess.run([str(SC_PY), str(HERE / "seamcheck_run.py"), str(geom.DATA / "unverified_patches" / nm), str(raw)],
                       capture_output=True, text=True)
    rec = dict(tool="seamcheck", patch=nm, returncode=p.returncode, stderr=p.stderr.strip()[-300:])
    if raw.exists():
        r = json.load(open(raw))
        raw.unlink()
        # a verdict exists unless SPARSE; alarms = flagged steps of a REVIEW / WATCH patch (uncapped)
        rec.update(verdict=r["verdict"], coverage=r["coverage"], ratio=r["ratio"], flagged=r["flagged"],
                   spots_capped=r["spots_capped"], winding_verdict=r["winding_verdict"],
                   alarms_xyz=[s["xyz"] for s in r["flagged_steps"]] if r["verdict"] in ("REVIEW", "WATCH") else [])
    else:
        rec.update(verdict="error", alarms_xyz=[])
    json.dump(rec, open(f, "w"))
    return rec


def annot1621(nm, P, N):
    f = DET / "annot1621" / f"{nm}.json"
    if f.exists():
        return json.load(open(f))
    f.parent.mkdir(parents=True, exist_ok=True)
    r = annot.check_1621(P, N)
    rec = dict(tool="#1621-style", patch=nm, pairs=r["pairs"], n_attached=r["n_attached"],
               alarms=[{k: (list(v) if isinstance(v, tuple) else v) for k, v in a.items()} for a in r["alarms"]])
    json.dump(rec, open(f, "w"), default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    return rec


GROUPS = ("fast", "wa_default", "wa_intended")


def run_patch(nm, groups=GROUPS):
    d = geom.DATA / "unverified_patches" / nm
    P = geom.load_tifxyz(d)
    N = geom.orient_outward(P, geom.grid_normals(P))
    if "fast" in groups:
        doctor_v1.run(nm)
        windcheck_default(nm)
        windcheck_patchmode(nm)
        annot1621(nm, P, N)
        seamcheck(nm)
    if "wa_default" in groups:
        run_windaudit_v1.run(nm, P, N, "default")
    if "wa_intended" in groups:
        run_windaudit_v1.run(nm, P, N, "intended")


def run_all(names, groups=GROUPS):
    for i, nm in enumerate(names):
        try:
            run_patch(nm, groups)
        except Exception as e:  # recorded, never silent
            (DET / "errors").mkdir(parents=True, exist_ok=True)
            json.dump(dict(patch=nm, error=repr(e)), open(DET / "errors" / f"{nm}.json", "w"))
            print("ERROR", nm, repr(e), flush=True)
        if (i + 1) % 25 == 0:
            print("detectors", i + 1, "/", len(names), flush=True)


if __name__ == "__main__":
    # python -m tools.switchbench.detectors_v1 GROUP[,GROUP] name... | GROUP[,GROUP] @file
    groups = tuple(sys.argv[1].split(","))
    assert set(groups) <= set(GROUPS), groups
    names = sys.argv[2:]
    if len(names) == 1 and names[0].startswith("@"):
        names = [x for x in open(names[0][1:]).read().split() if x]
    run_all(names, groups)

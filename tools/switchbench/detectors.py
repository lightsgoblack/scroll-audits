"""Run the public detectors (default parameters only) on corpus patches and collect alarm locations.

tifxyz-doctor 0.2.0 (aviad12g/tifxyz-doctor @5ca0444): `audit --json` only (no --html/--overlay, so
  no images). Primary alarms: `coherent-normal-step` candidate edges (the cue whose planted recall is
  published). Secondary: union of every localized review-cue example.
windcheck (joe-carr-data/windcheck @2b0fb2f, selfcross engine built from source with clang++):
  `check` -> transverse self-contact sites.
Alarms are grid cells (r, c); matching to events is by 3D distance in metrics.py.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from . import geom

EXT = Path("/home/user/ext")
OUT = geom.DATA / "detect"
TD = EXT / "tifxyz-doctor" / ".venv" / "bin" / "tifxyz-doctor"
WC = EXT / "windcheck"


def tifxyz_doctor(nm: str) -> dict:
    f = OUT / "tifxyz_doctor" / f"{nm}.json"
    if f.exists():
        return json.load(open(f))
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".raw.json")
    d = geom.DATA / "unverified_patches" / nm
    p = subprocess.run([str(TD), "audit", str(d), "--json", str(tmp)], capture_output=True, text=True)
    rec = dict(tool="tifxyz-doctor", patch=nm, returncode=p.returncode, stdout=p.stdout.strip()[-300:])
    if tmp.exists():
        a = json.load(open(tmp))
        g = a.get("geometry", {})
        codes = [x["code"] for x in a.get("findings", []) if x.get("level") == "review"]
        rc = lambda lst: [x["rc"] for x in lst if isinstance(x, dict) and "rc" in x]
        # a cue alarms only when its review finding is emitted; locations = that cue's examples
        cue_ex = {
            "coherent-normal-step": rc(g.get("coherent_normal_steps", {}).get("candidate_edge_examples", [])),
            "normal-jumps": rc(g.get("normal_jumps", {}).get("jump_examples", []))
            + rc(g.get("normal_jumps", {}).get("orientation_flip_examples", [])),
            "folded-quads": rc(g.get("folded_quad_examples", [])),
            "degenerate-triangles": rc(g.get("degenerate_triangle_examples", [])),
            "triangulation-sensitive": rc(g.get("triangulation_sensitive_examples", [])),
            "long-edges": rc(g.get("long_edge_examples", [])),
            "short-edges": rc(g.get("short_edge_examples", [])),
            "anisotropic-cells": rc(g.get("high_condition_examples", [])) + rc(g.get("high_shear_examples", []))
            + rc(g.get("high_symmetric_stretch_examples", [])) + rc(g.get("high_symmetric_dirichlet_examples", []))
            + rc(g.get("high_area_ratio_examples", [])) + rc(g.get("low_area_ratio_examples", [])),
        }
        anyc = [x for c in codes for x in cue_ex.get(c, [])]
        unlocalized = [c for c in codes if not cue_ex.get(c)]
        rec.update(findings=codes, alarms_primary=cue_ex["coherent-normal-step"] if "coherent-normal-step" in codes else [],
                   alarms_any=anyc, unlocalized_review_codes=unlocalized,
                   cns_components=g.get("coherent_normal_steps", {}).get("coherent_components"))
        tmp.unlink()
    json.dump(rec, open(f, "w"))
    return rec


def windcheck(nm: str) -> dict:
    f = OUT / "windcheck" / f"{nm}.json"
    if f.exists():
        return json.load(open(f))
    f.parent.mkdir(parents=True, exist_ok=True)
    out = OUT / "windcheck_raw" / nm
    d = geom.DATA / "unverified_patches" / nm
    p = subprocess.run(["uv", "run", "--project", str(WC), "windcheck", "check", str(d), "--out", str(out)],
                       capture_output=True, text=True, cwd=WC)
    rec = dict(tool="windcheck", patch=nm, returncode=p.returncode, stdout=(p.stdout + p.stderr).strip()[-400:])
    alarms = []
    if out.exists():
        for pf in out.glob("*_points.json"):
            pc = json.load(open(pf))
            for c in pc.get("collections", {}).values():
                for pt in c.get("points", {}).values():
                    alarms.append(pt["p"])
        rec["files"] = sorted(x.name for x in out.iterdir())
    rec["alarms_xyz"] = alarms
    rec["verdict"] = ("no_verdict" if "below the census validity threshold" in rec["stdout"]
                      else ("clean" if not alarms and p.returncode == 0 else ("alarm" if alarms else "error")))
    json.dump(rec, open(f, "w"))
    return rec


def run_all(names):
    for i, nm in enumerate(names):
        tifxyz_doctor(nm)
        windcheck(nm)
        if (i + 1) % 25 == 0:
            print("detectors", i + 1, "/", len(names), flush=True)


if __name__ == "__main__":
    names = [json.load(open(f))["patch"] for f in sorted((geom.DATA / "corpus").glob("*.json"))
             if json.load(open(f)).get("in_sample")]
    run_all(names if len(sys.argv) < 2 else sys.argv[1:])

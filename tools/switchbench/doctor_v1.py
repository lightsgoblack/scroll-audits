"""SwitchBench v1: tifxyz-doctor uncapped (protocol P1 (prereg/switchbench_v1.md) "tifxyz-doctor runs uncapped").

The doctor's CLI cannot raise its per-cue example cap (hard-coded), so doctor_wrap.py runs the
unmodified default CLI path in the doctor's own venv and captures, without changing any computation,
the public API's internal arrays (audit_mesh(...)["_arrays"]) plus the complete flagged set behind every
capped example list. Definitions (lead/reviewer post-freeze call 2026-09-26, Scout Report #8, fixed
before any v1 result):
  alarms_primary  (PRIMARY) = coherent_normal_step_cells mask  UNION  CLI coherent-normal-step examples
  mask_primary              = coherent_normal_step_cells mask only (what the tool's 124/128 was scored on)
  alarms_primary_capped     = CLI examples only (v0's definition, D10; recomputed from the public report)
  alarms_primary_alledges   = every flagged candidate edge (the complete list the examples are cut from)
  alarms_any (union)        = review_cue_mask  UNION  CLI examples of every emitted review cue
  mask_any / alarms_any_capped / alarms_any_allflagged: the corresponding variants for "any cue"
Each recorded call is mapped to its review code (fixed by the pinned source, 5ca0444) and every count is
checked against the tool's own public report (a mismatch raises). Per cue: n_full, n_examples, capped.
Alarm locations stay grid indices; metrics maps them to 3-D as v0 (metrics.cells_to_xyz).
"""
from __future__ import annotations

import os

import json
import subprocess
import sys
from pathlib import Path

from . import geom

TD_PY = Path(os.environ.get("SWITCHBENCH_EXT", "ext") + "/tifxyz-doctor/.venv/bin/python")
WRAP = Path(__file__).with_name("doctor_wrap.py")
OUT = geom.REPO / "data" / "switchbench_v1" / "detect" / "tifxyz_doctor"

# (calling function, call order) -> review code, from the pinned source (audit.py @5ca0444)
CALL_CODE = {
    ("_normal_jump_metrics", 0): "normal-jumps", ("_normal_jump_metrics", 1): "normal-jumps",
    ("_normal_jump_metrics", 2): "normal-jumps", ("_normal_jump_metrics", 3): "normal-jumps",  # flips
    ("_coherent_normal_step_metrics", 0): "coherent-normal-step",
    ("_coherent_normal_step_metrics", 1): "coherent-normal-step",
    ("audit_mesh", 0): "long-edges", ("audit_mesh", 1): "long-edges",
    ("audit_mesh", 2): "short-edges", ("audit_mesh", 3): "short-edges",
    ("audit_mesh", 4): "degenerate-triangles", ("audit_mesh", 5): "degenerate-triangles",
    ("audit_mesh", 6): "folded-quads", ("audit_mesh", 7): "triangulation-sensitive",
    ("audit_mesh", 8): "anisotropic-cells", ("audit_mesh", 9): "symmetric-stretch",
    ("audit_mesh", 10): "area-distortion", ("audit_mesh", 11): "area-distortion",
    ("audit_mesh", 12): "high-shear", ("audit_mesh", 13): "high-distortion",
}
# public-report example lists per code (for the capped count and the v0-style recomputation)
PUBLIC_EX = {
    "coherent-normal-step": [("coherent_normal_steps", "candidate_edge_examples")],
    "normal-jumps": [("normal_jumps", "jump_examples"), ("normal_jumps", "orientation_flip_examples")],
    "long-edges": [(None, "long_edge_examples")], "short-edges": [(None, "short_edge_examples")],
    "degenerate-triangles": [(None, "degenerate_triangle_examples")],
    "folded-quads": [(None, "folded_quad_examples")],
    "triangulation-sensitive": [(None, "triangulation_sensitive_examples")],
    "anisotropic-cells": [(None, "high_condition_examples")],
    "symmetric-stretch": [(None, "high_symmetric_stretch_examples")],
    "area-distortion": [(None, "low_area_ratio_examples"), (None, "high_area_ratio_examples")],
    "high-shear": [(None, "high_shear_examples")],
    "high-distortion": [(None, "high_symmetric_dirichlet_examples")],
}


def _examples(g, code):
    out = []
    for sub, key in PUBLIC_EX.get(code, []):
        lst = (g.get(sub, {}) if sub else g).get(key, [])
        out += [x["rc"] for x in lst if isinstance(x, dict) and "rc" in x]
    return out


def v0_style(a):
    """v0 detectors.tifxyz_doctor alarm definition, recomputed from a public report (for S4)."""
    g = a.get("geometry", {})
    codes = [x["code"] for x in a.get("findings", []) if x.get("level") == "review"]
    rc = lambda lst: [x["rc"] for x in lst if isinstance(x, dict) and "rc" in x]
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
    return codes, (cue_ex["coherent-normal-step"] if "coherent-normal-step" in codes else []), anyc


def _check_counts(g, full, prox_n, pub):
    n = lambda code: len(full.get(code, []))
    want = {
        "coherent-normal-step": g["coherent_normal_steps"]["candidate_edges"],
        "normal-jumps": g["normal_jumps"]["jumps_above_threshold"] + g["normal_jumps"]["orientation_flips"],
        "long-edges": g["long_edges"], "short-edges": g["short_edges"],
        "degenerate-triangles": g["degenerate_triangles"], "folded-quads": g["folded_quads"],
        "triangulation-sensitive": g["triangulation_sensitive_quads"],
        "anisotropic-cells": g["high_condition_cells"], "symmetric-stretch": g["high_symmetric_stretch_cells"],
        "area-distortion": g["high_area_distortion_cells"], "high-shear": g["high_shear_cells"],
        "high-distortion": g["high_symmetric_dirichlet_cells"],
    }
    bad = {k: (n(k), v) for k, v in want.items() if n(k) != v}
    if bad:
        raise RuntimeError(f"doctor wrapper call->code mapping disagrees with the public report: {bad}")
    if pub.get("nonlocal_proximity", {}).get("pair_count", 0) > 0 and not prox_n:
        raise RuntimeError("proximity pairs reported but no proximity vertices captured")


def run(nm: str, patch_dir: Path | None = None) -> dict:
    f = OUT / f"{nm}.json"
    if f.exists():
        return json.load(open(f))
    OUT.mkdir(parents=True, exist_ok=True)
    d = patch_dir or (geom.DATA / "unverified_patches" / nm)
    pub_f, side_f = f.with_suffix(".pub.json"), f.with_suffix(".side.json")
    p = subprocess.run([str(TD_PY), str(WRAP), str(d), str(pub_f), str(side_f)], capture_output=True, text=True)
    rec = dict(tool="tifxyz-doctor", commit="5ca0444", mode="default CLI, uncapped via doctor_wrap.py",
               patch=nm, returncode=p.returncode, stderr=p.stderr.strip()[-300:])
    if not (pub_f.exists() and side_f.exists()):
        rec["verdict"] = "error"
        json.dump(rec, open(f, "w"))
        return rec
    a = json.load(open(pub_f))
    s = json.load(open(side_f))
    g = a.get("geometry", {})
    full = {}
    for c in s["calls"]:
        code = CALL_CODE.get((c["func"], c["order"]))
        if code is None:
            raise RuntimeError(f"unmapped _top_locations call {c['func']}#{c['order']}")
        full.setdefault(code, []).extend(c["rc"])
    prox = s.get("proximity_vertices") or []
    _check_counts(g, full, len(prox), a)
    if prox:
        full["nonlocal-proximity"] = prox
    codes, prim_c, any_c = v0_style(a)
    cues = {}
    for code, lst in full.items():
        nex = len(_examples(g, code)) if code != "nonlocal-proximity" else len(a["nonlocal_proximity"].get("pairs", []))
        cues[code] = dict(n_full=len(lst), n_examples=nex, emitted=code in codes,
                          capped=(len(lst) > nex) if code != "nonlocal-proximity"
                          else bool(a["nonlocal_proximity"].get("pairs_truncated")))
    any_full = [x for c in codes for x in full.get(c, [])]
    arrs = s.get("arrays", {})
    mask_p = arrs.get("coherent_normal_step_cells", [])
    mask_a = arrs.get("review_cue_mask", [])
    union = lambda a, b: [list(x) for x in dict.fromkeys([tuple(x) for x in a] + [tuple(x) for x in b])]
    rec.update(findings=codes,
               config_equals_api_default=s.get("config_equals_api_default"),
               alarms_primary_capped=prim_c, alarms_any_capped=any_c,
               mask_primary=mask_p, mask_any=mask_a,
               alarms_primary=union(mask_p, prim_c), alarms_any=union(mask_a, any_c),
               alarms_primary_alledges=full.get("coherent-normal-step", []) if "coherent-normal-step" in codes else [],
               alarms_any_allflagged=any_full,
               cues=cues,
               capped_emitted_cues=sorted(c for c, v in cues.items() if v["emitted"] and v["capped"]),
               unlocalized_review_codes=[c for c in codes if c not in full],
               cns_components=g.get("coherent_normal_steps", {}).get("coherent_components"),
               verdict="alarm" if (mask_a or any_c) else "clean")
    if s.get("config_equals_api_default") is not True:
        raise RuntimeError("CLI config differs from AuditConfig() defaults")
    json.dump(rec, open(f, "w"))
    pub_f.unlink()
    side_f.unlink()
    return rec


if __name__ == "__main__":
    for nm in sys.argv[1:]:
        r = run(nm)
        print(nm, r.get("verdict"), {k: len(r.get(k, [])) for k in ("alarms_primary_capped", "mask_primary",
              "alarms_primary", "alarms_primary_alledges", "alarms_any_capped", "mask_any", "alarms_any")},
              r.get("capped_emitted_cues"))

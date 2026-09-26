"""windaudit (sergeievland/windaudit @aba5633) patch-graph audit applied to corpus patches.

windaudit's documented `windaudit run` audits annotations only and never reads a trace, so it cannot see
a switch inside an unverified patch. Its patch-graph harness (scripts/wide_patch_audit.py, run as in
scripts/reproduce_wide.sh with WIDE_ATTACHMENT_GAP=1, the corrected construction its README reports) is
the mode that reads surfaces. It is run unchanged (default band 6000-18000, tolerance 2.5 vx, erosion 1)
on a folder holding the unverified patch plus every verified patch whose bbox lies within 300 vx.
A patch can only enter an inconsistent cycle if >= 2 annotation points attach to it; patches with fewer
are reported as structurally silent (no alarm) without running.
Alarm on the unverified patch U = the corrected solver ('after') edits an edge incident to U, or U lies
on an initially inconsistent non-tree edge. Alarm location = U's attachment points of that edge.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import numpy as np

from . import annot, geom

WA = "/home/user/ext/windaudit"
OUT = geom.DATA / "detect" / "windaudit"


def run(nm, P, N):
    f = OUT / f"{nm}.json"
    if f.exists():
        return json.load(open(f))
    OUT.mkdir(parents=True, exist_ok=True)
    att = annot.attach(P, N)
    rec = dict(tool="windaudit", patch=nm, n_attached=len(att), alarms_xyz=[])
    if len(att) < 2:
        rec["verdict"] = "silent: fewer than 2 annotation points attach"
        json.dump(rec, open(f, "w"))
        return rec
    vi = geom.VerifiedIndex()
    lo = np.nanmin(P.reshape(-1, 3), 0); hi = np.nanmax(P.reshape(-1, 3), 0)
    from .sanity import lineage
    lin = lineage(nm)
    names = [v for v in vi.overlapping(lo, hi, pad=300.0) if lineage(v) != lin]  # same-lineage excluded, as in labeling
    tmp = geom.DATA / "detect" / "windaudit_tmp" / nm
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    os.symlink(geom.DATA / "unverified_patches" / nm, tmp / nm)
    for v in names:
        os.symlink(geom.DATA / "verified_patches" / v, tmp / v)
    out = geom.DATA / "detect" / "windaudit_out" / nm
    env = dict(os.environ, WIDE_ATTACHMENT_GAP="1")
    p = subprocess.run([f"{WA}/.venv/bin/python", "scripts/wide_patch_audit.py", str(tmp),
                        "upstream/villa/find_inconsistent_windings.py",
                        "out/wide_solver/spiral-fitting/find_inconsistent_windings.py", str(out), str(geom.DATA)],
                       cwd=WA, env=env, capture_output=True, text=True, timeout=3600)
    rec.update(returncode=p.returncode, n_verified_in_folder=len(names), tail=(p.stdout + p.stderr)[-600:])
    if p.returncode != 0 or not (out / "measured_edges.json").exists():
        rec["verdict"] = "error"
        json.dump(rec, open(f, "w"))
        return rec
    edges = json.load(open(out / "measured_edges.json"))
    after = json.load(open(out / "after_full.json"))
    changed = {(e["rel_pcl_id"], frozenset((e["from_point_id"], e["to_point_id"]))) for e in after.get("edges", [])}
    hits = []
    for e in edges:
        key = (e["pcl_id"], frozenset((e["from_point_id"], e["to_point_id"])))
        if key in changed and nm in (e["P"], e["R"]):
            ij = e["from_ij"] if e["P"] == nm else e["to_ij"]
            i, j = int(np.floor(ij[0])), int(np.floor(ij[1]))
            if 0 <= i < P.shape[0] and 0 <= j < P.shape[1] and np.isfinite(P[i, j]).all():
                hits.append(P[i, j].tolist())
    init = json.load(open(out / "initial_graph.json"))
    rec.update(verdict="alarm" if hits else "clean", alarms_xyz=hits,
               initial_inconsistent=init.get("inconsistent_non_tree_edges"),
               u_in_graph=any(nm in (e["P"], e["R"]) for e in edges))
    shutil.rmtree(tmp)
    json.dump(rec, open(f, "w"))
    return rec


if __name__ == "__main__":
    for nm in sys.argv[1:]:
        d = geom.DATA / "unverified_patches" / nm
        P = geom.load_tifxyz(d)
        N = geom.orient_outward(P, geom.grid_normals(P))
        print(json.dumps(run(nm, P, N))[:400])

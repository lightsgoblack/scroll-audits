"""windcheck (joe-carr-data/windcheck @2b0fb2f) in its author-documented small-patch mode.

Run inside windcheck's own environment:
  uv run --project $SWITCHBENCH_EXT (default ./ext)/windcheck python wc_patchmode.py <patch_dir> <work_dir> <out_json>

windcheck's `check` refuses surfaces under 5,000 valid cells ("census validity threshold"). Its docs
(docs/PATCH-AUDIT.md, bench/patch_audit.py:audit_one) census small verified patches by calling the
engine directly with no cell floor, both triangulations, threads=1, default CENSUS parameters; the
smallest patch in that published census had 164 valid cells. This script is that call, unchanged,
plus the location of each transverse contact (centre of both participating quads, from the tool's
own surface reader). Numeric output only.
"""
import json
import sys
from pathlib import Path

import numpy as np
from windcheck import pipeline, tifxyz


def quad_xyz(s, v, u):
    pts = [s.points[vv, uu] for vv in (v, v + 1) for uu in (u, u + 1)
           if vv < s.shape[0] and uu < s.shape[1] and s.valid[vv, uu]]
    return np.mean(pts, 0).astype(float).tolist() if pts else None


if __name__ == "__main__":
    mesh, work, out = (Path(a) for a in sys.argv[1:4])
    s = tifxyz.read(mesh)
    nv, nu = s.shape
    rec = {"grid": [int(nv), int(nu)], "n_valid": s.n_valid, "n_valid_upstream_rule": s.n_valid_pipeline,
           "mode": "bench/patch_audit.py audit_one (no cell floor)"}
    contacts = []
    for d in (0, 1):
        csv, counts = pipeline.run_engine(mesh, mesh.name, work, d, {"threads": 1})
        rec[f"d{d}"] = counts
        for r in pipeline.parse_census_csv(csv, d, nv, nu)["rows"]:
            if r["verdict"] == "transverse":
                contacts.append(dict(diag=d, q1=list(r["q1"]), q2=list(r["q2"]),
                                     xyz1=quad_xyz(s, *r["q1"]), xyz2=quad_xyz(s, *r["q2"])))
        csv.unlink(missing_ok=True)
    rec["transverse_both"] = int(rec["d0"]["transverse"] + rec["d1"]["transverse"])
    rec["contacts"] = contacts
    rec["clean"] = rec["transverse_both"] == 0
    json.dump(rec, open(out, "w"))

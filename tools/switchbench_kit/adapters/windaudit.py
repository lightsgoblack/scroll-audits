"""Adapter for sergeievland/windaudit.

In plain English: windaudit compares the scroll's "before" and "after" solved winding-number graphs.
An alarm is an edge touching your patch that changed between the two -- a sign the patch may be
attached to the wrong neighbour. This reads windaudit's own output folder (measured_edges.json,
after_full.json) for one patch and turns each such edge into an x/y/z alarm point, using the patch's
own tifxyz files (needs --patches-dir) to look up that grid cell's coordinates.

Reuses the exact hit rule of tools.switchbench.run_windaudit_v1.run: an edge from `measured_edges.json`
that touches this patch (`P` or `R` == patch name) counts if its (pcl_id, {from,to}_point_id) key also
appears among `after_full.json`'s edges; the alarm point is this patch's own grid cell of that edge.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from .common import AdapterError, iter_patch_inputs, load_json, write_alarms


def alarms_for_patch(nm: str, out_dir: Path, P: np.ndarray) -> list:
    edges_f, after_f = Path(out_dir) / "measured_edges.json", Path(out_dir) / "after_full.json"
    if not (edges_f.exists() and after_f.exists()):
        raise AdapterError(f"{out_dir}: expected measured_edges.json and after_full.json (windaudit's own output)")
    edges = load_json(edges_f)
    after = load_json(after_f)
    changed = {(e["rel_pcl_id"], frozenset((e["from_point_id"], e["to_point_id"]))) for e in after.get("edges", [])}
    hits = []
    for e in edges:
        key = (e["pcl_id"], frozenset((e["from_point_id"], e["to_point_id"])))
        if key in changed and nm in (e["P"], e["R"]):
            ij = e["from_ij"] if e["P"] == nm else e["to_ij"]
            i, j = int(np.floor(ij[0])), int(np.floor(ij[1]))
            if 0 <= i < P.shape[0] and 0 <= j < P.shape[1] and np.isfinite(P[i, j]).all():
                hits.append(P[i, j].tolist())
    return hits


def run(native_path: str, out: str, patches_dir: str, mode: str = "default", patch: str | None = None) -> dict:
    from tools.switchbench import geom  # heavy import (tifffile); kept local so `adapt --help` stays cheap
    alarms = {}
    for nm, d in iter_patch_inputs(Path(native_path), "dir"):
        pid = patch or nm
        P = geom.load_tifxyz(Path(patches_dir) / pid)
        alarms[pid] = alarms_for_patch(pid, d, P)
    write_alarms(alarms, out, detector=f"windaudit ({mode})", fmt="xyz")
    return alarms


def add_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--patches-dir", required=True, help="root of <patch_id>/{x,y,z}.tif (tifxyz patches)")
    ap.add_argument("--mode", default="default", choices=["default", "intended"],
                    help="label only (both modes parse the same windaudit output shape)")
    ap.add_argument("--patch", default=None, help="patch id, if native_output_path is a single patch's output dir")

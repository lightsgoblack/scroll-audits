"""Adapter for aviad12g/tifxyz-doctor.

In plain English: tifxyz-doctor prints a JSON "audit report" listing everything odd it found on a
patch. This reads that report (either straight from `tifxyz-doctor audit <patch> --json <out>`, or a
"side" file of its API's internal arrays, see below) and pulls out just the locations of one specific
warning -- "coherent-normal-step", the cue whose recall on planted switches is published -- as grid
cells for the kit to score.

Two modes, both reusing the exact parsing of the harness that produced every v0/v1 number:
  cli (default)  same as tools.switchbench.detectors.tifxyz_doctor: alarms = the report's own capped
                 "coherent-normal-step" example list (`--json` output only, no extra call).
  api-mask       same as tools.switchbench.doctor_v1.run's "alarms_primary": the union of the report's
                 example list with the boolean `coherent_normal_step_cells` mask from the tool's public
                 API (`audit_mesh(...)["_arrays"]`), which doctor_wrap.py in that module captures to a
                 "side" JSON ({"arrays": {"coherent_normal_step_cells": [[r, c], ...]}}). Needs --side.

Alarms are grid cells [row, col] (kit alarms "format b"); score with --patches-dir so the kit can turn
them into 3-D points.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .common import AdapterError, iter_patch_inputs, load_json, write_alarms


def _rc(lst):
    return [x["rc"] for x in lst if isinstance(x, dict) and "rc" in x]


def cue_examples(report: dict) -> list:
    """v0 tools.switchbench.detectors.tifxyz_doctor: coherent-normal-step alarms = that cue's example
    list, only when the review finding was actually emitted."""
    g = report.get("geometry", {})
    codes = [x["code"] for x in report.get("findings", []) if x.get("level") == "review"]
    if "coherent-normal-step" not in codes:
        return []
    return _rc(g.get("coherent_normal_steps", {}).get("candidate_edge_examples", []))


def alarms_for_patch(report: dict, side: dict | None) -> list:
    examples = cue_examples(report)
    if side is None:
        return examples
    mask = side.get("arrays", {}).get("coherent_normal_step_cells", [])
    seen = {tuple(x) for x in examples}
    out = [list(x) for x in examples]
    for c in mask:
        t = tuple(c)
        if t not in seen:
            seen.add(t)
            out.append(list(c))
    return out


def run(native_path: str, out: str, side: str | None = None, mode: str = "cli", patch: str | None = None) -> dict:
    if mode not in ("cli", "api-mask"):
        raise AdapterError("mode must be 'cli' or 'api-mask'")
    if mode == "api-mask" and not side:
        raise AdapterError("--side is required for --mode api-mask (doctor_wrap.py's side JSON)")
    side_by_patch = {}
    if side:
        for nm, p in iter_patch_inputs(Path(side), "file"):
            side_by_patch[nm] = load_json(p)
    alarms = {}
    for nm, p in iter_patch_inputs(Path(native_path), "file"):
        report = load_json(p)
        alarms[patch or nm] = alarms_for_patch(report, side_by_patch.get(patch or nm) if mode == "api-mask" else None)
    write_alarms(alarms, out, detector="tifxyz-doctor", fmt="grid")
    return alarms


def add_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--side", default=None, help="dir/file of doctor_wrap.py 'side' JSON (for --mode api-mask)")
    ap.add_argument("--mode", default="cli", choices=["cli", "api-mask"])
    ap.add_argument("--patch", default=None, help="patch id, if native_output_path is a single-patch file")

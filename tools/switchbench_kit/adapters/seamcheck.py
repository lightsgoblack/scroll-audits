"""Adapter for hwkim3330/seamcheck.

In plain English: seamcheck looks for sudden jumps between neighbouring grid rows/columns of a patch
and gives it an overall verdict (OK / WATCH / REVIEW / SPARSE). This reads its own output (as written
by tools/switchbench/seamcheck_run.py, which just calls seamcheck's `check()` and its own
`neighbour_steps()` with no changes) and lists the flagged step locations as x/y/z alarms, but only
when the patch's verdict is REVIEW or WATCH (a SPARSE/OK patch has no alarms) -- the same rule as
tools.switchbench.detectors_v1.seamcheck.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .common import iter_patch_inputs, load_json, write_alarms

ALARM_VERDICTS = ("REVIEW", "WATCH")


def alarms_for_patch(raw: dict) -> list:
    if raw.get("verdict") not in ALARM_VERDICTS:
        return []
    return [s["xyz"] for s in raw.get("flagged_steps", [])]


def run(native_path: str, out: str, patch: str | None = None) -> dict:
    alarms = {}
    for nm, p in iter_patch_inputs(Path(native_path), "file"):
        alarms[patch or nm] = alarms_for_patch(load_json(p))
    write_alarms(alarms, out, detector="seamcheck", fmt="xyz")
    return alarms


def add_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--patch", default=None, help="patch id, if native_output_path is a single-patch file")

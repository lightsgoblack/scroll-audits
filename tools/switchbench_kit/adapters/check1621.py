"""Adapter for the #1621-style annotation check (tools/switchbench/annot.py: check_1621).

In plain English: this check looks at pairs of annotation points that should land on the same spot of
the scroll and flags pairs whose winding counts disagree. This reads that check's own JSON output (as
written by tools/switchbench/detectors_v1.py: annot1621, which is exactly `annot.check_1621(P, N)`
serialized) and lists both points of every flagged pair as x/y/z alarms -- the same rule
tools.switchbench.detectors_v1.annot1621 records under "alarms".
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .common import iter_patch_inputs, load_json, write_alarms


def alarms_for_patch(raw: dict) -> list:
    alarms = raw.get("alarms", [])
    out = []
    for a in alarms:
        if a.get("xyz_p") is not None:
            out.append(a["xyz_p"])
        if a.get("xyz_q") is not None:
            out.append(a["xyz_q"])
    return out


def run(native_path: str, out: str, patch: str | None = None) -> dict:
    alarms = {}
    for nm, p in iter_patch_inputs(Path(native_path), "file"):
        alarms[patch or nm] = alarms_for_patch(load_json(p))
    write_alarms(alarms, out, detector="#1621-style", fmt="xyz")
    return alarms


def add_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--patch", default=None, help="patch id, if native_output_path is a single-patch file")

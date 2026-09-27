"""Adapter for joe-carr-data/windcheck.

In plain English: windcheck writes one folder per patch full of "*_points.json" files listing every
place its self-crossing check flagged. This walks that folder and lists the flagged points as x/y/z
alarms.

Two modes, mirroring the two ways v0/v1 ran windcheck:
  default  same as tools.switchbench.detectors.windcheck: `windcheck check <patch> --out <dir>`'s
           output folder; alarms = every point in every "*_points.json"'s collections.
  patch    same as tools.switchbench.wc_patchmode.py (bench/patch_audit.py audit_one, no cell-count
           floor): the raw JSON it writes; alarms = the transverse contacts' xyz1/xyz2 centres.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .common import iter_patch_inputs, load_json, write_alarms


def default_points(patch_dir: Path) -> list:
    alarms = []
    for pf in sorted(Path(patch_dir).glob("*_points.json")):
        pc = load_json(pf)
        for c in pc.get("collections", {}).values():
            for pt in c.get("points", {}).values():
                alarms.append(pt["p"])
    return alarms


def patch_mode_contacts(raw: dict) -> list:
    alarms = []
    for c in raw.get("contacts", []):
        for k in ("xyz1", "xyz2"):
            if c.get(k) is not None:
                alarms.append(c[k])
    return alarms


def run(native_path: str, out: str, mode: str = "default", patch: str | None = None) -> dict:
    alarms = {}
    if mode == "default":
        for nm, d in iter_patch_inputs(Path(native_path), "dir"):
            alarms[patch or nm] = default_points(d)
    elif mode == "patch":
        for nm, p in iter_patch_inputs(Path(native_path), "file"):
            alarms[patch or nm] = patch_mode_contacts(load_json(p))
    else:
        raise ValueError("mode must be 'default' or 'patch'")
    write_alarms(alarms, out, detector=f"windcheck ({mode})", fmt="xyz")
    return alarms


def add_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--mode", default="default", choices=["default", "patch"],
                    help="'default' reads a windcheck check --out folder; 'patch' reads wc_patchmode.py's raw JSON")
    ap.add_argument("--patch", default=None, help="patch id, if native_output_path is a single patch's output")

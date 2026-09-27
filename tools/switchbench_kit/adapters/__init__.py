"""One-command converters: a public detector's own NATIVE output -> the kit's alarms JSON
({"<patch_id>": [[x,y,z], ...]} or {"<patch_id>": [[row,col], ...]}).

In plain English: each public sheet-switch checker prints its results in its own private format.
These adapters read that raw output (unchanged, no re-running the tool) and rewrite it as the one
alarms format the SwitchBench kit understands, so you can score any of them with
`python -m tools.switchbench_kit score`. The parsing rules are copied from the exact code that scored
each tool for the v0/v1 leaderboards (tools/switchbench/detectors_v1.py, doctor_v1.py,
run_windaudit_v1.py, seamcheck_run.py, wc_patchmode.py) so an adapted file scores the same alarms.

CLI: python -m tools.switchbench_kit adapt <tool> <native_output_path> --out alarms.json
  <tool> is one of: tifxyz-doctor, windcheck, windcheck-patch, windaudit, seamcheck, check1621
"""
from __future__ import annotations

from .common import AdapterError  # noqa: F401 (re-exported)

TOOLS = ("tifxyz-doctor", "windcheck", "windaudit", "seamcheck", "check1621")

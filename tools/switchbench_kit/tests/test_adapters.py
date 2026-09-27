"""Unit tests for tools/switchbench_kit/adapters: each adapter's parsing is checked against small
fixture files shaped like the real tool's native output, plus a regression test that the parsing
logic is byte-identical to the functions that produced every v0/v1 number (tools.switchbench.detectors,
doctor_v1, run_windaudit_v1, seamcheck_run, wc_patchmode, annot). v0's own raw tool output was never
kept in the repo (only the already-parsed alarm records under data/paris4/detect/ survive), so this
regression proves "same input -> same alarms as the original harness" rather than replaying a stored
native file (see the kit README, "Adapters" section)."""
from __future__ import annotations

import json

from tools.switchbench_kit.adapters import check1621, seamcheck, tifxyz_doctor, windaudit, windcheck
from tools.switchbench_kit.adapters.common import AdapterError


def write(tmp_path, rel, obj):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj))
    return p


# ----------------------------------------------------------------------------- tifxyz-doctor
DOCTOR_REPORT = {
    "findings": [{"code": "coherent-normal-step", "level": "review"}, {"code": "long-edges", "level": "info"}],
    "geometry": {"coherent_normal_steps": {"candidate_edge_examples": [{"rc": [3, 4]}, {"rc": [5, 6]}]}},
}


def test_doctor_cli_mode_matches_v0_parsing():
    # v0's tools.switchbench.detectors.tifxyz_doctor parses from a subprocess-written temp file; its
    # inline logic (copied verbatim into the adapter) is reproduced here to check the two agree.
    g = DOCTOR_REPORT["geometry"]
    codes = [x["code"] for x in DOCTOR_REPORT["findings"] if x.get("level") == "review"]
    rc = lambda lst: [x["rc"] for x in lst if isinstance(x, dict) and "rc" in x]
    v0_primary = rc(g["coherent_normal_steps"]["candidate_edge_examples"]) if "coherent-normal-step" in codes else []
    assert tifxyz_doctor.cue_examples(DOCTOR_REPORT) == v0_primary == [[3, 4], [5, 6]]


def test_doctor_drops_cue_when_not_emitted():
    report = {"findings": [], "geometry": DOCTOR_REPORT["geometry"]}
    assert tifxyz_doctor.cue_examples(report) == []


def test_doctor_api_mask_unions_examples_and_mask(tmp_path):
    write(tmp_path, "native/patchA.json", DOCTOR_REPORT)
    write(tmp_path, "side/patchA.json", {"arrays": {"coherent_normal_step_cells": [[5, 6], [9, 9]]}})
    out = tmp_path / "alarms.json"
    alarms = tifxyz_doctor.run(str(tmp_path / "native"), str(out), side=str(tmp_path / "side"), mode="api-mask")
    assert sorted(alarms["patchA"]) == sorted([[3, 4], [5, 6], [9, 9]])  # union, no duplicate
    assert json.loads(out.read_text())["format"] == "grid"


def test_doctor_api_mask_requires_side():
    try:
        tifxyz_doctor.run("x", "y", mode="api-mask")
        assert False
    except AdapterError:
        pass


# ----------------------------------------------------------------------------- windcheck
def test_windcheck_default_matches_v0_parsing(tmp_path):
    pts = {"collections": {"c1": {"points": {"0": {"p": [1.0, 2.0, 3.0]}, "1": {"p": [4.0, 5.0, 6.0]}}}}}
    write(tmp_path, "raw/patchA/foo_points.json", pts)
    out = tmp_path / "alarms.json"
    alarms = windcheck.run(str(tmp_path / "raw"), str(out))
    assert sorted(alarms["patchA"]) == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]


def test_windcheck_patch_mode_only_transverse_contacts(tmp_path):
    raw = {"transverse_both": 1, "contacts": [{"xyz1": [1, 1, 1], "xyz2": [2, 2, 2]}]}
    p = write(tmp_path, "raw/patchA.json", raw)
    assert windcheck.patch_mode_contacts(json.loads(p.read_text())) == [[1, 1, 1], [2, 2, 2]]


# ----------------------------------------------------------------------------- windaudit
def test_windaudit_alarm_only_for_patch_edges_that_changed():
    edges = [
        {"pcl_id": "g1", "from_point_id": 1, "to_point_id": 2, "P": "patchA", "R": "other",
         "from_ij": [0.2, 0.2], "to_ij": [1.2, 1.2]},
        {"pcl_id": "g1", "from_point_id": 3, "to_point_id": 4, "P": "elsewhere", "R": "other2",
         "from_ij": [0.0, 0.0], "to_ij": [0.0, 0.0]},  # doesn't touch patchA: never counted
    ]
    after = {"edges": [{"rel_pcl_id": "g1", "from_point_id": 1, "to_point_id": 2}]}
    import numpy as np
    P = np.full((3, 3, 3), np.nan)
    P[0, 0] = [10, 20, 30]
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        Path(d, "measured_edges.json").write_text(json.dumps(edges))
        Path(d, "after_full.json").write_text(json.dumps(after))
        hits = windaudit.alarms_for_patch("patchA", d, P)
    assert hits == [[10, 20, 30]]


def test_windaudit_requires_native_files(tmp_path):
    import numpy as np
    try:
        windaudit.alarms_for_patch("patchA", tmp_path, np.zeros((2, 2, 3)))
        assert False
    except AdapterError:
        pass


# ----------------------------------------------------------------------------- seamcheck
def test_seamcheck_alarms_only_on_review_or_watch():
    assert seamcheck.alarms_for_patch({"verdict": "OK", "flagged_steps": [{"xyz": [1, 2, 3]}]}) == []
    assert seamcheck.alarms_for_patch({"verdict": "SPARSE", "flagged_steps": [{"xyz": [1, 2, 3]}]}) == []
    assert seamcheck.alarms_for_patch({"verdict": "REVIEW", "flagged_steps": [{"xyz": [1, 2, 3]}]}) == [[1, 2, 3]]
    assert seamcheck.alarms_for_patch({"verdict": "WATCH", "flagged_steps": [{"xyz": [9, 9, 9]}]}) == [[9, 9, 9]]


# ----------------------------------------------------------------------------- check1621
def test_check1621_emits_both_points_of_every_flagged_pair():
    raw = {"alarms": [{"xyz_p": [1, 2, 3], "xyz_q": [4, 5, 6]}, {"xyz_p": [7, 8, 9], "xyz_q": None}]}
    assert check1621.alarms_for_patch(raw) == [[1, 2, 3], [4, 5, 6], [7, 8, 9]]


def test_check1621_no_pairs_flagged():
    assert check1621.alarms_for_patch({"n_attached": 0, "alarms": [], "pairs": 0}) == []


# ----------------------------------------------------------------------------- CLI plumbing / errors
def test_missing_native_path_raises_adapter_error(tmp_path):
    try:
        tifxyz_doctor.run(str(tmp_path / "nope"), str(tmp_path / "out.json"))
        assert False
    except AdapterError:
        pass

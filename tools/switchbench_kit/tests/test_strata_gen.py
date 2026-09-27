"""tools.switchbench_kit.strata_gen: builds a leaderboard strata file straight from
explore_abruptness.py's own sheet-frame classification field (abrupt_primary_sf), with no re-derivation.
The v0-reproduction check (doctor: 5/24 abrupt, 1/30 gradual) lives in
tools/switchbench_kit/tests/test_v0_equivalence.py since it needs the real corpus + patch data."""
from __future__ import annotations

from tools.switchbench_kit import strata_gen


def test_build_reads_the_sheet_frame_field_only():
    explore = {"results": {"per_event": [
        {"patch": "p1", "xyz": [1.0, 2.0, 3.04], "abrupt_primary_sf": True, "abrupt_primary_planned": False},
        {"patch": "p1", "xyz": [4.0, 5.0, 6.0], "abrupt_primary_sf": False},
        {"patch": "p2", "xyz": [7.0, 8.0, 9.0], "abrupt_primary_sf": None},  # unclassified: skipped
    ]}}
    strata, skipped = strata_gen.build(explore)
    assert strata == {"p1|1.0,2.0,3.0": "abrupt", "p1|4.0,5.0,6.0": "gradual"}
    assert skipped == 1


def test_key_rounds_to_0_1_voxel_matching_leaderboard():
    assert strata_gen._key("p", [1.04, 1.05, 1.06]) == "p|1.0,1.1,1.1"


def test_missing_per_event_raises():
    try:
        strata_gen.build({"results": {}})
        assert False
    except ValueError:
        pass


def test_cli_roundtrip(tmp_path):
    import json
    explore = tmp_path / "explore.json"
    explore.write_text(json.dumps({"results": {"per_event": [
        {"patch": "p1", "xyz": [1.0, 2.0, 3.0], "abrupt_primary_sf": True},
    ]}}))
    out = tmp_path / "strata.json"
    rc = strata_gen.main(["--explore", str(explore), "--out", str(out)])
    assert rc == 0
    assert json.loads(out.read_text()) == {"p1|1.0,2.0,3.0": "abrupt"}

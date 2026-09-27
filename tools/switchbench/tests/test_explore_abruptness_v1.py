"""tools.switchbench.explore_abruptness: the v1 parametrization added for internal/release/RELEASE_RUNBOOK.md
4a2 (strata for ABRUPTNESS_TAKEAWAY). These are dependency-light unit tests of the pure logic only --
load_corpus_v1's pooling/status-override rule, cap_arrays' v1 dummy fallback, and stage_report_v1's
section-A-only output -- never touching real tifxyz patch geometry or the doctor's capture arrays, and
never opening data/switchbench_v1/blind_key.json. v0's own behaviour (geom/report with no --v1) is
covered implicitly: this file only ever calls the new code paths (load_corpus_v1, cap_arrays'
dummy_shape branch, stage_report_v1), never load_corpus_v0/stage_report/stage_sweep, so it cannot regress
them; the full-corpus run itself is checked by hand (per-patch checkpoint counts, corpus meta) in
results/switchbench_natural_v1_abruptness.json's own provenance/corpus block."""
from __future__ import annotations

import json

import numpy as np
import pytest

from tools.switchbench import explore_abruptness as ea


def _write(d, name, payload):
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(payload))


# ----------------------------------------------------------------------------- load_corpus_v1
def test_load_corpus_v1_pools_v0_and_new_dirs_and_applies_l0_status(tmp_path, monkeypatch):
    v0_dir, v1_dir = tmp_path / "paris4", tmp_path / "switchbench_v1"
    monkeypatch.setattr(ea.geom, "DATA", v0_dir)
    monkeypatch.setattr(ea, "V1_DATA", v1_dir)

    # a v0-prefix patch: level-2 status "confirmed", level-0 flips it to "contradicted"
    _write(v0_dir / "corpus", "p1", {
        "patch": "p1", "in_sample": True, "excluded_same_lineage": ["q1"],
        "events": [{"xyz": [1.0, 2.0, 3.0], "delta_signs": [1], "status": "confirmed", "members": []}],
        "negatives": [{"status": "confirmed", "verts": [[0, 0]], "len_mm": 1.0}],
    })
    _write(v1_dir / "l0", "p1", {"patch": "p1", "events": [
        {"i": 0, "xyz": [1.0, 2.0, 3.0], "status_l0": "contradicted"},
    ]})
    # a new v1 patch, unaffected level-0 verdict
    _write(v1_dir / "corpus", "p2", {
        "patch": "p2", "in_sample": True, "excluded_same_lineage": [],
        "events": [{"xyz": [4.0, 5.0, 6.0], "delta_signs": [1], "status": "unconfirmed", "members": []}],
        "negatives": [],
    })
    _write(v1_dir / "l0", "p2", {"patch": "p2", "events": [
        {"i": 0, "xyz": [4.0, 5.0, 6.0], "status_l0": "confirmed"},
    ]})
    # a not-in-sample patch: must be dropped entirely
    _write(v1_dir / "corpus", "p3", {"patch": "p3", "in_sample": False, "events": [], "negatives": []})

    recs = ea.load_corpus_v1()

    assert set(recs) == {"p1", "p2"}
    assert recs["p1"]["events"][0]["status"] == "contradicted"   # overridden by level-0
    assert recs["p1"]["negatives"][0]["status"] == "confirmed"   # negatives keep the v0/level-2 status
    assert recs["p1"]["excluded_same_lineage"] == ["q1"]         # schema field preserved, not dropped
    assert recs["p2"]["events"][0]["status"] == "confirmed"      # overridden by level-0


def test_load_corpus_v1_raises_on_xyz_mismatch(tmp_path, monkeypatch):
    v0_dir, v1_dir = tmp_path / "paris4", tmp_path / "switchbench_v1"
    monkeypatch.setattr(ea.geom, "DATA", v0_dir)
    monkeypatch.setattr(ea, "V1_DATA", v1_dir)
    _write(v0_dir / "corpus", "p1", {
        "patch": "p1", "in_sample": True,
        "events": [{"xyz": [1.0, 2.0, 3.0], "delta_signs": [1], "status": "confirmed", "members": []}],
        "negatives": [],
    })
    _write(v1_dir / "l0", "p1", {"patch": "p1", "events": [
        {"i": 0, "xyz": [999.0, 2.0, 3.0], "status_l0": "confirmed"},   # wrong xyz
    ]})
    with pytest.raises(RuntimeError):
        ea.load_corpus_v1()


def test_mode_dispatch_matches_env(monkeypatch):
    monkeypatch.setattr(ea, "IS_V1", False)
    # load_corpus() must call the v0 loader when not in v1 mode (patch it to prove it's the one used)
    called = {}
    monkeypatch.setattr(ea, "load_corpus_v0", lambda: called.setdefault("v0", True) or {})
    monkeypatch.setattr(ea, "load_corpus_v1", lambda: called.setdefault("v1", True) or {})
    ea.load_corpus()
    assert called == {"v0": True}

    called.clear()
    monkeypatch.setattr(ea, "IS_V1", True)
    ea.load_corpus()
    assert called == {"v1": True}


# ----------------------------------------------------------------------------- cap_arrays dummy fallback
def test_cap_arrays_dummy_when_missing_and_shape_given(tmp_path, monkeypatch):
    monkeypatch.setattr(ea, "EXPLORE", tmp_path)
    z = ea.cap_arrays("nope", dummy_shape=(3, 4))
    assert z["hscore"].shape == (3, 4) and np.isnan(z["hscore"]).all()
    assert z["vscore"].shape == (3, 4) and np.isnan(z["vscore"]).all()
    assert z["href"] == 1.0 and z["vref"] == 1.0


def test_cap_arrays_raises_when_missing_and_no_dummy_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(ea, "EXPLORE", tmp_path)
    with pytest.raises(FileNotFoundError):
        ea.cap_arrays("nope")


def test_cap_arrays_prefers_real_file_over_dummy(tmp_path, monkeypatch):
    monkeypatch.setattr(ea, "EXPLORE", tmp_path)
    cap = tmp_path / "capture"
    cap.mkdir()
    np.savez(cap / "p1.npz", hscore=np.array([[0.5]]), vscore=np.array([[0.1]]), href=2.0, vref=3.0)
    z = ea.cap_arrays("p1", dummy_shape=(9, 9))
    assert z["hscore"].shape == (1, 1) and float(z["hscore"][0, 0]) == 0.5


# ----------------------------------------------------------------------------- stage_report_v1
def _member(step_vx, n_steps=1):
    """A single reproduced member whose max_step_vx is exactly `step_vx` (event_level's abruptness
    input); n_step_measurements > 0 so event_level doesn't treat it as unmeasured."""
    return dict(axis="row", rc_a=[0, 0], rc_b=[0, n_steps], reproduced=True, W_mm=1.0, n_steps=n_steps,
                max_step_vx=step_vx, max_step_sf_vx=step_vx, max_rate_vx_per_mm=None, max_rate_sf_vx_per_mm=None,
                total_offset_vx=None, total_sf_vx=None, gap_a=None, gap_b=None, spacing_b=None,
                doctor_zone_max_score=None, doctor_zone_max_vx=None, n_step_measurements=1, partial=False)


def test_stage_report_v1_writes_per_event_abruptness_only(tmp_path, monkeypatch):
    monkeypatch.setattr(ea, "EXPLORE", tmp_path)
    out = tmp_path / "out.json"
    monkeypatch.setattr(ea, "OUT_JSON", out)
    geom_json = {"events": [
        {"patch": "p1", "event_index": 0, "status": "confirmed", "xyz": [1.0, 2.0, 3.0],
         "members": [_member(ea.ABRUPT_VX + 1)]},          # >= threshold: abrupt
        {"patch": "p1", "event_index": 1, "status": "confirmed", "xyz": [4.0, 5.0, 6.0],
         "members": [_member(ea.ABRUPT_VX - 1)]},          # < threshold: gradual
        {"patch": "p1", "event_index": 2, "status": "contradicted", "xyz": [7.0, 8.0, 9.0],
         "members": [_member(ea.ABRUPT_VX + 1)]},          # not confirmed: excluded from per_event
    ]}
    (tmp_path / "geom.json").write_text(json.dumps(geom_json))

    ea.stage_report_v1()

    written = json.loads(out.read_text())
    per_event = written["results"]["per_event"]
    assert len(per_event) == 2  # only the confirmed events
    by_idx = {r["event_index"]: r for r in per_event}
    assert by_idx[0]["abrupt_primary_sf"] is True
    assert by_idx[1]["abrupt_primary_sf"] is False
    assert written["corpus"]["n_confirmed"] == 2
    assert written["results"]["fraction_abrupt_confirmed"]["abrupt_primary_sf"]["k"] == 1
    assert written["results"]["fraction_abrupt_confirmed"]["abrupt_primary_sf"]["n"] == 2

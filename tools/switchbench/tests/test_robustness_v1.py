"""Unit tests for tools.switchbench.robustness_v1 (job 16: POST-HOC/DESCRIPTIVE C1 robustness checks).
All pure-logic: no real tifxyz patch geometry is loaded, no detector is re-run, and
data/switchbench_v1/blind_key.json is never referenced, matching the module's own contract."""
from __future__ import annotations

import json

import numpy as np
import pytest

from tools.switchbench import robustness_v1 as rv


# ----------------------------------------------------------------------------- batch_of
def test_batch_of_extracts_date_prefix():
    assert rv.batch_of("auto_grown_20260420115140568_region_002") == "20260420"


def test_batch_of_legacy_for_non_auto_grown_name():
    assert rv.batch_of("full_size_patch_007") == "legacy"


# ----------------------------------------------------------------------------- combine / cap_filter
def test_combine_none_is_behaviorally_identity():
    f = lambda x: x > 0
    assert rv.combine(None, f)(1) == f(1) and rv.combine(None, f)(-1) == f(-1)
    assert rv.combine(f, None)(1) == f(1) and rv.combine(f, None)(-1) == f(-1)


def test_combine_all_none_is_none():
    assert rv.combine(None, None) is None


def test_combine_requires_all_filters():
    f1 = lambda x: x["a"]
    f2 = lambda x: x["b"]
    g = rv.combine(f1, f2)
    assert g(dict(a=True, b=True)) is True
    assert g(dict(a=True, b=False)) is False


def test_cap_filter_none_selection_is_none():
    assert rv.cap_filter(None) is None


def test_cap_filter_membership():
    sel = {("p1", 0), ("p1", 2)}
    f = rv.cap_filter(sel)
    assert f(dict(patch="p1", i=0)) is True
    assert f(dict(patch="p1", i=1)) is False
    assert f(dict(patch="p2", i=0)) is False


# ----------------------------------------------------------------------------- with_corrected
def test_with_corrected_holds_under_bar():
    stats = dict(boot95=[0.05, 0.15])
    out = rv.with_corrected(stats, prec_lo=0.552)
    assert out["corrected_upper"] == pytest.approx(0.15 / 0.552)
    assert out["c1_would_hold"] is True


def test_with_corrected_does_not_hold_over_bar():
    stats = dict(boot95=[0.1, 0.4])
    out = rv.with_corrected(stats, prec_lo=0.552)
    assert out["corrected_upper"] == pytest.approx(0.4 / 0.552)
    assert out["c1_would_hold"] is False


def test_with_corrected_none_upper_is_not_a_hold():
    stats = dict(boot95=[None, None])
    out = rv.with_corrected(stats, prec_lo=0.552)
    assert out["corrected_upper"] is None
    assert out["c1_would_hold"] is False


# ----------------------------------------------------------------------------- precision_lower_bound
def test_precision_lower_bound_reads_wilson_lower(tmp_path, monkeypatch):
    monkeypatch.setattr(rv, "RES", tmp_path)
    (tmp_path / "switchbench_v1_blind_review_score.json").write_text(
        json.dumps(dict(precision=dict(wilson95=[0.552, 0.953]))))
    assert rv.precision_lower_bound() == pytest.approx(0.552)


# ----------------------------------------------------------------------------- sel_set (real cap_selection)
def _rec(patch, subset, statuses):
    return dict(patch=patch, subset=subset,
               events=[dict(i=i, xyz=[float(i), 0.0, 0.0], status=s) for i, s in enumerate(statuses)])


def test_sel_set_none_cap_is_none():
    recs = [_rec("p1", "v0", ["confirmed"] * 3)]
    assert rv.sel_set(recs, None) is None


def test_sel_set_cap_1_selects_exactly_one_per_patch():
    recs = [_rec("p1", "v0", ["confirmed"] * 4), _rec("p2", "new", ["confirmed", "contradicted"])]
    sel = rv.sel_set(recs, 1)
    p1_sel = {i for p, i in sel if p == "p1"}
    p2_sel = {i for p, i in sel if p == "p2"}
    assert len(p1_sel) == 1
    assert p2_sel == {0}          # only 1 confirmed event on p2, under the cap -> kept whole


def test_sel_set_cap_above_count_keeps_all_confirmed():
    recs = [_rec("p1", "v0", ["confirmed", "confirmed", "contradicted"])]
    sel = rv.sel_set(recs, 3)
    assert {i for p, i in sel if p == "p1"} == {0, 1}


# ----------------------------------------------------------------------------- grid_rows / batch_rows (synthetic)
def _ev_row(patch, subset, i, hits):
    """hits: {tool: {radius: bool}}"""
    return dict(patch=patch, subset=subset, i=i, capped=True, hit=hits)


def _synthetic_ev_rows_and_recs():
    # 2 patches, 2 confirmed events each; tool "T" hits at 1.0/2.0 mm but not 0.5 mm on event 0 of each patch
    hits_hit = {"T": {0.5: False, 1.0: True, 2.0: True}}
    hits_miss = {"T": {0.5: False, 1.0: False, 2.0: False}}
    ev_rows = [
        _ev_row("auto_grown_20260420000000000_region_000", "v0", 0, hits_hit),
        _ev_row("auto_grown_20260420000000000_region_000", "v0", 1, hits_miss),
        _ev_row("auto_grown_20260421000000000_region_000", "new", 0, hits_hit),
        _ev_row("auto_grown_20260421000000000_region_000", "new", 1, hits_hit),
    ]
    recs = [
        _rec("auto_grown_20260420000000000_region_000", "v0", ["confirmed", "confirmed"]),
        _rec("auto_grown_20260421000000000_region_000", "new", ["confirmed", "confirmed"]),
    ]
    return ev_rows, recs


def test_grid_rows_pooled_recall_matches_manual_count(monkeypatch):
    ev_rows, recs = _synthetic_ev_rows_and_recs()
    monkeypatch.setattr(rv, "TOOLS", ("T",))
    monkeypatch.setattr(rv.e1, "RADII", (0.5, 1.0, 2.0))
    monkeypatch.setattr(rv, "CAPS", (None,))
    monkeypatch.setattr(rv, "FROZEN", dict(cap=None, radius=1.0))
    grid = rv.grid_rows(ev_rows, recs, prec_lo=0.552)
    pooled_1mm = next(r for r in grid if r["subset"] == "pooled" and r["radius"] == 1.0)
    assert pooled_1mm["hits"] == 3            # 3 of 4 synthetic events hit at 1.0 mm
    assert pooled_1mm["n_events"] == 4
    assert pooled_1mm["recall"] == pytest.approx(0.75)
    assert pooled_1mm["corrected_upper"] == pytest.approx(pooled_1mm["boot95"][1] / 0.552)
    assert pooled_1mm["frozen"] is True       # cap None == FROZEN["cap"] here, radius matches


def test_grid_rows_marks_c1_would_hold_correctly(monkeypatch):
    ev_rows, recs = _synthetic_ev_rows_and_recs()
    monkeypatch.setattr(rv, "TOOLS", ("T",))
    monkeypatch.setattr(rv.e1, "RADII", (1.0,))
    monkeypatch.setattr(rv, "CAPS", (None,))
    grid = rv.grid_rows(ev_rows, recs, prec_lo=0.01)   # tiny precision -> corrected upper blows past 0.60
    assert all(r["c1_would_hold"] is False for r in grid)


def test_batch_rows_groups_by_date_prefix(monkeypatch):
    ev_rows, recs = _synthetic_ev_rows_and_recs()
    monkeypatch.setattr(rv, "TOOLS", ("T",))
    monkeypatch.setattr(rv.e1, "RADII", (1.0,))
    monkeypatch.setattr(rv, "CAPS", (None,))
    batches, counts = rv.batch_rows(ev_rows, recs, prec_lo=0.552)
    assert counts == {"20260420": 1, "20260421": 1}
    b420 = next(r for r in batches if r["batch"] == "20260420")
    assert b420["n_events"] == 2
    assert b420["hits"] == 1


# ----------------------------------------------------------------------------- load_contradicted_rows
def test_load_contradicted_rows_matches_cached_alarms_and_skips_uncached_patches(monkeypatch):
    P = np.array([[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
                  [[0.0, 1.0, 0.0], [1.0, 1.0, 0.0]]])

    def fake_j(tool, nm):
        assert tool == "tifxyz_doctor"
        if nm == "patchA":
            return dict(alarms_primary=[[0, 0]], alarms_any=[])
        return None   # patchB: no cached detector run

    monkeypatch.setattr(rv.e1, "_j", fake_j)
    monkeypatch.setattr(rv.e1, "patch_geom", lambda nm: (P, None, {}))

    recs = [
        dict(patch="patchA", subset="v0",
             events=[dict(i=0, status="contradicted", xyz=[0.5, 0.5, 0.0], delta_signs=[1], members=[]),
                     dict(i=1, status="confirmed", xyz=[9.0, 9.0, 9.0], delta_signs=[1], members=[])]),
        dict(patch="patchB", subset="new",
             events=[dict(i=0, status="contradicted", xyz=[0.0, 0.0, 0.0], delta_signs=[1], members=[])]),
    ]
    rows, cov = rv.load_contradicted_rows(recs)
    assert cov == dict(candidate_patches=2, cached_patches=1, candidate_events=2)
    assert len(rows) == 1              # only patchA's contradicted event; patchB skipped (no cache)
    r = rows[0]
    assert r["patch"] == "patchA" and r["i"] == 0
    # alarms_primary cell (0,0) -> mean of the 4 corners = (0.5, 0.5, 0.0), exactly the event xyz
    assert r["hit"][rv.DOCTOR][0.5] is True
    assert r["hit"][rv.DOCTOR][1.0] is True
    assert r["hit"][rv.ANYCUE][1.0] is False   # alarms_any is empty


def test_load_contradicted_rows_no_candidates_gives_empty(monkeypatch):
    rows, cov = rv.load_contradicted_rows([dict(patch="p1", subset="v0",
                                                events=[dict(i=0, status="confirmed", xyz=[0, 0, 0])])])
    assert rows == []
    assert cov == dict(candidate_patches=0, cached_patches=0, candidate_events=0)

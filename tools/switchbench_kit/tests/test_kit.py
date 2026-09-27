"""Unit tests of the SwitchBench scorer kit on synthetic patches (see _synth.py for the layout)."""
from __future__ import annotations

import json

import numpy as np
import pytest

from _synth import corpus_dict, grid_a, make_patches, write_alarms, write_corpus
from tools.switchbench_kit import (AlarmsError, CorpusError, format_report, from_xyz, load_alarms, load_benchmark,
                                   score)
from tools.switchbench_kit import geometry, scoring
from tools.switchbench_kit.__main__ import main as cli

MM = 1.0 / 0.0096                     # voxels per mm
EVENT = [1210.0, 2000.0, 3100.0]      # the confirmed event's transition point (= its centre)
RUN_MM = 1200 / MM + 1180 / MM        # confirmed negative runs: pA row 20 + pB col 5


@pytest.fixture
def bench(tmp_path):
    make_patches(tmp_path / "patches")
    return load_benchmark(write_corpus(tmp_path / "corpus.json"), tmp_path / "patches")


def run(bench, mapping, **kw):
    return score(bench, from_xyz(bench, mapping), **kw)


# ----------------------------------------------------------------------------- corpus and geometry
def test_corpus_is_rebuilt_from_the_grid(bench):
    assert bench.patches == ["pA", "pB"]                       # pC carries only an unconfirmed event
    ev = bench.events["pA"]
    assert [e.status for e in ev] == ["confirmed", "contradicted"]
    np.testing.assert_array_equal(ev[0].points, [EVENT, EVENT])  # transition point + centre
    runs = [n for p in bench.patches for n in bench.negatives[p] if n.status == "confirmed"]
    assert [len(n.verts) for n in runs] == [61, 60]
    assert sum(n.length_mm for n in runs) == pytest.approx(RUN_MM, abs=1e-12)


def test_run_vertices_and_length():
    assert geometry.run_vertices("row", [2, 3], [2, 5]) == [(2, 3), (2, 4), (2, 5)]
    assert geometry.run_vertices("col", [1, 7], [3, 7]) == [(1, 7), (2, 7), (3, 7)]
    with pytest.raises(ValueError):
        geometry.run_vertices("row", [2, 3], [4, 5])
    assert geometry.arc_mm(grid_a(), [(0, 0), (0, 1), (0, 2)], MM) == pytest.approx(40 / MM)


def test_masked_and_minus_one_vertices_are_invalid(tmp_path):
    make_patches(tmp_path)
    P = geometry.load_tifxyz(tmp_path / "pA")
    assert np.isnan(P[0, 79]).all() and np.isnan(P[27, 75]).all() and np.isfinite(P[5, 10]).all()
    assert np.isfinite(geometry.load_tifxyz(tmp_path / "pA", use_mask=False)[27, 75]).all()


def test_geometry_that_disagrees_with_the_corpus_is_refused(tmp_path):
    make_patches(tmp_path / "patches")
    d = corpus_dict()
    d["events"][0]["xyz"][0] += 1.0                             # centre off by one voxel
    (tmp_path / "c1.json").write_text(json.dumps(d))
    with pytest.raises(CorpusError, match="centre"):
        load_benchmark(tmp_path / "c1.json", tmp_path / "patches")
    d = corpus_dict()
    d["negatives"][0]["len_mm"] = 12.0                          # wrong run length
    (tmp_path / "c2.json").write_text(json.dumps(d))
    with pytest.raises(CorpusError, match="run length"):
        load_benchmark(tmp_path / "c2.json", tmp_path / "patches")
    d = corpus_dict()
    d["events"][0]["transitions"][0]["rc_b"] = [27, 75]         # a masked vertex
    (tmp_path / "c3.json").write_text(json.dumps(d))
    with pytest.raises(CorpusError, match="not a valid vertex"):
        load_benchmark(tmp_path / "c3.json", tmp_path / "patches")


def test_missing_patch_files_are_refused(tmp_path):
    make_patches(tmp_path / "patches")
    (tmp_path / "patches" / "pB" / "x.tif").unlink()
    with pytest.raises(CorpusError, match="missing"):
        load_benchmark(write_corpus(tmp_path / "c.json"), tmp_path / "patches")


def test_fingerprint_sees_the_mask(tmp_path):
    make_patches(tmp_path)
    a = geometry.fingerprint({"pA": geometry.load_tifxyz(tmp_path / "pA")})
    b = geometry.fingerprint({"pA": geometry.load_tifxyz(tmp_path / "pA", use_mask=False)})
    assert a != b and a == geometry.fingerprint({"pA": geometry.load_tifxyz(tmp_path / "pA")})


# ----------------------------------------------------------------------------- matching rule
def test_alarm_exactly_at_a_transition_is_a_hit(bench):
    r = run(bench, {"pA": [EVENT], "pB": []})
    assert (r["recall"]["hits"], r["recall"]["events"]) == (1, 1)
    assert r["false_alarms"]["count"] == 0
    assert r["events"][0]["hit"] and r["events"][0]["nearest_alarm_mm"] == 0.0


def test_alarm_just_inside_and_just_outside_the_radius(bench):
    inside = [EVENT[0], EVENT[1] + 1.0 * MM - 1e-6, EVENT[2]]
    outside = [EVENT[0], EVENT[1] + 1.0 * MM + 1e-3, EVENT[2]]
    assert run(bench, {"pA": [inside], "pB": []})["recall"]["hits"] == 1
    r = run(bench, {"pA": [outside], "pB": []})
    assert r["recall"]["hits"] == 0 and r["false_alarms"]["count"] == 0
    assert r["events"][0]["nearest_alarm_mm"] == pytest.approx(1.0, abs=1e-5)
    assert run(bench, {"pA": [outside], "pB": []}, match_mm=2.0)["recall"]["hits"] == 1


def test_alarm_on_a_negative_run_is_a_false_alarm(bench):
    on_run = grid_a()[20, 30].tolist()
    r = run(bench, {"pA": [on_run], "pB": []})
    assert r["recall"]["hits"] == 0 and r["false_alarms"]["count"] == 1
    assert r["false_alarms"]["negative_mm"] == pytest.approx(RUN_MM)
    assert r["false_alarms"]["per_100mm"] == pytest.approx(100 / RUN_MM)


def test_alarm_near_any_candidate_event_is_not_a_false_alarm(bench):
    # (20, 40) lies on the run and 22 voxels from the CONTRADICTED event: excluded, as in v0
    r = run(bench, {"pA": [grid_a()[20, 40].tolist()], "pB": []})
    assert r["false_alarms"]["count"] == 0


def test_unconfirmed_runs_do_not_count(bench):
    r = run(bench, {"pA": [grid_a()[22, 30].tolist()], "pB": []})   # 2 grid rows (0.38 mm) from run 0
    assert r["false_alarms"]["count"] == 1                           # counted once, for the confirmed run
    r = run(bench, {"pA": [(grid_a()[22, 30] + [0, 0, 70]).tolist()], "pB": []})   # 1.06 mm from row 20,
    assert r["false_alarms"]["count"] == 0                                           # 0.67 mm from row 22


def test_crossing_runs_count_an_alarm_once_per_run(tmp_path):
    make_patches(tmp_path / "patches")
    d = corpus_dict()
    A = grid_a()
    d["negatives"].append(dict(patch="pA", status="confirmed", axis="col", rc0=[10, 30], rc1=[25, 30],
                               len_mm=round(300 / MM, 2), xyz0=A[10, 30].tolist(), xyz1=A[25, 30].tolist()))
    (tmp_path / "c.json").write_text(json.dumps(d))
    b = load_benchmark(tmp_path / "c.json", tmp_path / "patches")
    assert run(b, {"pA": [A[20, 30].tolist()], "pB": []})["false_alarms"]["count"] == 2


def test_false_alarm_dedup_merges_close_alarms_but_hits_use_every_alarm(bench):
    a = grid_a()[20, 30]
    two = [a.tolist(), (a + [0.3 * MM, 0, 0]).tolist()]            # 0.3 mm apart, both on the run
    assert run(bench, {"pA": two, "pB": []})["false_alarms"]["count"] == 1
    assert run(bench, {"pA": two, "pB": []}, fa_dedup_mm=0)["false_alarms"]["count"] == 2
    # first alarm 1.2 mm from the event (a miss), second 0.3 mm from the first and 0.9 mm from the event
    first = [EVENT[0], EVENT[1] + 1.2 * MM, EVENT[2]]
    second = [EVENT[0], EVENT[1] + 0.9 * MM, EVENT[2]]
    assert run(bench, {"pA": [first, second], "pB": []})["recall"]["hits"] == 1


def test_dedup_is_v0_greedy_in_input_order():
    rng = np.random.default_rng(1)
    A = rng.uniform(0, 400, (300, 3))
    r = 0.5 * MM

    keep = []                                                       # v0 evaluate.dedup_alarms, verbatim logic
    for a in A:
        if all(np.linalg.norm(a - b) > r for b in keep):
            keep.append(a)
    np.testing.assert_array_equal(scoring.dedup(A, r), np.array(keep))
    B = np.array([[0, 0, 0], [r, 0, 0], [2 * r, 0, 0]], float)     # exactly on the radius: dropped, as v0
    np.testing.assert_array_equal(scoring.dedup(B, r), B[[0, 2]])


# ----------------------------------------------------------------------------- coverage
def test_patch_missing_from_alarms_is_no_verdict_not_no_alarm(bench):
    r = run(bench, {"pA": [EVENT]})                                 # pB absent
    assert r["coverage"]["patches"] == [1, 2]
    assert r["coverage"]["negative_mm"][0] == pytest.approx(1200 / MM)
    assert r["coverage"]["negative_mm"][1] == pytest.approx(RUN_MM)
    assert [x["verdict"] for x in r["patches"]] == [True, False]
    assert "no verdict on 1 of 2 scored patches" in format_report(r)
    r = run(bench, {"pB": []})                                      # pA absent: its event is a miss
    assert (r["recall"]["hits"], r["recall"]["events"]) == (0, 1)
    assert r["coverage"]["events"] == [0, 1] and r["events"][0]["verdict"] is False
    assert r["coverage"]["recall_where_verdict"]["recall"] is None


def test_null_means_no_verdict(bench, tmp_path):
    a = load_alarms(write_alarms(tmp_path / "a.json", {"pA": [EVENT], "pB": None}), bench)
    assert a.by_patch["pB"] is None
    assert score(bench, a)["coverage"]["patches"] == [1, 2]


def test_unknown_and_unscored_patch_ids_are_listed(bench, tmp_path):
    a = load_alarms(write_alarms(tmp_path / "a.json", {"pA": [], "pB": [], "pC": [], "pZ": [[1, 2, 3]]}), bench)
    r = score(bench, a)
    assert r["detector"]["unknown_patch_ids"] == ["pZ"]
    assert r["detector"]["unscored_patches_ignored"] == ["pC"]
    assert "not in the corpus" in format_report(r)


def test_off_surface_alarms_are_flagged(bench):
    r = run(bench, {"pA": [[3100.0, 2000.0, 1210.0]], "pB": []})    # z and x swapped: far from pA
    assert r["detector"]["alarms_off_surface"] == 1
    assert "frame" in format_report(r)


# ----------------------------------------------------------------------------- input formats
def test_the_three_input_formats_agree(bench, tmp_path):
    A = grid_a()
    cells = [[5, 10], [20, 30], [12, 50]]
    xyz = load_alarms(write_alarms(tmp_path / "x.json", {"pA": [A[r, c].tolist() for r, c in cells], "pB": []}), bench)
    grid = load_alarms(write_alarms(tmp_path / "g.json", {"pA": cells, "pB": []}), bench)
    mdir = tmp_path / "masks"
    mdir.mkdir()
    m = np.zeros((30, 80), bool)
    m[tuple(np.array(cells).T)] = True
    np.savez(mdir / "pA.npz", mask=m)
    np.savez(mdir / "pB.npz", np.zeros((60, 20), np.uint8))       # unnamed 0/1 array is accepted too
    masks = load_alarms(mdir, bench)
    assert (xyz.format, grid.format, masks.format) == ("xyz", "grid", "masks")
    res = [score(bench, s) for s in (xyz, grid, masks)]
    for r in res:
        assert (r["recall"]["hits"], r["false_alarms"]["count"], r["coverage"]["patches"]) == (1, 1, [2, 2])
        assert [e["hit"] for e in r["events"]] == [e["hit"] for e in res[0]["events"]]


def test_wrapped_json_with_declared_format(bench, tmp_path):
    p = write_alarms(tmp_path / "w.json", {"format": "grid", "detector": "my-detector", "alarms": {"pA": [[5, 10]]}})
    a = load_alarms(p, bench)
    assert (a.format, a.detector) == ("grid", "my-detector")
    with pytest.raises(AlarmsError):
        load_alarms(p, bench, fmt="xyz")


def test_grid_alarms_on_invalid_vertices_are_dropped_and_counted(bench, tmp_path):
    a = load_alarms(write_alarms(tmp_path / "g.json", {"pA": [[27, 75], [0, 79], [5, 10]]}), bench)
    assert a.dropped_invalid == 2 and len(a.by_patch["pA"]) == 1


@pytest.mark.parametrize("obj,msg", [
    ({"pA": [[5, 10], [1, 2, 3]]}, "mixes"),
    ({"pA": [[99, 10]]}, "outside"),
    ({"pA": [[5.5, 10]]}, "integer"),
    ({"pA": [[1.0, "x", 2.0]]}, "numbers"),
    ({"pA": [[1.0, float("nan"), 2.0]]}, "non-finite"),
    ({"pA": [1, 2, 3]}, "every alarm"),
    ({"pA": "none"}, "list of points"),
])
def test_malformed_alarms_are_refused(bench, tmp_path, obj, msg):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(obj))
    with pytest.raises(AlarmsError, match=msg):
        load_alarms(p, bench)


def test_mask_with_wrong_shape_or_bad_file_is_refused(bench, tmp_path):
    (tmp_path / "m").mkdir()
    np.savez(tmp_path / "m" / "pA.npz", mask=np.zeros((10, 10), bool))
    with pytest.raises(AlarmsError, match="shape"):
        load_alarms(tmp_path / "m", bench)
    (tmp_path / "m" / "pA.npz").write_text("not a zip")
    with pytest.raises(AlarmsError, match="readable"):
        load_alarms(tmp_path / "m", bench)


# ----------------------------------------------------------------------------- statistics
def test_wilson_matches_the_v0_table():
    assert scoring.wilson(6, 54) == (0.1111111111111111, 0.051930224969995484, 0.2219470102118128)
    assert scoring.wilson(0, 54)[2] == 0.0664135880908964
    assert scoring.wilson(0, 0) == (None, None, None)


def test_bootstrap_is_deterministic_and_per_detector(bench):
    a = run(bench, {"pA": [EVENT], "pB": []}, bootstrap=200)
    b = run(bench, {"pA": [EVENT], "pB": []}, bootstrap=200)
    assert a["recall"]["bootstrap95"] == b["recall"]["bootstrap95"] == [1.0, 1.0]
    hits = [[True, False], [False], [True, True, False], [False, False]]
    one = scoring.patch_bootstrap(hits, 500, np.random.default_rng(20260925))
    assert one == scoring.patch_bootstrap(hits, 500, np.random.default_rng(20260925))
    shared = np.random.default_rng(20260925)                       # v0 report.py: one stream for all rows
    first, second = (scoring.patch_bootstrap(hits, 500, shared) for _ in range(2))
    moved = np.random.default_rng(20260925)
    for _ in range(500):                                           # the draws the first row consumed
        moved.choice(4, 4, replace=True)
    assert first == one and second == scoring.patch_bootstrap(hits, 500, moved)


def test_false_alarm_bootstrap_is_deterministic_and_reported(bench):
    on_run = grid_a()[20, 30].tolist()
    a = run(bench, {"pA": [on_run], "pB": []}, bootstrap=500)
    b = run(bench, {"pA": [on_run], "pB": []}, bootstrap=500)
    assert a["false_alarms"]["bootstrap95"] == b["false_alarms"]["bootstrap95"]
    assert a["false_alarms"]["bootstrap95"][0] <= a["false_alarms"]["per_100mm"] <= a["false_alarms"]["bootstrap95"][1]
    assert a["false_alarms"]["bootstrap_patches"] == 2
    # zero bootstrap draws still leaves recall/FA point estimates and coverage untouched, CIs just None
    z = run(bench, {"pA": [on_run], "pB": []}, bootstrap=0)
    assert z["false_alarms"]["bootstrap95"] is None and z["false_alarms"]["count"] == 1
    assert z["recall"]["bootstrap95"] is None
    fa = [3, 0]
    mm = [10.0, 20.0]
    one = scoring.fa_bootstrap(fa, mm, 500, np.random.default_rng(1))
    assert one == scoring.fa_bootstrap(fa, mm, 500, np.random.default_rng(1))
    assert scoring.fa_bootstrap([], [], 500, np.random.default_rng(1)) is None
    assert scoring.fa_bootstrap(fa, mm, 0, np.random.default_rng(1)) is None
    # a shared recall rng stream (v0 report.py's one-stream-per-report convention) is untouched by FA:
    # the FA CI always uses its own fresh seed(seed)-RNG, so adding it changes no downstream detector's
    # recall bootstrap in a multi-detector report.
    shared = np.random.default_rng(20260925)
    hits = [[True, False], [False], [True, True, False], [False, False]]
    before = scoring.patch_bootstrap(hits, 500, shared)
    scoring.fa_bootstrap(fa, mm, 500, np.random.default_rng(20260925))  # independent stream, not `shared`
    after = scoring.patch_bootstrap(hits, 500, np.random.default_rng(20260925))
    for _ in range(500):
        after
    assert before == scoring.patch_bootstrap(hits, 500, np.random.default_rng(20260925))


def test_limited_scope_flags_low_coverage(bench):
    on_run = grid_a()[20, 30].tolist()
    full = run(bench, {"pA": [on_run], "pB": []})
    assert full["coverage"]["limited_scope"] is False       # 2/2 patches with a verdict
    none_scored = run(bench, {})
    assert none_scored["coverage"]["limited_scope"] is True  # 0/2 patches with a verdict, < 50%


def test_per_patch_cap_follows_v1(tmp_path):
    make_patches(tmp_path / "patches")
    A = grid_a()
    extra = []
    for c in (20, 30, 50, 60):                                     # 4 more confirmed events in pA (5 in all)
        extra.append(dict(patch="pA", status="confirmed", xyz=[round(float(v), 1) for v in (A[8, c] + A[8, c + 1]) / 2],
                          delta_signs=[1], transitions=[dict(axis="row", rc_a=[8, c], rc_b=[8, c + 1])]))
    b = load_benchmark(write_corpus(tmp_path / "c.json", extra_events=extra), tmp_path / "patches")
    sel = scoring.cap_selection(b, 3, 20260925)
    conf = sorted([e for e in b.events["pA"] if e.status == "confirmed"], key=lambda e: tuple(e.centre.tolist()))
    want = {conf[j].index for j in sorted(np.random.default_rng(20260925).choice(5, 3, replace=False).tolist())}
    assert sel == want                                             # v1 evaluate_v1.cap_selection
    r = run(b, {"pA": [], "pB": []}, per_patch_cap=3)
    assert r["recall"]["events"] == 3 and r["corpus"]["confirmed_events"] == 5
    assert run(b, {"pA": [], "pB": []}, per_patch_cap=0)["recall"]["events"] == 5


def test_settings_come_from_argument_then_corpus_then_kit(tmp_path):
    make_patches(tmp_path / "patches")
    b = load_benchmark(write_corpus(tmp_path / "c.json", scoring={"match_mm": 2.0, "per_patch_cap": 3}),
                       tmp_path / "patches")
    st, src = scoring.resolve_settings(b, match_mm=None, seed=7)
    assert (st["match_mm"], src["match_mm"]) == (2.0, "corpus file")
    assert (st["seed"], src["seed"]) == (7, "argument")
    assert (st["bootstrap"], src["bootstrap"]) == (2000, "kit default")


# ----------------------------------------------------------------------------- command line
def test_cli_list_and_score(bench, tmp_path, capsys):
    corpus = tmp_path / "corpus.json"
    assert cli(["list", "--corpus", str(corpus)]) == 0
    assert capsys.readouterr().out.split() == ["pA", "pB"]
    alarms = write_alarms(tmp_path / "a.json", {"pA": [EVENT, grid_a()[20, 30].tolist()], "pB": []})
    out = tmp_path / "res.json"
    assert cli(["score", "--corpus", str(corpus), "--alarms", str(alarms), "--patches-dir", str(tmp_path / "patches"),
                "--json", str(out), "--per-event"]) == 0
    text = capsys.readouterr().out
    assert "| Recall (hits / events) | 1.000 (1/1) |" in text and "HIT" in text
    r = json.loads(out.read_text())
    assert r["recall"]["hits"] == 1 and r["false_alarms"]["count"] == 1
    assert r["settings"]["match_mm"] == 1.0 and r["settings"]["seed"] == 20260925
    assert cli(["score", "--corpus", str(corpus), "--alarms", str(tmp_path / "nope.json"),
                "--patches-dir", str(tmp_path / "patches")]) == 2

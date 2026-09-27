"""Unit tests for tools.switchbench.refresh's pure logic (job 6, monthly leaderboard refresh dry run).
No bucket calls, no patch geometry, no detector code, and data/switchbench_v1/blind_key.json is never
referenced -- these test only batch-date filtering (list) and the diff/noise verdict (diff)."""
from __future__ import annotations

from tools.switchbench import refresh as rf


# ----------------------------------------------------------------------------- batch_full_id / ts_to_iso
def test_batch_full_id_extracts_full_timestamp():
    assert rf.batch_full_id("auto_grown_20260420114949303_region_000") == "20260420114949303"


def test_batch_full_id_none_for_non_auto_grown_name():
    assert rf.batch_full_id("auto_grown_w20231210121321") is None
    assert rf.batch_full_id("full_size_patch_007") is None


def test_batch_full_id_groups_regions_of_one_batch_together():
    a = rf.batch_full_id("auto_grown_20260420114949303_region_000")
    b = rf.batch_full_id("auto_grown_20260420114949303_region_004")
    assert a == b


def test_ts_to_iso():
    assert rf.ts_to_iso("20260420114949303") == "2026-04-20"


# ----------------------------------------------------------------------------- corpus_cutoff_ts
def test_corpus_cutoff_ts_is_the_max_known_batch_timestamp():
    known = ["auto_grown_20260420114949303_region_000", "auto_grown_20260428164716694_region_002",
             "auto_grown_20260421000000000_region_001"]
    assert rf.corpus_cutoff_ts(known) == "20260428164716694"


def test_corpus_cutoff_ts_ignores_non_auto_grown_names():
    known = ["auto_grown_w20231210121321", "auto_grown_20260420114949303_region_000"]
    assert rf.corpus_cutoff_ts(known) == "20260420114949303"


def test_corpus_cutoff_ts_none_when_pool_is_empty_or_all_legacy():
    assert rf.corpus_cutoff_ts([]) is None
    assert rf.corpus_cutoff_ts(["auto_grown_w20231210121321"]) is None


# ----------------------------------------------------------------------------- group_new_batches (list filtering)
def test_group_new_batches_groups_by_full_timestamp_sorted_oldest_first():
    new_names = ["auto_grown_20260501000000000_region_002", "auto_grown_20260430000000000_region_000",
                 "auto_grown_20260501000000000_region_000"]
    batches = rf.group_new_batches(new_names)
    assert [b["batch_id"] for b in batches] == ["20260430000000000", "20260501000000000"]
    assert batches[1]["n_patches"] == 2
    assert batches[1]["patches"] == ["auto_grown_20260501000000000_region_000",
                                     "auto_grown_20260501000000000_region_002"]
    assert batches[0]["batch_date_utc"] == "2026-04-30"


def test_group_new_batches_drops_non_auto_grown_names():
    assert rf.group_new_batches(["auto_grown_w20231210121321"]) == []


def test_group_new_batches_empty_for_no_new_patches():
    assert rf.group_new_batches([]) == []


# ----------------------------------------------------------------------------- estimate_bytes_per_patch
def test_estimate_bytes_per_patch_sums_files_per_patch_and_averages():
    listing = [
        ["spiral/PHercParis4/unverified_patches/pA/x.tif", 100],
        ["spiral/PHercParis4/unverified_patches/pA/y.tif", 100],
        ["spiral/PHercParis4/unverified_patches/pB/x.tif", 300],
    ]
    # pA totals 200, pB totals 300 -> mean 250
    assert rf.estimate_bytes_per_patch(listing) == 250.0


def test_estimate_bytes_per_patch_empty_listing_is_zero():
    assert rf.estimate_bytes_per_patch([]) == 0.0


# ----------------------------------------------------------------------------- overlaps
def test_overlaps_true_when_intervals_intersect():
    assert rf.overlaps((0.0, 0.2), (0.1, 0.3))


def test_overlaps_false_when_intervals_disjoint():
    assert not rf.overlaps((0.0, 0.1), (0.2, 0.3))


def test_overlaps_touching_endpoints_count_as_overlap():
    assert rf.overlaps((0.0, 0.1), (0.1, 0.2))


def test_overlaps_none_is_treated_as_overlap_not_a_confident_change():
    assert rf.overlaps(None, (0.1, 0.2))
    assert rf.overlaps((0.1, 0.2), None)
    assert rf.overlaps(None, None)


# ----------------------------------------------------------------------------- diff_row
def _row(recall=None, bootstrap_patches=10, fa=None, fa_patches=10, name="d"):
    return dict(name=name,
                recall=dict(events=recall[2] if recall else 0, recall=recall[0] if recall else None,
                           bootstrap95=recall[1] if recall else None, bootstrap_patches=bootstrap_patches),
                false_alarms=dict(negative_mm=fa[2] if fa else 0, per_100mm=fa[0] if fa else None,
                                  bootstrap95=fa[1] if fa else None, bootstrap_patches=fa_patches))


def test_diff_row_zero_candidate_events_is_not_enough_data():
    cur = _row(recall=None)
    prev = _row(recall=(0.1, (0.05, 0.15), 50))
    out = rf.diff_row(cur, prev)
    assert "not enough new data" in out["recall_verdict"]
    assert "0 new confirmed events" in out["recall_verdict"]


def test_diff_row_zero_candidate_negative_mm_is_not_enough_data():
    cur = _row(fa=None)
    prev = _row(fa=(0.5, (0.1, 1.0), 1000.0))
    out = rf.diff_row(cur, prev)
    assert "not enough new data" in out["fa_verdict"]
    assert "0 mm" in out["fa_verdict"]


def test_diff_row_too_few_bootstrap_patches_is_not_enough_data_even_with_events():
    # 1 counted event/patch is not enough for a trustworthy bootstrap CI, even though it's > 0
    cur = _row(recall=(0.0, (0.0, 0.0), 1), bootstrap_patches=1)
    prev = _row(recall=(0.1, (0.05, 0.15), 50))
    out = rf.diff_row(cur, prev)
    assert "not enough new data" in out["recall_verdict"]
    assert "too few for a trustworthy CI" in out["recall_verdict"]


def test_diff_row_within_noise_when_cis_overlap_and_enough_patches():
    cur = _row(recall=(0.15, (0.05, 0.30), 20), bootstrap_patches=20)
    prev = _row(recall=(0.10, (0.02, 0.20), 50))
    out = rf.diff_row(cur, prev)
    assert out["recall_verdict"] == "within noise (CIs overlap)"


def test_diff_row_changed_beyond_noise_when_cis_disjoint_and_enough_patches():
    cur = _row(recall=(0.90, (0.80, 0.99), 20), bootstrap_patches=20)
    prev = _row(recall=(0.10, (0.02, 0.20), 50))
    out = rf.diff_row(cur, prev)
    assert out["recall_verdict"] == "changed beyond noise (CIs do not overlap)"


def test_diff_row_fa_within_noise_when_enough_scored_patches():
    cur = _row(fa=(0.4, (0.1, 0.9), 500.0), fa_patches=20)
    prev = _row(fa=(0.5, (0.2, 1.0), 8000.0))
    out = rf.diff_row(cur, prev)
    assert out["fa_verdict"] == "within noise (CIs overlap)"

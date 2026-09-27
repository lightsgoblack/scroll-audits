"""Leaderboard rendering: false-alarm CI, the "limited scope" coverage flag/badge and its sort order."""
from __future__ import annotations

from tools.switchbench_kit import leaderboard as lb

FULL = {"name": "full-coverage", "tool": "t@1", "mode": "default", "notes": "", "strata": {},
        "recall": {"recall": 0.5, "hits": 5, "events": 10, "wilson95": [0.2, 0.8]},
        "false_alarms": {"per_100mm": 2.0, "bootstrap95": [1.0, 3.0]},
        "coverage": {"patches": [10, 10], "limited_scope": False}}
LIMITED = {"name": "limited-scope", "tool": "t@2", "mode": "default", "notes": "", "strata": {},
           "recall": {"recall": 0.5, "hits": 1, "events": 2, "wilson95": [0.1, 0.9]},
           "false_alarms": {"per_100mm": 0.0, "bootstrap95": [0.0, 0.0]},
           "coverage": {"patches": [1, 10], "limited_scope": True}}
BOARD = {"meta": {"corpus": {"scroll": "S", "sha256": "abc123def456" * 4}, "generated_utc": "now",
                  "settings": {"match_mm": 1.0, "per_patch_cap": None, "fa_dedup_mm": 0.5},
                  "kit": {"name": "switchbench_kit", "version": "9.9.9"}},
         "rows": [FULL, LIMITED]}


def test_markdown_reports_fa_ci_and_scope_badge():
    md = lb.to_markdown(BOARD)
    assert "FA 95% CI (bootstrap)" in md and "Scope" in md
    assert "[1.00, 3.00]" in md and "n/a" not in md.split("\n\n")[0]
    assert "Full" in md and "Limited scope" in md


def test_html_flags_limited_scope_row_with_a_badge_and_tooltip():
    out = lb.to_html(BOARD)
    assert 'class="limited-scope"' in out
    assert "Limited scope</span>" in out and "title=" in out
    assert "FA 95% CI" in out


def test_equal_recall_sorts_full_coverage_before_limited_scope():
    # LIMITED and FULL tie on recall (0.5) and LIMITED even has the lower FA rate (0.0 vs 2.0) -- full
    # coverage must still sort first, or a detector that barely scored anything would out-rank one that
    # covered the whole corpus (red-team SHOULD FIX 5).
    rows = sorted([LIMITED, FULL], key=lambda r: (-r["recall"]["recall"], bool(r["coverage"]["limited_scope"]),
                                                  r["false_alarms"]["per_100mm"]))
    assert [r["name"] for r in rows] == ["full-coverage", "limited-scope"]


def test_cells_include_fa_ci_and_scope_columns():
    cells = lb._cells(FULL, [])
    assert cells[5] == "[1.00, 3.00]" and cells[7] == "Full"
    cells = lb._cells(LIMITED, [])
    assert cells[5] == "[0.00, 0.00]" and cells[7] == "Limited scope"

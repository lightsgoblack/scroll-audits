"""Detector leaderboard on a SwitchBench corpus: one row per detector entry, rendered as markdown, JSON and HTML.

    python -m tools.switchbench_kit leaderboard --entries entries.json --corpus <events.json> \
        [--patches-dir DIR] [--strata strata.json] --out DIR

entries.json: {"entries": [{"name": "...", "alarms": "path", "tool": "repo@commit", "mode": "default|author-intended|tuned",
                            "notes": "..."}]}
strata.json (optional): {"<patch>|<x>,<y>,<z>": "abrupt" | "gradual", ...}  (event xyz rounded to 0.1 voxel;
    event_index is NOT a stable key across tools, coordinates are)

Rows are ordered by recall, then (at equal recall) full-coverage rows before "limited scope" ones (coverage
below 50% of patches), then by fewer false alarms. Coverage is always shown next to recall: a detector that
returns no verdict on most patches is reported as limited coverage, not as a failure -- flagged with a
"limited scope" badge so a reader skimming the Recall column alone still sees it (red-team SHOULD FIX 5).
Every number comes from tools.switchbench_kit.scoring.score, so a leaderboard row equals what `score` prints
for the same inputs.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

from .alarms import load_alarms
from .corpus import load_benchmark
from .scoring import score, wilson


def load_strata(path: Path | str | None) -> dict:
    if not path:
        return {}
    raw = json.loads(Path(path).read_text())
    return {tuple(k.rsplit("|", 1)): v for k, v in raw.items()}


def strata_recall(res: dict, strata: dict) -> dict:
    out = {}
    for name in sorted(set(strata.values())):
        rows = [e for e in res["events"] if e.get("counted") and strata.get(
            (e["patch"], ",".join(f"{round(v, 1):.1f}" for v in e["xyz"]))) == name]
        k, n = sum(1 for e in rows if e.get("hit")), len(rows)
        out[name] = {"hits": k, "events": n, "recall": k / n if n else None, "wilson95": list(wilson(k, n)) if n else None}
    return out


def run(entries: list[dict], corpus: str, patches_dir: str | None = None, strata_path: str | None = None) -> dict:
    bench = load_benchmark(corpus, patches_dir)
    strata = load_strata(strata_path)
    rows = []
    for e in entries:
        res = score(bench, load_alarms(e["alarms"], bench, detector=e["name"]))
        rows.append({"name": e["name"], "tool": e.get("tool", ""), "mode": e.get("mode", "default"),
                     "notes": e.get("notes", ""), "recall": res["recall"], "false_alarms": res["false_alarms"],
                     "coverage": res["coverage"], "strata": strata_recall(res, strata) if strata else {},
                     "alarms_sha256": res["detector"]["sha256"]})
    # full-coverage rows sort before "limited scope" ones at equal recall (red-team SHOULD FIX 5): a
    # detector that only ever saw a sliver of the corpus shouldn't rank above one that covered it all
    # just because its near-zero coverage also kept its false-alarm rate down.
    rows.sort(key=lambda r: (-(r["recall"]["recall"] or 0.0), bool(r["coverage"]["limited_scope"]),
                             r["false_alarms"]["per_100mm"] if r["false_alarms"]["per_100mm"] is not None
                             else float("inf")))
    meta = {"generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "corpus": {k: v for k, v in res["corpus"].items() if k != "patches_dir"},
            "settings": {k: v for k, v in res["settings"].items() if k != "settings_source"}, "kit": res["kit"]}
    return {"meta": meta, "rows": rows}


def _pct(x):
    return "n/a" if x is None else f"{100 * x:.0f}%"


def _fa_ci(fa: dict) -> str:
    ci = fa.get("bootstrap95")
    return "n/a" if not ci else f"[{ci[0]:.2f}, {ci[1]:.2f}]"


def _scope_badge(cv: dict) -> str:
    return "Limited scope" if cv.get("limited_scope") else "Full"


def _fa_rate(fa: dict) -> str:
    return "n/a" if fa["per_100mm"] is None else f"{fa['per_100mm']:.2f}"


def _cells(r: dict, strata_names: list) -> list[str]:
    rc, fa, cv = r["recall"], r["false_alarms"], r["coverage"]
    cells = [r["name"], r["mode"], f"{_pct(rc['recall'])} ({rc['hits']}/{rc['events']})",
             f"[{_pct(rc['wilson95'][0])}, {_pct(rc['wilson95'][1])}]", _fa_rate(fa),
             _fa_ci(fa), f"{cv['patches'][0]}/{cv['patches'][1]}", _scope_badge(cv)]
    for s in strata_names:
        v = r["strata"].get(s)
        cells.append(f"{_pct(v['recall'])} ({v['hits']}/{v['events']})" if v and v["events"] else "n/a")
    cells.append(r["tool"])
    return cells


def to_markdown(board: dict) -> str:
    rows, meta = board["rows"], board["meta"]
    strata_names = sorted({s for r in rows for s in r["strata"]})
    head = ["Detector", "Mode", "Recall", "95% CI (Wilson)", "False alarms / 100 mm", "FA 95% CI (bootstrap)",
            "Patches with a verdict", "Scope",
            *[f"Recall: {s}" for s in strata_names], "Tool @ commit"]
    lines = [f"# SwitchBench-natural leaderboard ({meta['corpus'].get('scroll', '')})", "",
             f"Generated {meta['generated_utc']} with {meta['kit']['name']} {meta['kit']['version']}. "
             f"Corpus sha256 `{meta['corpus']['sha256'][:16]}...`; matching {meta['settings']['match_mm']} mm; "
             f"per-patch cap {meta['settings']['per_patch_cap']}; false alarms deduplicated at "
             f"{meta['settings']['fa_dedup_mm']} mm.", "",
             "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(_cells(r, strata_names)) + " |" for r in rows]
    lines += ["", "Coverage matters: a detector with few patches with a verdict is limited in scope here, not wrong "
              "-- it's flagged **Limited scope** (fewer than half the patches got a verdict) and sorted after "
              "full-coverage detectors at the same recall, so a 0% false-alarm rate on a sliver of the corpus "
              "doesn't rank above a detector that covered it all. "
              "Every row is reproducible with `python -m tools.switchbench_kit score` on the same inputs."]
    return "\n".join(lines) + "\n"


def to_html(board: dict) -> str:
    rows, meta = board["rows"], board["meta"]
    strata_names = sorted({s for r in rows for s in r["strata"]})
    head = ["Detector", "Mode", "Recall", "95% CI", "FA / 100 mm", "FA 95% CI", "Coverage", "Scope",
            *[f"{s}" for s in strata_names], "Tool"]
    th = "".join(f"<th>{html.escape(h)}</th>" for h in head)

    def row_html(r):
        cells = _cells(r, strata_names)
        scope_i = head.index("Scope")
        tds = []
        for i, c in enumerate(cells):
            if i == scope_i and r["coverage"].get("limited_scope"):
                tds.append(f'<td><span class="badge" title="Fewer than half the patches got a verdict from this '
                           f'detector: its recall and false-alarm numbers describe only the part of the corpus it '
                           f'actually scored, not the whole thing.">{html.escape(c)}</span></td>')
            else:
                tds.append(f"<td>{html.escape(c)}</td>")
        cls = ' class="limited-scope"' if r["coverage"].get("limited_scope") else ""
        return f"<tr{cls}>" + "".join(tds) + "</tr>"

    trs = "".join(row_html(r) for r in rows)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SwitchBench leaderboard</title><style>
:root{{--bg:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--badge-bg:#f1ead0;--badge-ink:#6b5a1f}}
@media (prefers-color-scheme: dark){{:root{{--bg:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--badge-bg:#3a331a;--badge-ink:#e8d68a}}}}
body{{background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;padding:24px 16px}}
main{{max-width:1100px;margin:0 auto}} h1{{font-size:24px;margin:0 0 6px}} p{{color:var(--ink2)}}
.wrap{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}
th{{text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);border-bottom:1px solid var(--axis);padding:8px}}
td{{border-bottom:1px solid var(--grid);padding:8px;white-space:nowrap}}
tr.limited-scope{{opacity:.85}}
.badge{{background:var(--badge-bg);color:var(--badge-ink);border-radius:4px;padding:2px 6px;font-size:12px;cursor:help}}</style></head><body><main>
<h1>SwitchBench-natural leaderboard</h1>
<p>Recall on naturally occurring sheet switches in {html.escape(meta['corpus'].get('scroll', ''))} auto-grown traces. Generated {meta['generated_utc']} with {html.escape(meta['kit']['name'])} {html.escape(meta['kit']['version'])}. Matching {meta['settings']['match_mm']} mm; per-patch cap {meta['settings']['per_patch_cap']}.</p>
<div class="wrap"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>
<p>Coverage matters: a detector with few patches with a verdict is limited in scope here, not wrong -- that's what the
<span class="badge" title="Fewer than half the patches got a verdict from this detector.">Limited scope</span> badge
means. Those rows sort after full-coverage detectors at the same recall. Every row is reproducible with the scorer
kit on the same inputs.</p>
</main></body></html>
"""


def write(board: dict, out: Path | str) -> dict:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "leaderboard.json").write_text(json.dumps(board, indent=1))
    (out / "leaderboard.md").write_text(to_markdown(board))
    (out / "leaderboard.html").write_text(to_html(board))
    return {k: str(out / f"leaderboard.{k}") for k in ("json", "md", "html")}

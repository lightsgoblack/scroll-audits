/* SwitchBench leaderboard viewer + in-browser self-scorer.
 *
 * Recall scoring here mirrors tools/switchbench_kit/scoring.py `score()` exactly for the parts a
 * static page can do without patch geometry: for every already-counted confirmed event (the
 * corpus_events.json export has already applied the corpus's per-patch cap / counted rule), a hit
 * is any alarm within match_mm (converted to voxels with corpus_events.json's vx_per_mm) of ANY of
 * that event's match points (each transition point plus the event centre). A patch's alarms count
 * only if the patch key is present in the alarms file and is not null (a "verdict"); events on a
 * patch with no verdict count as misses, same as the kit. False alarms need the confirmed-clean
 * patch geometry (patch xyz grids), which this page does not ship, so it is not computed here --
 * see the "Score your own detector" panel for the exact kit command.
 *
 * Exposed as `window.SwitchBenchViewer` in a browser, and as CommonJS exports under Node (used only
 * by tools/release/tests/test_viewer_parity.py to check this file against the Python kit).
 */
(function (root, factory) {
  const mod = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = mod;
  } else {
    root.SwitchBenchViewer = mod;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const Z95 = 1.959963984540054;

  function wilson(k, n) {
    if (n === 0) return [null, null, null];
    const p = k / n;
    const z2 = Z95 * Z95;
    const den = 1 + z2 / n;
    const c = (p + z2 / (2 * n)) / den;
    const h = (Z95 * Math.sqrt((p * (1 - p)) / n + z2 / (4 * n * n))) / den;
    return [p, Math.max(0, c - h), Math.min(1, c + h)];
  }

  function dist3(a, b) {
    const dx = a[0] - b[0], dy = a[1] - b[1], dz = a[2] - b[2];
    return Math.sqrt(dx * dx + dy * dy + dz * dz);
  }

  function hasVerdict(alarms, patch) {
    return Object.prototype.hasOwnProperty.call(alarms, patch) && alarms[patch] !== null &&
      alarms[patch] !== undefined;
  }

  /** corpusEvents: the parsed corpus_events.json export. alarms: parsed alarms.json {patch: [[x,y,z],...]|null}.
   *  Returns {hits, events, recall, wilson95, coveragePatches, coverageTotal, perEvent}. */
  function scoreRecall(corpusEvents, alarms) {
    const rVx = corpusEvents.meta.match_mm * corpusEvents.meta.vx_per_mm;
    let hits = 0;
    const perEvent = [];
    for (const ev of corpusEvents.events) {
      const verdict = hasVerdict(alarms, ev.patch);
      const A = verdict ? (alarms[ev.patch] || []) : [];
      let hit = false;
      for (const pt of ev.points) {
        for (const a of A) {
          if (dist3(pt, a) <= rVx) { hit = true; break; }
        }
        if (hit) break;
      }
      if (hit) hits += 1;
      perEvent.push({ patch: ev.patch, xyz: ev.xyz, verdict, hit });
    }
    const n = corpusEvents.events.length;
    const [p, lo, hi] = wilson(hits, n);
    const withVerdict = corpusEvents.patches.filter((p) => hasVerdict(alarms, p)).length;
    return {
      hits, events: n, recall: p, wilson95: [lo, hi],
      coveragePatches: withVerdict, coverageTotal: corpusEvents.patches.length,
      perEvent,
    };
  }

  function fmtPct(x) {
    return x === null || x === undefined ? "n/a" : (100 * x).toFixed(0) + "%";
  }

  function fmtCI(ci) {
    if (!ci || ci[0] === null || ci[0] === undefined) return "n/a";
    return "[" + fmtPct(ci[0]) + ", " + fmtPct(ci[1]) + "]";
  }

  return { wilson, dist3, hasVerdict, scoreRecall, fmtPct, fmtCI };
});

/* ---------------------------------------------------------------------- page wiring (browser only) */
if (typeof window !== "undefined" && typeof document !== "undefined") {
  (function () {
    const V = window.SwitchBenchViewer;
    let leaderboard = null;
    let corpusEvents = null;
    let sortKey = "recall";
    let sortDir = "desc";
    let userRow = null;

    function rowValue(r, key) {
      if (key === "name") return r.name.toLowerCase();
      if (key === "mode") return r.mode.toLowerCase();
      if (key === "recall") return r.recall.recall == null ? -1 : r.recall.recall;
      if (key === "fa") return r.false_alarms.per_100mm == null ? Infinity : r.false_alarms.per_100mm;
      if (key === "coverage") return r.coverage.patches[0] / Math.max(1, r.coverage.patches[1]);
      return 0;
    }

    // Fewer than half the patches with a verdict: "limited scope", not a failure -- see the badge and
    // its tooltip below. Plain English: this detector only ever looked at a sliver of the corpus, so
    // its numbers describe that sliver, not the whole thing.
    function isLimitedScope(r) {
      if (typeof r.coverage.limited_scope === "boolean") return r.coverage.limited_scope;
      return r.coverage.patches[0] / Math.max(1, r.coverage.patches[1]) < 0.5;
    }

    function sortedRows() {
      const rows = leaderboard.rows.slice();
      if (userRow) rows.push(userRow);
      rows.sort((a, b) => {
        const av = rowValue(a, sortKey), bv = rowValue(b, sortKey);
        if (av !== bv) return av < bv ? (sortDir === "asc" ? -1 : 1) : (sortDir === "asc" ? 1 : -1);
        // tie-break: at equal sort value (typically equal recall), full-coverage rows come first so a
        // detector that barely scored anything doesn't out-rank one that covered the whole corpus.
        const al = isLimitedScope(a) ? 1 : 0, bl = isLimitedScope(b) ? 1 : 0;
        return al - bl;
      });
      return rows;
    }

    function fmtFaCi(fa) {
      const ci = fa && fa.bootstrap95;
      if (!ci || ci[0] === null || ci[0] === undefined) return "n/a";
      return `[${ci[0].toFixed(2)}, ${ci[1].toFixed(2)}]`;
    }

    function renderTable() {
      const tbody = document.getElementById("board-body");
      tbody.innerHTML = "";
      for (const r of sortedRows()) {
        const tr = document.createElement("tr");
        if (r.isYou) tr.className = "you-row";
        const limited = isLimitedScope(r);
        if (limited) tr.classList.add("limited-scope");
        const rc = r.recall, fa = r.false_alarms, cv = r.coverage;
        const cells = [
          r.name,
          r.mode,
          `${V.fmtPct(rc.recall)} (${rc.hits}/${rc.events})`,
          V.fmtCI(rc.wilson95),
          fa.per_100mm == null ? "n/a" : fa.per_100mm.toFixed(2),
          fmtFaCi(fa),
          `${cv.patches[0]}/${cv.patches[1]}`,
          r.tool || "",
        ];
        cells.forEach((c, i) => {
          const td = document.createElement("td");
          if (i === 6) {
            // coverage cell: add the "limited scope" badge with a plain-English tooltip in place
            td.textContent = c + " ";
            if (limited) {
              const badge = document.createElement("span");
              badge.className = "badge";
              badge.textContent = "Limited scope";
              badge.title = "Fewer than half the patches got a verdict from this detector: its recall and " +
                "false-alarm numbers describe only the part of the corpus it actually scored, not the whole thing.";
              td.appendChild(badge);
            }
          } else {
            td.textContent = c;
          }
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      }
      document.querySelectorAll(".sort-btn").forEach((btn) => {
        const arrow = btn.querySelector(".arrow");
        arrow.textContent = btn.dataset.key === sortKey ? (sortDir === "asc" ? "↑" : "↓") : "";
      });
    }

    function wireSorting() {
      document.querySelectorAll(".sort-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const key = btn.dataset.key;
          if (sortKey === key) {
            sortDir = sortDir === "asc" ? "desc" : "asc";
          } else {
            sortKey = key;
            sortDir = key === "fa" ? "asc" : "desc";
          }
          renderTable();
        });
      });
    }

    async function loadData() {
      const metaEl = document.getElementById("board-meta");
      try {
        const [lbRes, ceRes] = await Promise.all([fetch("leaderboard.json"), fetch("corpus_events.json")]);
        leaderboard = await lbRes.json();
        corpusEvents = await ceRes.json();
        const m = leaderboard.meta || {};
        const settings = m.settings || {};
        metaEl.textContent = `${m.corpus ? m.corpus.scroll || "" : ""} · generated ${m.generated_utc || "?"} ` +
          `· match ${settings.match_mm ?? "?"} mm · ${leaderboard.rows.length} detectors`;
        renderTable();
      } catch (err) {
        metaEl.textContent = "Could not load leaderboard.json / corpus_events.json next to this page.";
        console.error(err);
      }
    }

    function setStatus(msg, state) {
      const el = document.getElementById("scorer-status");
      el.textContent = msg;
      if (state) el.dataset.state = state; else delete el.dataset.state;
    }

    function renderResult(res) {
      const card = document.getElementById("scorer-result");
      card.hidden = false;
      const rows = sortedRows().filter((r) => !r.isYou);
      let rank = 1;
      for (const r of rows) {
        if ((r.recall.recall || 0) > (res.recall || 0)) rank += 1;
      }
      card.innerHTML = "";
      const head = document.createElement("div");
      head.className = "headline";
      head.textContent = `Recall: ${V.fmtPct(res.recall)} (${res.hits}/${res.events})`;
      const sub = document.createElement("div");
      sub.className = "sub";
      sub.textContent = `Would rank #${rank} of ${rows.length + 1} by recall alone (false alarms not scored here).`;
      const dl = document.createElement("dl");
      const items = [
        ["95% CI (Wilson)", V.fmtCI(res.wilson95)],
        ["Coverage", `${res.coveragePatches}/${res.coverageTotal} patches with a verdict`],
      ];
      for (const [k, v] of items) {
        const dt = document.createElement("dt"); dt.textContent = k;
        const dd = document.createElement("dd"); dd.textContent = v;
        dl.appendChild(dt); dl.appendChild(dd);
      }
      card.appendChild(head);
      card.appendChild(sub);
      card.appendChild(dl);
    }

    function wireScorer() {
      const input = document.getElementById("alarms-file");
      input.addEventListener("change", () => {
        const file = input.files && input.files[0];
        if (!file) return;
        setStatus("Reading and scoring …");
        const reader = new FileReader();
        reader.onload = () => {
          let alarms;
          try {
            const raw = JSON.parse(reader.result);
            alarms = raw && typeof raw === "object" && raw.alarms && typeof raw.alarms === "object" ? raw.alarms : raw;
          } catch (e) {
            setStatus("That file is not valid JSON.", "error");
            return;
          }
          if (!corpusEvents) {
            setStatus("Corpus data has not loaded yet; try again in a moment.", "error");
            return;
          }
          try {
            const res = V.scoreRecall(corpusEvents, alarms);
            setStatus(`Scored ${res.events} events across ${corpusEvents.patches.length} patches.`, "ok");
            userRow = {
              name: `${file.name} (you)`, mode: "self-scored", tool: "",
              isYou: true,
              recall: { recall: res.recall, hits: res.hits, events: res.events, wilson95: res.wilson95 },
              false_alarms: { per_100mm: null },
              coverage: { patches: [res.coveragePatches, res.coverageTotal] },
            };
            renderResult(res);
            renderTable();
          } catch (e) {
            setStatus("Could not score that file: " + e.message, "error");
          }
        };
        reader.onerror = () => setStatus("Could not read that file.", "error");
        reader.readAsText(file);
      });
    }

    document.addEventListener("DOMContentLoaded", () => {
      wireSorting();
      wireScorer();
      loadData();
    });
  })();
}

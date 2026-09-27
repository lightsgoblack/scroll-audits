"""Monthly SwitchBench-natural leaderboard refresh (job 6, the frozen-criteria history/the settled-rules file corpus pipeline).

In plain English: this checks the scrollprize Hugging Face bucket for newly auto-grown PHercParis4
patches (batches added since the v1 corpus was built), runs the *exact same, unchanged* labeling and
confirmation code v1 used on up to N of them, re-scores every detector that already has a kit adapter,
and reports whether the resulting mini "v1.1" leaderboard differs from the sealed v1 one by more than
sampling noise would explain. Nothing here re-tunes any threshold and nothing here publishes anything;
every subcommand is dry-run only and writes exclusively under data/switchbench_refresh/ (gitignored).

Three resumable subcommands:
  list                    list auto-grown batches on the bucket newer than the v1 corpus date (listing
                           only, no download). Writes data/switchbench_refresh/new_batches.json.
  run --max-patches N     pull + label + CT-confirm (level-2 and level-0, frozen thresholds) up to N
                           new patches (checkpointed per patch), then re-score every detector that has
                           a tools/switchbench_kit/adapters/ entry on the resulting mini corpus. Writes
                           data/switchbench_refresh/leaderboard_candidate.{json,md}.
  diff                    compare the candidate leaderboard against the sealed
                           results/switchbench_natural_v1_leaderboard/leaderboard.json, per detector, and say
                           plainly whether anything moved beyond noise (bootstrap-CI overlap).

Frozen means frozen: this module calls tools.switchbench.corpus_v1, confirm_l0, detectors_v1, doctor_v1
and run_windaudit_v1 exactly as v1 called them (same thresholds, same rule files), only redirecting
their output paths (all hold their output directory in a single reassignable module attribute, patched
here for the duration of one call) so a refresh run never writes into data/switchbench_v1/ and never
touches data/switchbench_v1/blind_key.json (not imported, not opened, not referenced anywhere below).

Usage:
    python -m tools.switchbench.refresh list
    python -m tools.switchbench.refresh run --max-patches 3
    python -m tools.switchbench.refresh diff
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

from . import confirm_l0, corpus_v1, detectors_v1, doctor_v1, geom, pull, run_windaudit_v1
from .robustness_v1 import batch_of  # noqa: F401  (re-exported for callers/tests that want the same date rule)

REPO = geom.REPO
DATA = geom.DATA                                   # data/paris4 (shared patch-geometry cache)
V1 = REPO / "data" / "switchbench_v1"
REFRESH = REPO / "data" / "switchbench_refresh"    # gitignored; everything this module writes lives here
ORDER_FILE = DATA / "unverified_order.json"        # the full known unverified-patch pool (seeded 20260925)
FILES_FILE = DATA / "unverified_files.json"        # that pool's file listing, for size estimation

BUCKET = "scrollprize/datasets"
ROOT = "spiral/PHercParis4"
PREFIX = f"{ROOT}/unverified_patches/"

SEALED_LEADERBOARD = REPO / "vault" / "release" / "prebuilt" / "leaderboard_v1" / "leaderboard.json"
# The sealed v1 leaderboard names one row differently (added after the freeze); everything else matches
# the candidate's own DETECTOR_SPECS names verbatim.
SEALED_NAME_ALIASES = {"seamcheck": "seamcheck [secondary, added after freeze]"}
NEW_BATCHES_JSON = REFRESH / "new_batches.json"
CANDIDATE_EVENTS_JSON = REFRESH / "events_candidate.json"
CANDIDATE_ENTRIES_JSON = REFRESH / "entries_candidate.json"
LEADERBOARD_OUT = REFRESH  # leaderboard_candidate.{json,md,html} land directly here (see run())

FULL_BATCH_RE = re.compile(r"^auto_grown_(\d{17})_region_\d+$")
MIN_FREE = 3 * 2**30       # smoke-test disk floor (task budget: under 3 GB of downloads)
DOWNLOAD_BUDGET = 3 * 2**30

# Detectors with a tools/switchbench_kit/adapters/ entry, and how to read frozen v1 alarm output for
# each (grid rc's or 3-D xyz points; see doctor_v1.run / detectors_v1.py's own per-detector records,
# which are already the exact fields v1's leaderboard alarms were built from).
DETECTOR_SPECS = [
    dict(name="tifxyz-doctor (coherent-normal-step)", key="doctor", field="alarms_primary", fmt="grid"),
    dict(name="tifxyz-doctor (any cue)", key="doctor", field="alarms_any", fmt="grid"),
    dict(name="windcheck", key="windcheck_default", field="alarms_xyz", fmt="xyz"),
    dict(name="windcheck [author-intended: patch mode, no cell floor]", key="windcheck_patchmode",
         field="alarms_xyz", fmt="xyz"),
    dict(name="windaudit", key="windaudit_default", field="alarms_xyz", fmt="xyz"),
    dict(name="windaudit [author-intended: attachment 0.45 D]", key="windaudit_intended",
         field="alarms_xyz", fmt="xyz"),
    dict(name="#1621-style annotation check", key="annot1621", field=None, fmt="xyz"),  # special-cased below
    dict(name="seamcheck", key="seamcheck", field="alarms_xyz", fmt="xyz"),
]


# =============================================================================================== list
def batch_full_id(name: str) -> str | None:
    """Full 17-digit growth-batch timestamp (many regions share one), or None for a non-auto-grown name."""
    m = FULL_BATCH_RE.match(name)
    return m.group(1) if m else None


def ts_to_iso(ts: str) -> str:
    """17-digit auto_grown timestamp YYYYMMDDHHMMSSmmm -> ISO date (day resolution, UTC as stored)."""
    return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"


def corpus_cutoff_ts(known_names: list[str]) -> str | None:
    """The v1 corpus date: the newest growth-batch timestamp among all patches the corpus was drawn
    from (unverified_order.json, the full seeded pool v1's [3000:10000] slice is cut from). Any batch
    newer than this was not yet on the bucket when v1 was built."""
    ts = [batch_full_id(n) for n in known_names]
    ts = [t for t in ts if t]
    return max(ts) if ts else None


def group_new_batches(new_names: list[str]) -> list[dict]:
    """Group newly-seen auto_grown names by growth-batch timestamp, sorted oldest first."""
    by_batch: dict[str, list[str]] = {}
    for n in new_names:
        b = batch_full_id(n)
        if b is None:
            continue
        by_batch.setdefault(b, []).append(n)
    out = []
    for b in sorted(by_batch):
        patches = sorted(by_batch[b])
        out.append(dict(batch_id=b, batch_date_utc=ts_to_iso(b), n_patches=len(patches), patches=patches))
    return out


def estimate_bytes_per_patch(files_listing: list) -> float:
    """Mean total bytes per known patch (x/y/z/meta[/mask]), from the local file listing already
    pulled for the known pool -- used only to *estimate* new-batch download size, no download here."""
    per_patch: dict[str, int] = {}
    for rel, size in files_listing:
        # rel like ".../unverified_patches/<patch>/<file>"
        parts = rel.split("/")
        if "unverified_patches" not in parts:
            continue
        i = parts.index("unverified_patches")
        if i + 1 >= len(parts):
            continue
        patch = parts[i + 1]
        per_patch[patch] = per_patch.get(patch, 0) + size
    if not per_patch:
        return 0.0
    return sum(per_patch.values()) / len(per_patch)


def list_live_patches() -> list[str]:
    """Non-recursive listing of spiral/PHercParis4/unverified_patches/ -- folder names only, no
    per-file sizes, no download. Same call fetch.py already uses for the ink-segment bucket."""
    from huggingface_hub import list_bucket_tree
    live = []
    for f in list_bucket_tree(BUCKET, prefix=PREFIX, recursive=False, token=False):
        if type(f).__name__ == "BucketFolder":
            live.append(f.path[len(PREFIX):])
        elif type(f).__name__ == "BucketFile":
            # a stray file directly under unverified_patches/ (not expected, but don't choke on it)
            continue
    return live


def cmd_list() -> dict:
    REFRESH.mkdir(parents=True, exist_ok=True)
    known = json.load(open(ORDER_FILE)) if ORDER_FILE.exists() else []
    known_set = set(known)
    cutoff = corpus_cutoff_ts(known)
    live = list_live_patches()
    new_names = sorted(n for n in live if n not in known_set)
    batches = group_new_batches(new_names)
    non_auto_grown_new = sorted(n for n in new_names if batch_full_id(n) is None)

    # sanity: every batch we're calling "new" really is newer than the corpus cutoff
    if cutoff is not None:
        for b in batches:
            assert b["batch_id"] > cutoff, f"batch {b['batch_id']} not newer than cutoff {cutoff}"

    est_bytes = 0.0
    if new_names and FILES_FILE.exists():
        per_patch = estimate_bytes_per_patch(json.load(open(FILES_FILE)))
        est_bytes = per_patch * len(new_names)

    out = dict(
        generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        bucket=BUCKET, prefix=PREFIX,
        v1_corpus_cutoff_batch_ts=cutoff, v1_corpus_cutoff_date=ts_to_iso(cutoff) if cutoff else None,
        known_patch_count=len(known_set), live_patch_count=len(live),
        new_patch_count=len(new_names), new_batch_count=len(batches),
        non_auto_grown_new_count=len(non_auto_grown_new),
        estimated_download_bytes=est_bytes, estimated_download_gb=est_bytes / 2**30,
        batches=batches,
    )
    json.dump(out, open(NEW_BATCHES_JSON, "w"), indent=2)
    return out


def print_list_summary(out: dict) -> None:
    print(f"v1 corpus cutoff: batch {out['v1_corpus_cutoff_batch_ts']} ({out['v1_corpus_cutoff_date']})")
    print(f"live on bucket: {out['live_patch_count']} patches; known to v1's pool: {out['known_patch_count']}")
    if out["new_patch_count"] == 0:
        print("no new auto-grown batches since the v1 corpus date -- nothing to pull")
    else:
        print(f"{out['new_batch_count']} new batch(es), {out['new_patch_count']} new patches, "
              f"~{out['estimated_download_gb']:.3f} GB estimated")
        for b in out["batches"]:
            print(f"  {b['batch_date_utc']}  batch {b['batch_id']}  {b['n_patches']} patches")
    if out["non_auto_grown_new_count"]:
        print(f"({out['non_auto_grown_new_count']} new non-auto-grown name(s) seen too, not counted as a batch)")
    print(f"wrote {NEW_BATCHES_JSON}")


# =============================================================================================== run
def pick_smoke_patches(n: int) -> list[str]:
    """No new batches: prove the pipeline wiring on n patches already in the v1 corpus (geometry
    already cached locally), preferring ones with candidate events so the L0-confirm and detector
    re-scoring paths actually run, not just the labeler. Output is redirected to data/switchbench_refresh/
    (never data/switchbench_v1/), so this never mutates or shadows the sealed v1 corpus."""
    v1_corpus = corpus_v1.CORPUS1  # real v1 corpus dir (read-only here)
    if not v1_corpus.exists():
        raise SystemExit(f"no new batches and no local v1 corpus at {v1_corpus} to smoke-test against")
    with_events, without = [], []
    for f in sorted(v1_corpus.glob("*.json")):
        r = json.load(open(f))
        if not r.get("in_sample"):
            continue
        (with_events if r.get("events") else without).append(r["patch"])
    chosen = (with_events + without)[:n]
    if not chosen:
        raise SystemExit("no in-sample v1 patches found to smoke-test against")
    return chosen


def disk_check() -> None:
    free = shutil.disk_usage(REPO).free
    if free < MIN_FREE:
        raise SystemExit(f"STOP: free disk {free/2**30:.2f} GB < {MIN_FREE/2**30:.0f} GB floor")


def ensure_geometry(nm: str, downloaded: list) -> None:
    """Pull one patch's small tifxyz files if not already cached; record it in `downloaded` so run()
    deletes exactly the files it fetched (never a pre-existing shared-cache patch) once done with it."""
    d = DATA / "unverified_patches" / nm
    if d.exists() and (d / "x.tif").exists():
        return
    disk_check()
    pull.pull_unverified([nm])
    downloaded.append(nm)


def delete_patch_geometry(nm: str) -> None:
    """Delete one patch's downloaded raw tifxyz files -- explicit, literal path, no shell variable."""
    d = DATA / "unverified_patches" / nm
    if d.exists():
        shutil.rmtree(d)


def _rc_or_xyz_to_xyz(P, pts, fmt: str) -> list:
    if fmt == "xyz":
        return [list(map(float, p)) for p in pts]
    out = []
    for rc in pts:
        r, c = int(rc[0]), int(rc[1])
        if 0 <= r < P.shape[0] and 0 <= c < P.shape[1]:
            v = P[r, c]
            if all(x == x for x in v):  # not NaN
                out.append([float(v[0]), float(v[1]), float(v[2])])
    return out


def build_alarms(patches: list[str]) -> dict:
    """Run every adapter-covered detector on `patches` (frozen v1 code, output redirected below) and
    return {spec_name: {patch: [[x,y,z], ...]}} in the kit's xyz alarm format."""
    old = dict(det_det=detectors_v1.DET, doc_out=doctor_v1.OUT, wa_v1=run_windaudit_v1.V1)
    detectors_v1.DET = REFRESH / "detect"
    doctor_v1.OUT = REFRESH / "detect" / "tifxyz_doctor"
    run_windaudit_v1.V1 = REFRESH
    try:
        for nm in patches:
            detectors_v1.run_patch(nm)
        alarms = {spec["name"]: {} for spec in DETECTOR_SPECS}
        for nm in patches:
            d = DATA / "unverified_patches" / nm
            P = geom.load_tifxyz(d)
            doctor_rec = json.load(open(doctor_v1.OUT / f"{nm}.json"))
            wc_def = json.load(open(detectors_v1.DET / "windcheck" / f"{nm}.json"))
            wc_pm = json.load(open(detectors_v1.DET / "windcheck_patchmode" / f"{nm}.json"))
            wa_def = json.load(open((REFRESH / "detect" / "windaudit_default") / f"{nm}.json"))
            wa_int = json.load(open((REFRESH / "detect" / "windaudit_intended") / f"{nm}.json"))
            a1621 = json.load(open(detectors_v1.DET / "annot1621" / f"{nm}.json"))
            sc = json.load(open(detectors_v1.DET / "seamcheck" / f"{nm}.json"))
            records = dict(doctor=doctor_rec, windcheck_default=wc_def, windcheck_patchmode=wc_pm,
                            windaudit_default=wa_def, windaudit_intended=wa_int, annot1621=a1621,
                            seamcheck=sc)
            for spec in DETECTOR_SPECS:
                rec = records[spec["key"]]
                if spec["key"] == "annot1621":
                    pts = [a["xyz_p"] for a in rec.get("alarms", [])] + [a["xyz_q"] for a in rec.get("alarms", [])]
                    alarms[spec["name"]][nm] = pts
                else:
                    pts = rec.get(spec["field"], [])
                    alarms[spec["name"]][nm] = _rc_or_xyz_to_xyz(P, pts, spec["fmt"])
        return alarms
    finally:
        detectors_v1.DET, doctor_v1.OUT, run_windaudit_v1.V1 = old["det_det"], old["doc_out"], old["wa_v1"]


def build_events_file(records: list[dict]) -> dict:
    """v1-schema events file (same field names switchbench_v1_events.json uses) built only from the
    patches this refresh actually processed. status = level-0 (2.4 um) verdict when the patch had
    candidates and L0 confirmation ran, else the level-2 rule's verdict (mirrors v1's own precedence)."""
    events, negatives, multi = [], [], []
    for rec, l0 in records:
        if not rec.get("in_sample"):
            continue
        l0_by_i = {e["i"]: e for e in (l0 or {}).get("events", [])} if l0 else {}
        for i, e in enumerate(rec.get("events", [])):
            l0e = l0_by_i.get(i)
            status = l0e["status_l0"] if l0e else e["status"]
            events.append(dict(patch=rec["patch"], subset="refresh", status=status, status_v0rule=e["status"],
                               xyz=[round(v, 1) for v in e["xyz"]], delta_signs=e["delta_signs"],
                               transitions=[dict(axis=m["axis"], rc_a=m["rc_a"], rc_b=m["rc_b"],
                                                 len_a_mm=round(m["len_a_mm"], 2), len_b_mm=round(m["len_b_mm"], 2))
                                            for m in e["members"]]))
        for n in rec.get("negatives", []):
            negatives.append(dict(patch=rec["patch"], subset="refresh", status=n["status"], axis=n["axis"],
                                  rc0=n["verts"][0], rc1=n["verts"][-1], len_mm=round(n["len_mm"], 2),
                                  xyz0=[round(v, 1) for v in n["xyz0"]], xyz1=[round(v, 1) for v in n["xyz1"]]))
        for m in rec.get("multi_wrap", []):
            multi.append(dict(patch=rec["patch"], xyz=[round(v, 1) for v in m["xyz"]], delta_signs=m["delta_signs"]))
    return dict(scroll="PHercParis4", frame="level-2 voxels (x, y, z) of volume 20260411134726 (9.6 um/vx)",
               voxel_mm=geom.VOXEL_MM,
               source="monthly refresh dry run: HF bucket spiral/PHercParis4 unverified_patches, "
                      "frozen v1 corpus pipeline (tools.switchbench.refresh)",
               scoring=dict(per_patch_cap=3, match_mm=1.0, fa_dedup_mm=0.5, bootstrap=2000, seed=20260925),
               events=events, negatives=negatives, multi_wrap=multi)


def cmd_run(max_patches: int) -> dict:
    REFRESH.mkdir(parents=True, exist_ok=True)
    for sub in ("corpus", "regeom", "l0", "detect", "checkpoints"):
        (REFRESH / sub).mkdir(parents=True, exist_ok=True)

    new_batches = json.load(open(NEW_BATCHES_JSON)) if NEW_BATCHES_JSON.exists() else cmd_list()
    new_names = [p for b in new_batches["batches"] for p in b["patches"]]
    mode = "new_batches"
    if not new_names:
        mode = "smoke_test_existing_v1_patches"
        new_names = pick_smoke_patches(max_patches)
    patches = new_names[:max_patches]

    old_c1, old_regeom = corpus_v1.CORPUS1, corpus_v1.REGEOM
    corpus_v1.CORPUS1, corpus_v1.REGEOM = REFRESH / "corpus", REFRESH / "regeom"
    old_l0 = confirm_l0.OUT
    confirm_l0.OUT = REFRESH / "l0"
    downloaded: list[str] = []
    sampler = None
    l0_params = None
    t0 = time.time()
    records = []
    try:
        disk_check()
        for nm in patches:
            ensure_geometry(nm, downloaded)
            rec = corpus_v1._process_new(nm)
            l0 = None
            if rec.get("in_sample") and rec.get("events"):
                if sampler is None:
                    from .ct0 import Sampler
                    sampler = Sampler(0, max_chunks=360)
                    l0_params = confirm_l0.load_rule()
                l0 = confirm_l0.do_patch(sampler, rec, l0_params, source="refresh")
            records.append((rec, l0))
            # geometry for a freshly-downloaded patch is kept just long enough for build_alarms() below
            # (which still needs x/y/z.tif to turn detector grid alarms into 3-D points); deleted after.
        alarms = build_alarms(patches)
    finally:
        corpus_v1.CORPUS1, corpus_v1.REGEOM = old_c1, old_regeom
        confirm_l0.OUT = old_l0
        if mode == "new_batches":
            for nm in downloaded:
                delete_patch_geometry(nm)

    events_file = build_events_file(records)
    json.dump(events_file, open(CANDIDATE_EVENTS_JSON, "w"), indent=2)

    alarms_dir = REFRESH / "alarms"
    alarms_dir.mkdir(exist_ok=True)
    entries = []
    for spec in DETECTOR_SPECS:
        p = alarms_dir / (spec["key"] + ("_primary" if spec["field"] == "alarms_primary" else
                                          "_any" if spec["field"] == "alarms_any" else "") + ".json")
        json.dump(alarms[spec["name"]], open(p, "w"))
        entries.append(dict(name=spec["name"], alarms=str(p.relative_to(REPO)), tool=spec["key"], mode="default"))
    json.dump(dict(entries=entries), open(CANDIDATE_ENTRIES_JSON, "w"), indent=2)

    from tools.switchbench_kit.leaderboard import run as lb_run, to_markdown, write
    board = lb_run(entries, str(CANDIDATE_EVENTS_JSON), str(DATA / "unverified_patches"), None)
    paths = write(board, str(LEADERBOARD_OUT))
    # write() names its files leaderboard.{json,md,html}; alias to the task-specified name
    for ext in ("json", "md", "html"):
        src = LEADERBOARD_OUT / f"leaderboard.{ext}"
        dst = LEADERBOARD_OUT / f"leaderboard_candidate.{ext}"
        if src.exists():
            shutil.copyfile(src, dst)

    summary = dict(mode=mode, patches_processed=patches, n_patches=len(patches),
                   n_in_sample=sum(1 for r, _ in records if r.get("in_sample")),
                   n_candidate_events=sum(len(r.get("events", [])) for r, _ in records),
                   n_confirmed_events_l0=sum(1 for r, l0 in records for e in (l0 or {}).get("events", [])
                                             if e["status_l0"] == "confirmed"),
                   wall_s=time.time() - t0, downloaded_and_deleted=sorted(downloaded))
    json.dump(summary, open(REFRESH / "run_summary.json", "w"), indent=2)
    return summary


# =============================================================================================== diff
def overlaps(a: tuple, b: tuple) -> bool:
    """Two [lo, hi] 95% CIs overlap (or either is missing, in which case we can't tell -> treat as
    overlap, i.e. not a confident 'changed' claim)."""
    if a is None or b is None:
        return True
    return a[0] <= b[1] and b[0] <= a[1]


MIN_BOOTSTRAP_PATCHES = 5  # below this, a patch-block bootstrap CI is too degenerate to trust (e.g. a
                           # 1-patch sample resamples the same patch every draw -> a zero-width CI that
                           # would look like "changed beyond noise" for no real reason)


def diff_row(cur: dict, prev: dict) -> dict:
    """One detector's candidate-vs-sealed comparison. 'changed' only when the two bootstrap CIs don't
    overlap AND the candidate CI itself rests on enough patches to be trusted; 'not enough new data'
    when the candidate has zero events/mm, or too few patches for a non-degenerate bootstrap CI."""
    out = dict(name=cur["name"])
    cr, pr = cur.get("recall", {}), prev.get("recall", {})
    if not cr.get("events"):
        out["recall_verdict"] = "not enough new data (0 new confirmed events)"
    elif cr.get("bootstrap_patches", 0) < MIN_BOOTSTRAP_PATCHES:
        out["recall_verdict"] = (f"not enough new data ({cr.get('bootstrap_patches', 0)} patch(es) with a "
                                 f"counted event -- too few for a trustworthy CI)")
    else:
        ov = overlaps(tuple(cr.get("bootstrap95") or (None, None)) if cr.get("bootstrap95") else None,
                      tuple(pr.get("bootstrap95") or (None, None)) if pr.get("bootstrap95") else None)
        out["recall_verdict"] = "within noise (CIs overlap)" if ov else "changed beyond noise (CIs do not overlap)"
    out["recall_candidate"], out["recall_sealed"] = cr.get("recall"), pr.get("recall")

    cf, pf = cur.get("false_alarms", {}), prev.get("false_alarms", {})
    if not cf.get("negative_mm"):
        out["fa_verdict"] = "not enough new data (0 mm of new confirmed negative run)"
    elif cf.get("bootstrap_patches", 0) < MIN_BOOTSTRAP_PATCHES:
        out["fa_verdict"] = (f"not enough new data ({cf.get('bootstrap_patches', 0)} scored patch(es) -- "
                             f"too few for a trustworthy CI)")
    else:
        ov = overlaps(tuple(cf.get("bootstrap95") or (None, None)) if cf.get("bootstrap95") else None,
                      tuple(pf.get("bootstrap95") or (None, None)) if pf.get("bootstrap95") else None)
        out["fa_verdict"] = "within noise (CIs overlap)" if ov else "changed beyond noise (CIs do not overlap)"
    out["fa_candidate"], out["fa_sealed"] = cf.get("per_100mm"), pf.get("per_100mm")
    return out


def cmd_diff() -> dict:
    cand_f = LEADERBOARD_OUT / "leaderboard_candidate.json"
    if not cand_f.exists():
        raise SystemExit(f"no candidate leaderboard at {cand_f}; run `refresh run` first")
    if not SEALED_LEADERBOARD.exists():
        raise SystemExit(f"no sealed leaderboard at {SEALED_LEADERBOARD}")
    cand = json.load(open(cand_f))
    sealed = json.load(open(SEALED_LEADERBOARD))
    sealed_by_name = {r["name"]: r for r in sealed["rows"]}
    rows = []
    for r in cand["rows"]:
        sealed_name = SEALED_NAME_ALIASES.get(r["name"], r["name"])
        if sealed_name in sealed_by_name:
            rows.append(diff_row(r, sealed_by_name[sealed_name]))
    any_beyond_noise = any("changed beyond noise" in r["recall_verdict"] or "changed beyond noise" in r["fa_verdict"]
                           for r in rows)
    out = dict(generated_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               candidate=str(cand_f), sealed=str(SEALED_LEADERBOARD),
               any_beyond_noise=any_beyond_noise, rows=rows)
    json.dump(out, open(REFRESH / "diff.json", "w"), indent=2)
    return out


def print_diff(out: dict) -> None:
    print(f"{'detector':<55} {'recall verdict':<45} {'FA verdict'}")
    for r in out["rows"]:
        print(f"{r['name']:<55} {r['recall_verdict']:<45} {r['fa_verdict']}")
    print()
    if out["any_beyond_noise"]:
        print("VERDICT: at least one detector moved beyond noise -- review before treating this as v1.1.")
    else:
        print("VERDICT: nothing changed beyond sampling noise (expected on a handful of new patches).")


# =============================================================================================== CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("run")
    r.add_argument("--max-patches", type=int, required=True)
    sub.add_parser("diff")
    args = ap.parse_args(argv)

    if args.cmd == "list":
        print_list_summary(cmd_list())
    elif args.cmd == "run":
        s = cmd_run(args.max_patches)
        print(json.dumps(s, indent=2))
    elif args.cmd == "diff":
        print_diff(cmd_diff())
    return 0


if __name__ == "__main__":
    sys.exit(main())

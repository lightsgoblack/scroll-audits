"""Human-readable rendering of a score result (the JSON form is the result dict itself)."""
from __future__ import annotations

import json
from pathlib import Path


def _f(x, nd=3):
    return "n/a" if x is None else f"{x:.{nd}f}"


def _ci(v, nd=3):
    return "n/a" if not v or v[0] is None else f"[{v[0]:.{nd}f}, {v[1]:.{nd}f}]"


def warnings(res: dict) -> list:
    d, c, s = res["detector"], res["corpus"], res["settings"]
    out = []
    if c["geometry_check"] == "MISMATCH":
        out.append("patch geometry differs from the geometry this corpus was released on (fingerprint "
                   "mismatch): re-fetch the patches; these numbers are not comparable")
    if d["unknown_patch_ids"]:
        ids = ", ".join(d["unknown_patch_ids"][:5])
        out.append(f"{len(d['unknown_patch_ids'])} patch id(s) in the alarms are not in the corpus and were "
                   f"ignored (typo or path instead of id?): {ids}{' ...' if len(d['unknown_patch_ids']) > 5 else ''}")
    if d["unscored_patches_ignored"]:
        out.append(f"{len(d['unscored_patches_ignored'])} corpus patch(es) in the alarms carry no confirmed event or "
                   "run and were ignored")
    if d["dropped_invalid_vertices"]:
        out.append(f"{d['dropped_invalid_vertices']} grid/mask alarm(s) sat on invalid vertices (-1 or masked) and "
                   "were dropped")
    if d["alarms_off_surface"]:
        out.append(f"{d['alarms_off_surface']} of {d['alarms_on_scored_patches']} alarm(s) lie more than "
                   f"{s['match_mm']:g} mm from their patch's surface and can never match; check the frame "
                   "(level-2 voxels, x y z order)")
    cp = res["coverage"]["patches"]
    if cp[0] < cp[1]:
        out.append(f"no verdict on {cp[1] - cp[0]} of {cp[1]} scored patches: their events count as misses "
                   "(see coverage)")
    return out


def format_report(res: dict, per_event: bool = False) -> str:
    c, d, s = res["corpus"], res["detector"], res["settings"]
    R, F, C = res["recall"], res["false_alarms"], res["coverage"]
    cap = s["per_patch_cap"]
    L = [f"SwitchBench scorer kit {res['kit']['version']}",
         f"Corpus    {c['path']} (sha256 {c['sha256'][:12]}), {c['scored_patches']} scored patches, "
         f"geometry fingerprint: {c['geometry_check']}",
         f"Detector  {d['name']} ({d['format']}: {d['source']})",
         f"Settings  match {s['match_mm']:g} mm (3D) | false-alarm de-dup {s['fa_dedup_mm']:g} mm | per-patch cap "
         f"{cap if cap else 'none'} | bootstrap B = {s['bootstrap']}, seed {s['seed']}",
         "",
         "| Metric | Value |",
         "|---|---|",
         f"| Recall (hits / events) | {_f(R['recall'])} ({R['hits']}/{R['events']}) |",
         f"| 95% Wilson CI | {_ci(R['wilson95'])} |",
         f"| 95% patch-block bootstrap CI ({R['bootstrap_patches']} patches) | {_ci(R['bootstrap95'])} |",
         f"| False alarms per 100 mm | {_f(F['per_100mm'])} ({F['count']} in {F['negative_mm']:.1f} mm of confirmed "
         f"negative runs) |",
         f"| Coverage: patches with a verdict | {C['patches'][0]}/{C['patches'][1]} |",
         f"| Coverage: events, negative mm | {C['events'][0]}/{C['events'][1]} events, "
         f"{C['negative_mm'][0]:.1f}/{C['negative_mm'][1]:.1f} mm |",
         f"| Recall on patches with a verdict | {_f(C['recall_where_verdict']['recall'])} "
         f"({C['recall_where_verdict']['hits']}/{C['recall_where_verdict']['events']}) |"]
    w = warnings(res)
    if w:
        L.append("")
        L += [f"WARNING: {x}" for x in w]
    if per_event:
        L += ["", "| # | Event | Patch | Centre (x, y, z) vx | Transitions | Verdict | Hit | Nearest alarm (mm) |",
              "|---|---|---|---|---|---|---|---|"]
        for i, e in enumerate([x for x in res["events"] if x["counted"]], 1):
            L.append(f"| {i} | {e['event_index']} | {e['patch']} | {', '.join(f'{v:.1f}' for v in e['xyz'])} | "
                     f"{e['transitions']} | {'yes' if e['verdict'] else 'NO VERDICT'} | {'HIT' if e['hit'] else 'miss'} | "
                     f"{_f(e['nearest_alarm_mm'], 2)} |")
    return "\n".join(L)


def write_json(res: dict, path: Path | str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(res, f, indent=1)
        f.write("\n")

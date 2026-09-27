"""SwitchBench v1 blind review packet (protocol P1 (prereg/switchbench_v1.md) "Labels: strong or not": triggered when the 2.4 um
rule is not STRONG on the held-out ladder half).

30 seeded locations (seed 20260925): 15 confirmed events drawn from the capped confirmed set that counts
toward recall, 10 CT-contradicted candidates, 5 confirmed negative runs; order shuffled with the same
RNG. Every location is described in one identical format (centre point, grid direction, a fixed 12-cell
span of about 2.3 mm, shifted inward at grid edges), so the description does not reveal its kind.
Writes results/switchbench_natural_v1_blind_review.md (no labels) and data/switchbench_v1/blind_key.json
(answer key, gitignored); returns the key's SHA-256, which is committed before the packet is handed over.
Measured precision (later) = confirmed events marked "switch" / confirmed events marked either way
(Wilson 95% CI).
"""
from __future__ import annotations

import hashlib
import json
import time

import numpy as np

from . import evaluate_v1, geom

SEED = 20260925
V1 = geom.REPO / "data" / "switchbench_v1"
KEY = V1 / "blind_key.json"
PACKET = geom.REPO / "vault" / "results" / "switchbench_v1_blind_review.md"
SPAN = 5
VOL = ("https://vesuvius-challenge-open-data.s3.us-east-1.amazonaws.com/PHercParis4/volumes/"
       "20260411134726-2.400um-0.2m-78keV-masked.zarr")


def _span(P, axis, rc_lo, rc_hi):
    """Fixed-length window (2 x SPAN + 2 = 12 cells) along the run axis, centred on the midpoint of
    [rc_lo, rc_hi] and shifted inward at the grid edge, so every location's span looks the same."""
    H, W, _ = P.shape
    L = 2 * SPAN + 2
    if axis == "row":
        r, n = rc_lo[0], W
        mid = (rc_lo[1] + rc_hi[1]) // 2
    else:
        r, n = rc_lo[1], H
        mid = (rc_lo[0] + rc_hi[0]) // 2
    a = min(max(0, mid - L // 2), max(0, n - 1 - L))
    b = min(n - 1, a + L)
    ok = lambda i: np.isfinite(P[r, i]).all() if axis == "row" else np.isfinite(P[i, r]).all()
    while a < mid and not ok(a):
        a += 1
    while b > mid and not ok(b):
        b -= 1
    return ([r, a], [r, b]) if axis == "row" else ([a, r], [b, r])


def location_event(rec, e):
    P, _, _ = evaluate_v1.patch_geom(rec["patch"])
    X = np.array(e["xyz"])
    m = min(e["members"], key=lambda m: np.linalg.norm(np.array(m["xyz"]) - X))
    lo, hi = _span(P, m["axis"], m["rc_a"], m["rc_b"])
    return dict(patch=rec["patch"], xyz=e["xyz"], axis=m["axis"], cells=[lo, hi])


def location_negative(rec, n):
    P, _, _ = evaluate_v1.patch_geom(rec["patch"])
    mid = n["verts"][len(n["verts"]) // 2]
    lo, hi = _span(P, n["axis"], mid, mid)
    return dict(patch=rec["patch"], xyz=P[tuple(mid)].tolist(), axis=n["axis"], cells=[lo, hi])


def build():
    recs = evaluate_v1.load_pooled()
    sc = evaluate_v1.scored(recs)
    sel = evaluate_v1.cap_selection(sc)
    conf = sorted([(r["patch"], e["i"]) for r in sc for e in r["events"]
                   if e["status"] == "confirmed" and e["i"] in sel[r["patch"]]])
    contra = sorted([(r["patch"], e["i"]) for r in recs for e in r["events"] if e["status"] == "contradicted"])
    negs = sorted([(r["patch"], j) for r in recs for j, n in enumerate(r["negatives"]) if n["status"] == "confirmed"])
    by = {r["patch"]: r for r in recs}
    rng = np.random.default_rng(SEED)
    pc = [conf[i] for i in rng.choice(len(conf), 15, replace=False)]
    pd = [contra[i] for i in rng.choice(len(contra), 10, replace=False)]
    pn = [negs[i] for i in rng.choice(len(negs), 5, replace=False)]
    items = ([("confirmed_event", p, i) for p, i in pc] + [("ct_contradicted_candidate", p, i) for p, i in pd]
             + [("negative_run", p, j) for p, j in pn])
    order = rng.permutation(len(items))
    key, rows = {}, []
    for k, idx in enumerate(order):
        kind, p, i = items[idx]
        rec = by[p]
        if kind == "negative_run":
            loc = location_negative(rec, rec["negatives"][i])
            extra = dict(negative_index=i, len_mm=rec["negatives"][i]["len_mm"])
        else:
            e = next(x for x in rec["events"] if x["i"] == i)
            loc = location_event(rec, e)
            extra = dict(event_index=i, status_l0=e["status"], status_l2_v0rule=e["status_l2"], subset=rec["subset"])
        rid = f"R{k + 1:02d}"
        key[rid] = dict(kind=kind, **loc, **extra)
        rows.append((rid, loc))
    key_doc = dict(seed=SEED, created_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   pools=dict(confirmed_capped=len(conf), contradicted=len(contra), negatives=len(negs)), key=key)
    KEY.write_text(json.dumps(key_doc, indent=1, sort_keys=True) + "\n")
    sha = hashlib.sha256(KEY.read_bytes()).hexdigest()
    write_packet(rows, sha)
    return sha, key_doc


def write_packet(rows, sha):
    L = []
    L.append("# SwitchBench v1: blind review (for the authors)")
    L.append("")
    L.append("**Why.** The 2.4 um CT rule that labels our sheet switches is not strong enough on its own "
             "(protocol P1 (prereg/switchbench_v1.md)). So the frozen plan asks you to look at 30 locations yourself. Your answers measure "
             "how many of our \"confirmed\" switches are real. About 1 hour (2 minutes per location).")
    L.append("")
    L.append("**Keep it blind.** The table has no labels. Some locations are switches we believe in, some are not, "
             "in shuffled order. Until you have filled in every row, please don't open anything under "
             "`results/switchbench*` (other than this file) or `data/`. The answer key is sealed: its SHA-256 "
             f"is `{sha}`, committed before this file was handed over.")
    L.append("")
    L.append("## Setup (once)")
    L.append("")
    L.append(f"1. **Volume:** PHercParis4, scan 20260411134726 (78 keV, 2.4 um), OME-Zarr: `{VOL}`. "
             "Open resolution level 2 (9.6 um per voxel). That is the frame the traces live in. "
             "For a sharper look you can switch to level 1 (4.8 um) or level 0 (2.4 um).")
    L.append("2. **Traces:** each location names one auto-grown trace (\"patch\"). It is in the Hugging Face bucket "
             "`scrollprize/datasets`, folder `spiral/PHercParis4/unverified_patches/<patch>/` "
             "(files x.tif, y.tif, z.tif, meta.json and, if present, mask.tif). Load it in VC3D as a tifxyz surface.")
    L.append("3. **Coordinates** are (x, y, z) voxels at level 2 (9.6 um), in the same order as the trace's x.tif, y.tif and "
             "z.tif. If VC3D shows full-resolution (2.4 um) coordinates, use the second column (the same point, multiplied by 4). "
             "Some VC3D panels list coordinates as (z, y, x).")
    L.append("")
    L.append("## What to do at each location")
    L.append("")
    L.append("1. Go to the point and find the patch's traced surface there.")
    L.append("2. The trace is a grid of points (the rows and columns of its x.tif / y.tif / z.tif images). The "
             "\"direction\" column says whether to follow a grid **row** (column index changes) or a grid **column** "
             "(row index changes); \"cells\" gives the two grid cells (row, column) at the ends of a stretch of about "
             "2.3 mm (12 grid steps) that passes through the point. In VC3D's flattened view of the trace, rows and columns are the two "
             "grid axes, so the stretch is a straight line there.")
    L.append("3. Follow the traced surface along that stretch. Papyrus sheets show as bright layers with dark gaps "
             "between them.")
    L.append("   - **switch**: on one side of the point the trace sits on one sheet, and on the other side it sits on "
             "the neighbouring sheet (it crossed a dark gap to the next bright layer).")
    L.append("   - **no switch**: the trace stays on the same sheet all along the stretch.")
    L.append("   - **can't tell**: the CT is too unclear, the sheets touch, or the trace is off every sheet.")
    L.append("4. Put an x in one of the three answer columns. Notes are optional.")
    L.append("")
    L.append("| ID | Patch | Point (x, y, z), 9.6 um | Same point, 2.4 um | Direction | Cells (from -> to) | switch | no switch | can't tell | Notes |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for rid, loc in rows:
        x = [int(round(v)) for v in loc["xyz"]]
        x4 = [int(round(4 * v)) for v in loc["xyz"]]
        (a, b) = loc["cells"]
        L.append(f"| {rid} | `{loc['patch']}` | {x[0]}, {x[1]}, {x[2]} | {x4[0]}, {x4[1]}, {x4[2]} | "
                 f"{loc['axis']} | ({a[0]}, {a[1]}) -> ({b[0]}, {b[1]}) |  |  |  |  |")
    L.append("")
    L.append("When done, send the filled table back (or paste the ID and answer for each row). The builder then opens "
             "the key, checks its SHA-256 against the committed value, and computes the measured precision: "
             "confirmed events marked \"switch\" divided by confirmed events marked either way (Wilson 95% CI). "
             "That number feeds the frozen C1 rule.")
    L.append("")
    PACKET.write_text("\n".join(L))


if __name__ == "__main__":
    s, k = build()
    print("blind key sha256", s, k["pools"])

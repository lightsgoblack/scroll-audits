"""Held-out geometry for the 1667 ink segments (masks only, no preds).

For each segment: pixel size, validation-mask area / bbox, overlap with every supervision-mask
version, the eroded evaluation region per the the frozen-criteria history held-out rule, 5 mm and 2.5 mm tile
counts, and labeled ink px inside the eroded region.

Held-out rule (the frozen-criteria history, global): erode validation_mask_v2 by E px, E = max over compared models
of (patch side x input downsample factor), never below 640 px. Erosion here uses a square
(chessboard) structuring element, because a training patch is a square: a val pixel is exposed
if it lies within Chebyshev distance < patch side of non-val supervision. Chessboard removes a
superset of what a disk erosion removes (more conservative).

Tiles: square grid anchored at the eroded-region bbox top-left, tile kept if >= 50% of its
pixels are in the eroded mask.

    .venv/bin/python -m tools.lie_detector_v0.geometry            # prints JSON, writes data/geometry.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

from tools.harness.fetch import REPO, Seg, read_2d

SEGMENTS = [
    "w028_20251208130119156_2um",
    "w029_20251212185248662_2um",
    "w023_20240304161941_2um",
    "w031_2025122323_2um",
    "w018_20240304144031_2um",
    "w013_20240304141531_2um",
]
E_FLOOR = 640


def pixel_um(meta: dict) -> float:
    """Voxel size from the volume name (e.g. SCROLLS_HEL_2.399um_...). tifxyz scale ~0.05 means
    one grid step = 1/scale voxels and the flat image is rendered at 1 px per voxel."""
    m = re.search(r"_(\d+(?:\.\d+)?)um_", meta["volume"])
    if not m:
        raise ValueError(f"cannot parse voxel size from {meta['volume']}")
    return float(m.group(1))


def footprint(pred_name: str) -> tuple[int, int]:
    """(patch side px, input downsample factor) from a pred file name. Patch side = the largest
    spatial number in the ps*/_640 tokens; downsample = 2**N for a 'scaleN' token, else 1."""
    n = Path(pred_name).name
    sides = [int(v) for v in re.findall(r"ps(\d+)", n)]
    sides += [int(v) for v in re.findall(r"ps\d+_(\d+)_(\d+)", n) for v in v]
    sides += [int(v) for v in re.findall(r"betti_ema_(\d+)_forward", n)]
    sc = re.search(r"scale(\d+)", n)
    ds = 2 ** int(sc.group(1)) if sc else 1
    return (max(sides) if sides else 0), ds


def erode_chessboard(mask: np.ndarray, e: int) -> tuple[np.ndarray, tuple[int, int]]:
    """Erode a bool mask by e px (square SE). Works on the mask bbox, zero-padded. Returns
    (eroded array over bbox, (y0, x0) offset of that array in the full image).
    Chessboard distance > e == erosion by a (2e+1)^2 square with zero padding, done as two
    separable 1D min filters on uint8 (exact; ~1 byte/px instead of int32 cdt, so a 1 Gpx
    bbox such as w018 fits in RAM)."""
    ys, xs = np.nonzero(mask)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    del ys, xs
    sub = mask[y0:y1, x0:x1].astype(np.uint8)
    for ax in (0, 1):
        ndimage.minimum_filter1d(sub, 2 * e + 1, axis=ax, output=sub, mode="constant", cval=0)
    return sub.astype(bool), (int(y0), int(x0))


def tile_count(m: np.ndarray, side: int, frac: float = 0.5) -> int:
    """Tiles of side px on a grid anchored at the bbox top-left of m, >= frac inside m."""
    if not m.any():
        return 0
    ys, xs = np.nonzero(m)
    sub = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    H, W = sub.shape
    ph, pw = -H % side, -W % side
    sub = np.pad(sub, ((0, ph), (0, pw)))
    s = sub.reshape(sub.shape[0] // side, side, sub.shape[1] // side, side).sum(axis=(1, 3), dtype=np.int64)
    return int((s >= frac * side * side).sum())


def segment_geometry(name: str) -> dict:
    s = Seg(name)
    meta = json.loads((s.small / "meta.json").read_text())
    listing = json.loads(s.listing_json.read_text()) if s.listing_json.exists() else {}
    preds = {k: v for k, v in listing.items() if k.startswith("preds/")}
    um = pixel_um(meta)
    mm = 1000.0 / um
    out = {
        "segment": name, "volume": meta["volume"], "tifxyz_scale": meta["scale"],
        "scroll_source_field": meta.get("scroll_source"), "pixel_um": um, "px_per_mm": mm,
        "preds": {k[6:]: v for k, v in preds.items()},
    }
    fps = {k[6:]: footprint(k) for k in preds if "reverse" not in k}
    out["footprints"] = {k: {"side": a, "ds": b, "px": a * b} for k, (a, b) in fps.items()}
    E = max([E_FLOOR] + [a * b for a, b in fps.values()])
    out["E_px"] = E
    out["E_basis"] = max(fps, key=lambda k: fps[k][0] * fps[k][1]) if fps else "floor"

    vf = s.val_file()
    if vf is None:
        out["validation_file"] = None
        out["verdict"] = "NO VALIDATION MASK IN BUCKET"
        return out
    lab = sorted(s.small.glob(f"{s.seg_id}_inklabels*.tif"))[-1]
    sups = sorted(s.small.glob(f"{s.seg_id}_supervision_mask*.tif"))
    out["validation_file"] = vf.name
    out["labels_file"] = lab.name
    raw = read_2d(vf)
    shape = list(raw.shape)
    ys, xs = np.nonzero(raw)
    bb = [int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1]
    # Everything below works on the val bbox only (val is 0 outside it, so every count is
    # exact); full-segment masks are 4+ GB each on w018/w023.
    val = raw[bb[0]:bb[1], bb[2]:bb[3]] > 0
    del raw
    n_cc = ndimage.label(val)[1]
    out.update({
        "segment_shape": shape,
        "val_px": int(ys.size), "val_mm2": ys.size / mm ** 2,
        "val_bbox_y0y1x0x1": bb, "val_bbox_hw_px": [bb[1] - bb[0], bb[3] - bb[2]],
        "val_bbox_hw_mm": [(bb[1] - bb[0]) / mm, (bb[3] - bb[2]) / mm],
        "val_components": int(n_cc),
    })
    out["overlap"] = {}
    for f in sups:
        sm = read_2d(f)[bb[0]:bb[1], bb[2]:bb[3]] > 0
        ov = int(np.count_nonzero(sm & val))
        out["overlap"][f.name] = {"px": ov, "frac_of_val": ov / ys.size}
        del sm

    labels = read_2d(lab)[bb[0]:bb[1], bb[2]:bb[3]] > 0
    for tag, e in (("rule", E), ("floor640", E_FLOOR)):
        er, (oy, ox) = erode_chessboard(val, e)
        r = {"E_px": e, "eroded_px": int(er.sum()), "eroded_mm2": float(er.sum()) / mm ** 2}
        if er.any():
            ey, ex = np.nonzero(er)
            r["eroded_bbox_hw_px"] = [int(ey.max() - ey.min() + 1), int(ex.max() - ex.min() + 1)]
            r["eroded_bbox_hw_mm"] = [v / mm for v in r["eroded_bbox_hw_px"]]
            r["eroded_components"] = int(ndimage.label(er)[1])
        t5, t25, t10 = round(5 * mm), round(2.5 * mm), round(10 * mm)
        r["tile_px"] = {"5mm": t5, "2.5mm": t25, "10mm": t10}
        r["tiles_5mm"] = tile_count(er, t5)
        r["tiles_2.5mm"] = tile_count(er, t25)
        r["tiles_10mm"] = tile_count(er, t10)
        lab_sub = labels[oy:oy + er.shape[0], ox:ox + er.shape[1]]
        r["ink_px_in_eroded"] = int(np.count_nonzero(lab_sub & er))
        r["ink_frac_in_eroded"] = r["ink_px_in_eroded"] / max(1, r["eroded_px"])
        out["eroded_" + tag] = r
        if e == E and tag == "rule" and E == E_FLOOR:
            out["eroded_floor640"] = r
            break
    r = out["eroded_rule"]
    out["qualifies_5mm"] = r["tiles_5mm"] >= 20
    out["candidate_2.5mm"] = r["tiles_2.5mm"] >= 20
    return out


def main() -> None:
    res = [segment_geometry(n) for n in SEGMENTS]
    p = REPO / "data" / "geometry.json"
    p.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    sys.exit(main())

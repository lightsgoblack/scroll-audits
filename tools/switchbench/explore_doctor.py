"""EXPLORATORY helper (SwitchBench-natural v0 robustness; not pre-registered, changes no verdict).

tifxyz-doctor (aviad12g/tifxyz-doctor @5ca0444) through its public Python API, run with the doctor's
own interpreter, never ours:

  $SWITCHBENCH_EXT (default ./ext)/tifxyz-doctor/.venv/bin/python tools/switchbench/explore_doctor.py capture <dirs.json> <out_dir>
  $SWITCHBENCH_EXT (default ./ext)/tifxyz-doctor/.venv/bin/python tools/switchbench/explore_doctor.py sweep   <dirs.json> <out_dir>
  $SWITCHBENCH_EXT (default ./ext)/tifxyz-doctor/.venv/bin/python tools/switchbench/explore_doctor.py planted <split.json> <verified_root> <out_json>
  $SWITCHBENCH_EXT (default ./ext)/tifxyz-doctor/.venv/bin/python tools/switchbench/explore_doctor.py planted20 <verified_root> <out_json>

capture: audit_mesh(load_tifxyz(dir), AuditConfig()) once; records the per-edge coherent-normal-step
  scores (|edge . local normal| / median grid spacing) that the tool computes internally and hands to its
  example selector, the two reference spacings, and _arrays (coherent_normal_step_cells, review_score,
  review_cue_mask, valid_cells). No computation is changed: two module functions are wrapped only to
  record their arguments.
sweep: audit_mesh with AuditConfig(normal_step_ratio=r, normal_step_min_component_cells=m) for the grid
  below; per m stores the largest r at which each cell is in _arrays["coherent_normal_step_cells"], and
  checks monotonicity (lower r or lower m must give a superset).
planted: the doctor's own sealed holdout (benchmarks/reviewed-same-wrap-split-v1.json) and its own
  injector; detection by its own rule plus the per-edge scores on the edges the offset changes.
planted20 (addition X2): the same ladder on 128 seeded verified auto_grown patches with a 20 vx grid
  (meta scale 0.05, the natural corpus's resolution); detection vs normal_step_ratio (m = 8) rebuilt from
  the captured scores with the doctor's own helpers, checked against the API mask at the default.
Numeric arrays only; no image is produced.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
from tifxyz_doctor import AuditConfig, audit_mesh, load_tifxyz
from tifxyz_doctor import audit as A
from tifxyz_doctor.io import TifxyzData
from tifxyz_doctor.reviewed_benchmark import _transition_coefficients, inject_normal_offset_switch
from tifxyz_doctor.topology import label_components_8

R_GRID = [0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.13, 0.14, 0.15, 0.16, 0.17,
          0.18, 0.19, 0.20, 0.22, 0.25, 0.30, 0.35, 0.40, 0.50]
M_GRID = [1, 2, 4, 8, 16, 32]

REC = {}
_orig_top = A._top_locations
_orig_cns = A._coherent_normal_step_metrics


def _top(values, mask, *, limit=50, largest=True):
    if sys._getframe(1).f_code.co_name == "_coherent_normal_step_metrics":
        REC.setdefault("scores", []).append(np.array(values, dtype=np.float64, copy=True))
    return _orig_top(values, mask, limit=limit, largest=largest)


def _cns(*args, **kw):
    # audit_mesh calls it positionally: (..., horizontal_reference, vertical_reference, config)
    REC["refs"] = (args[7], args[8])
    return _orig_cns(*args, **kw)


A._top_locations = _top
A._coherent_normal_step_metrics = _cns


def run(data, cfg=None):
    REC.clear()
    rep = audit_mesh(data, cfg or AuditConfig())
    h, v = REC["scores"][0], REC["scores"][1]
    return rep, h, v, REC["refs"]


def capture(dirs, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for d in dirs:
        d = Path(d)
        f = out / f"{d.name}.npz"
        if f.exists():
            continue
        t0 = time.time()
        data = load_tifxyz(d)
        rep, h, v, refs = run(data)
        a = rep["_arrays"]
        g = rep["geometry"]["coherent_normal_steps"]
        np.savez_compressed(
            f, hscore=h, vscore=v, href=np.float64(refs[0] if refs[0] is not None else np.nan),
            vref=np.float64(refs[1] if refs[1] is not None else np.nan),
            cns=np.asarray(a["coherent_normal_step_cells"], bool), review_score=np.asarray(a["review_score"], np.float32),
            review_cue_mask=np.asarray(a["review_cue_mask"], bool), valid_cells=np.asarray(a["valid_cells"], bool),
            valid=np.asarray(data.valid, bool), coherent_components=np.int64(g["coherent_components"]),
            coherent_cells=np.int64(g["coherent_cells"]), elapsed=np.float64(time.time() - t0))
        print("capture", d.name, round(time.time() - t0, 2), flush=True)


def sweep(dirs, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for d in dirs:
        d = Path(d)
        f = out / f"{d.name}.npz"
        if f.exists():
            continue
        t0 = time.time()
        data = load_tifxyz(d)
        level = None
        viol_r = viol_m = 0
        prev = {}
        default_mask = None
        for r in sorted(R_GRID, reverse=True):
            row = []
            for m in M_GRID:
                rep = audit_mesh(data, AuditConfig(normal_step_ratio=r, normal_step_min_component_cells=m))
                mk = np.asarray(rep["_arrays"]["coherent_normal_step_cells"], bool)
                if level is None:
                    level = np.zeros((len(M_GRID),) + mk.shape, np.float64)
                j = M_GRID.index(m)
                if m in prev and (prev[m] & ~mk).any():
                    viol_r += 1            # a cell retained at a higher r is lost at this lower r
                if row and (mk & ~row[-1]).any():
                    viol_m += 1            # a larger m retains a cell a smaller m drops
                level[j][mk & (level[j] == 0)] = r
                prev[m] = mk
                row.append(mk)
                if r == 0.25 and m == 8:
                    default_mask = mk
        np.savez_compressed(f, level=level, r_grid=np.array(R_GRID), m_grid=np.array(M_GRID),
                            viol_r=np.int64(viol_r), viol_m=np.int64(viol_m), default_mask=default_mask,
                            elapsed=np.float64(time.time() - t0))
        print("sweep", d.name, round(time.time() - t0, 1), "viol", viol_r, viol_m, flush=True)


def _transition_edges(case, shape, width):
    """Boolean masks (horizontal edges H x W-1, vertical edges H-1 x W) where the planted offset changes."""
    H, W = shape
    L = W if case.orientation == "vertical" else H
    coef = _transition_coefficients(L, case.seam_index, width)
    ch = np.abs(np.diff(coef)) > 1e-12
    he = np.zeros((H, W - 1), bool)
    ve = np.zeros((H - 1, W), bool)
    if case.orientation == "vertical":
        he[:, ch] = True
    else:
        ve[ch, :] = True
    return he, ve, float(np.max(np.abs(np.diff(coef)))), int(ch.sum())


def _row_max(score, emask, orientation):
    """Per crossing line (row for a vertical seam, column for a horizontal seam) max score on its transition edges."""
    s = np.where(emask, score, np.nan)
    with np.errstate(all="ignore"):
        if orientation == "vertical":
            s = s[np.any(emask, 1)]
            vals = np.nanmax(np.where(np.isfinite(s), s, -np.inf), 1)
        else:
            s = s[:, np.any(emask, 0)]
            vals = np.nanmax(np.where(np.isfinite(s), s, -np.inf), 0)
    return vals[np.isfinite(vals)]


def planted(split, root, out_json):
    ids = json.load(open(split))["split"]["selected_holdout_ids"]
    cfg = AuditConfig()
    rows = []
    for k, pid in enumerate(ids):
        d = Path(root) / pid
        data = load_tifxyz(d)
        base, bh, bv, brefs = run(data, cfg)
        base_cns = np.asarray(base["_arrays"]["coherent_normal_step_cells"], bool)
        for off in (4.0, 8.0, 16.0):
            for width in (1, 4, 12):
                case = inject_normal_offset_switch(data, offset_voxels=off, transition_width_cells=width)
                rep, h, v, refs = run(case.data, cfg)
                cns = np.asarray(rep["_arrays"]["coherent_normal_step_cells"], bool)
                det = bool((cns & ~base_cns & case.evaluation_cells).any())
                he, ve, max_dcoef, n_steps = _transition_edges(case, data.valid.shape, width)
                score, bscore, em = (h, bh, he) if case.orientation == "vertical" else (v, bv, ve)
                rm = _row_max(score, em, case.orientation)
                brm = _row_max(bscore, em, case.orientation)
                rows.append(dict(patch=pid, offset_vx=off, width_cells=width, orientation=case.orientation,
                                 detected=det, max_step_vx=off * max_dcoef, n_transition_steps=n_steps,
                                 n_lines=int(len(rm)), max_score=float(rm.max()) if len(rm) else None,
                                 median_line_max_score=float(np.median(rm)) if len(rm) else None,
                                 frac_lines_ge_025=float((rm >= 0.25).mean()) if len(rm) else None,
                                 base_median_line_max_score=float(np.median(brm)) if len(brm) else None,
                                 ref_spacing=float(refs[0] if case.orientation == "vertical" else refs[1])))
        if (k + 1) % 16 == 0:
            print("planted", k + 1, "/", len(ids), flush=True)
    # flat-grid reference (same injector and audit): the planted step with no surface roughness
    H = W = 40
    yy, xx = np.mgrid[0:H, 0:W].astype(float)
    coords = np.stack([xx * 20 + 1000, yy * 20 + 1000, np.full_like(xx, 5000.0)], -1).astype(np.float32)
    flat = TifxyzData(path=Path("flat"), coordinates=coords, valid=np.ones((H, W), bool), metadata={},
                      explicit_mask=None)
    flat_rows = []
    for off in (4.0, 8.0, 16.0):
        for width in (1, 4, 12):
            case = inject_normal_offset_switch(flat, offset_voxels=off, transition_width_cells=width)
            rep, h, v, refs = run(case.data, cfg)
            flat_rows.append(dict(offset_vx=off, width_cells=width, max_score=float(np.nanmax(h)),
                                  coherent_cells=int(np.asarray(rep["_arrays"]["coherent_normal_step_cells"]).sum())))
    json.dump(dict(rows=rows, flat=flat_rows), open(out_json, "w"))


def rebuild(h, v, cell_valid, r, m):
    """coherent_normal_step_cells from per-edge scores, with the doctor's own helpers and rule."""
    hf = np.isfinite(h) & (h >= r)
    vf = np.isfinite(v) & (v >= r)
    cand = np.zeros(cell_valid.shape, bool)
    A._project_edge_flags_to_cells(cand, hf, vf)
    cand &= cell_valid
    labels, sizes = label_components_8(cand)
    keep = [i for i, sz in enumerate(sizes, start=1) if sz >= m]
    return np.isin(labels, keep) if keep else np.zeros(cand.shape, bool)


R_PL = [r for r in R_GRID if r >= 0.10]


def planted20(root, out_json, n_target=128, seed=20260925):
    root = Path(root)
    cands = []
    for d in sorted(root.iterdir()):
        if not d.name.startswith("auto_grown") or not (d / "meta.json").exists():
            continue
        sc = json.load(open(d / "meta.json")).get("scale")
        if sc and abs(sc[0] - 0.05) < 1e-6 and abs(sc[1] - 0.05) < 1e-6:
            cands.append(d.name)
    order = np.random.default_rng(seed).permutation(len(cands))
    cfg = AuditConfig()
    rows, skipped, accepted, mism = [], [], [], 0
    for i in order:
        if len(accepted) >= n_target:
            break
        nm = cands[int(i)]
        try:
            data = load_tifxyz(root / nm)
            inject_normal_offset_switch(data, offset_voxels=8.0, transition_width_cells=1)
        except Exception as e:  # the injector refuses surfaces without a supported interior seam
            skipped.append([nm, repr(e)[:120]])
            continue
        base, bh, bv, brefs = run(data, cfg)
        cv = np.asarray(base["_arrays"]["valid_cells"], bool)
        base_cns = np.asarray(base["_arrays"]["coherent_normal_step_cells"], bool)
        mism += int(not np.array_equal(rebuild(bh, bv, cv, 0.25, 8), base_cns))
        base_r = {r: rebuild(bh, bv, cv, r, 8) for r in R_PL}
        for off in (4.0, 8.0, 16.0):
            for width in (1, 4, 12):
                case = inject_normal_offset_switch(data, offset_voxels=off, transition_width_cells=width)
                rep, h, v, refs = run(case.data, cfg)
                cns = np.asarray(rep["_arrays"]["coherent_normal_step_cells"], bool)
                cv2 = np.asarray(rep["_arrays"]["valid_cells"], bool)
                mism += int(not np.array_equal(rebuild(h, v, cv2, 0.25, 8), cns))
                det = bool((cns & ~base_cns & case.evaluation_cells).any())
                det_r = {f"{r:.2f}": bool((rebuild(h, v, cv2, r, 8) & ~base_r[r] & case.evaluation_cells).any())
                         for r in R_PL}
                he, ve, max_dcoef, n_steps = _transition_edges(case, data.valid.shape, width)
                score, em = (h, he) if case.orientation == "vertical" else (v, ve)
                rm = _row_max(score, em, case.orientation)
                rows.append(dict(patch=nm, offset_vx=off, width_cells=width, detected=det, detected_by_ratio_m8=det_r,
                                 max_step_vx=off * max_dcoef, n_transition_steps=n_steps, n_lines=int(len(rm)),
                                 max_score=float(rm.max()) if len(rm) else None,
                                 median_line_max_score=float(np.median(rm)) if len(rm) else None,
                                 frac_lines_ge_025=float((rm >= 0.25).mean()) if len(rm) else None,
                                 ref_spacing=float(refs[0] if case.orientation == "vertical" else refs[1])))
        accepted.append(nm)
        if len(accepted) % 16 == 0:
            print("planted20", len(accepted), "/", n_target, "skipped", len(skipped), flush=True)
    json.dump(dict(rows=rows, accepted=accepted, skipped=skipped, n_candidates=len(cands),
                   rebuild_default_mismatches=mism, r_grid=R_PL), open(out_json, "w"))


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "capture":
        capture(json.load(open(sys.argv[2])), sys.argv[3])
    elif mode == "sweep":
        sweep(json.load(open(sys.argv[2])), sys.argv[3])
    elif mode == "planted":
        planted(sys.argv[2], sys.argv[3], sys.argv[4])
    elif mode == "planted20":
        planted20(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit("mode must be capture, sweep or planted")

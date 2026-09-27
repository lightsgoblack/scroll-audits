"""Read a detector's alarms in one of three formats and turn them into corpus-frame points.

(a) xyz   JSON {"patch_id": [[x, y, z], ...], ...}   level-2 voxels (x, y, z), the corpus frame
(b) grid  JSON {"patch_id": [[row, col], ...], ...}  integer vertex indices into the patch's tifxyz
          grid (row = first array axis of x.tif); the alarm sits on that vertex
(c) masks a directory of <patch_id>.npz files, each holding one boolean array of the tifxyz grid
          shape (key "mask", or the only array); every True valid vertex is an alarm

A JSON file may also wrap the mapping: {"format": "xyz" | "grid", "detector": "name", "alarms": {...}}.
A patch present with an empty list has a verdict and raised no alarm. A patch that is absent (or
null in JSON, or without an .npz file) has NO VERDICT: the kit reports it under coverage and never
reads it as "no alarm". Grid alarms on invalid vertices (-1 or masked by mask.tif) are dropped and
counted. Patch ids that are not scored patches of the corpus are ignored and listed (unscored corpus
patches separately from ids the corpus does not know, which are usually typos).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .corpus import Benchmark, sha256_file

FORMATS = ("xyz", "grid", "masks")


class AlarmsError(ValueError):
    """The alarms input cannot be read as given."""


@dataclass
class AlarmSet:
    by_patch: dict                      # scored patch id -> (n, 3) float64 voxels, or None (no verdict)
    format: str
    detector: str = None
    source: str = None
    sha256: str = None
    n_in_input: int = 0                 # patch entries in the input (any id, verdict or not)
    unscored: list = field(default_factory=list)      # corpus patches that carry nothing scored (ignored)
    unknown: list = field(default_factory=list)       # ids that are not in the corpus at all (typos?)
    dropped_invalid: int = 0            # grid / mask alarms on invalid vertices


def from_xyz(bench: Benchmark, mapping: dict, detector: str = None) -> AlarmSet:
    """Build an AlarmSet from {patch: (n, 3) array-like or None} (Python API, format a)."""
    s = AlarmSet(by_patch={}, format="xyz", detector=detector or "alarms", source="python mapping",
                 n_in_input=len(mapping))
    for p, v in mapping.items():
        if _skip(s, bench, p):
            continue
        s.by_patch[p] = None if v is None else _as_xyz(v, p)
    return s


def load_alarms(path: Path | str, bench: Benchmark, fmt: str = "auto", detector: str = None) -> AlarmSet:
    path = Path(path)
    if not path.exists():
        raise AlarmsError(f"alarms input {path} does not exist")
    if path.is_dir():
        if fmt not in ("auto", "masks"):
            raise AlarmsError(f"{path} is a directory: only the masks format (c) reads directories")
        s = _load_masks(path, bench)
    else:
        if fmt == "masks":
            raise AlarmsError(f"the masks format (c) needs a directory of <patch_id>.npz files, got file {path}")
        s = _load_json(path, bench, fmt)
        s.sha256 = sha256_file(path)
    s.source = str(path)
    s.detector = detector or s.detector or path.stem
    return s


def _skip(s: AlarmSet, bench: Benchmark, p: str) -> bool:
    """True (and recorded) if patch id p is not a scored patch of the corpus."""
    if p in bench.geometry:
        return False
    (s.unscored if p in bench.all_patch_ids else s.unknown).append(p)
    return True


# ----------------------------------------------------------------------------- JSON (a) and (b)
def _load_json(path: Path, bench: Benchmark, fmt: str) -> AlarmSet:
    try:
        raw = json.load(open(path))
    except json.JSONDecodeError as e:
        raise AlarmsError(f"{path} is not valid JSON: {e}")
    detector = None
    if isinstance(raw, dict) and isinstance(raw.get("alarms"), dict):
        detector = raw.get("detector")
        declared = raw.get("format")
        if declared is not None:
            if declared not in ("xyz", "grid"):
                raise AlarmsError(f"{path}: 'format' must be 'xyz' or 'grid', got {declared!r}")
            if fmt not in ("auto", declared):
                raise AlarmsError(f"{path} declares format {declared!r} but --format {fmt} was given")
            fmt = declared
        raw = raw["alarms"]
    if not isinstance(raw, dict):
        raise AlarmsError(f"{path}: expected a JSON object {{patch_id: [[...], ...]}}")
    for p, v in raw.items():
        if v is not None and not isinstance(v, list):
            raise AlarmsError(f"{path}: alarms of {p!r} must be a list of points or null")
    lens = {len(a) if isinstance(a, list) else -1 for v in raw.values() if v for a in v}
    if fmt == "auto":
        if lens - {2, 3}:
            raise AlarmsError(f"{path}: every alarm must be [x, y, z] (format a) or [row, col] (format b)")
        if lens == {2, 3}:
            raise AlarmsError(f"{path} mixes [x, y, z] and [row, col] alarms; use one format per file")
        fmt = "grid" if lens == {2} else "xyz"
    want = 3 if fmt == "xyz" else 2
    if lens - {want}:
        raise AlarmsError(f"{path}: format {fmt} needs {want} numbers per alarm")
    s = AlarmSet(by_patch={}, format=fmt, detector=detector, n_in_input=len(raw))
    for p, v in raw.items():
        if _skip(s, bench, p):
            continue
        if v is None:
            s.by_patch[p] = None
        elif fmt == "xyz":
            s.by_patch[p] = _as_xyz(v, p)
        else:
            s.by_patch[p], nbad = _grid_to_xyz(bench.geometry[p], v, p)
            s.dropped_invalid += nbad
    return s


def _as_xyz(v, p) -> np.ndarray:
    try:
        A = np.asarray(v, dtype=np.float64).reshape(-1, 3)
    except (ValueError, TypeError):
        raise AlarmsError(f"alarms of {p!r}: expected [[x, y, z], ...] numbers")
    if not np.isfinite(A).all():
        raise AlarmsError(f"alarms of {p!r}: non-finite coordinates")
    return A


def _grid_to_xyz(P: np.ndarray, v, p) -> tuple[np.ndarray, int]:
    try:
        G = np.asarray(v, dtype=np.float64).reshape(-1, 2)
    except (ValueError, TypeError):
        raise AlarmsError(f"alarms of {p!r}: expected [[row, col], ...] integers")
    if not np.isfinite(G).all() or (G != np.round(G)).any():
        raise AlarmsError(f"alarms of {p!r}: grid alarms must be integer [row, col] vertex indices")
    G = G.astype(np.int64)
    H, W = P.shape[:2]
    out = (G[:, 0] < 0) | (G[:, 0] >= H) | (G[:, 1] < 0) | (G[:, 1] >= W)
    if out.any():
        raise AlarmsError(f"alarms of {p!r}: [row, col] {G[out][0].tolist()} is outside the {H} x {W} grid")
    A = P[G[:, 0], G[:, 1]]
    ok = np.isfinite(A).all(-1)
    return A[ok], int((~ok).sum())


# ----------------------------------------------------------------------------- masks (c)
def _load_masks(d: Path, bench: Benchmark) -> AlarmSet:
    files = sorted(d.glob("*.npz"))
    s = AlarmSet(by_patch={}, format="masks", n_in_input=len(files))
    for f in files:
        p = f.stem
        if _skip(s, bench, p):
            continue
        try:
            with np.load(f) as z:
                keys = list(z.keys())
                if "mask" in keys:
                    m = z["mask"]
                elif len(keys) == 1:
                    m = z[keys[0]]
                else:
                    raise AlarmsError(f"{f}: holds {keys}; name the boolean array 'mask'")
        except AlarmsError:
            raise
        except Exception as e:
            raise AlarmsError(f"{f} is not a readable .npz file: {e}")
        P = bench.geometry[p]
        if m.shape != P.shape[:2]:
            raise AlarmsError(f"{f}: mask shape {m.shape} differs from the tifxyz grid shape {P.shape[:2]}")
        if m.dtype != bool:
            if not np.isin(m, (0, 1)).all():
                raise AlarmsError(f"{f}: mask must be boolean (or 0/1)")
            m = m.astype(bool)
        rc = np.argwhere(m)
        A = P[rc[:, 0], rc[:, 1]].reshape(-1, 3)
        ok = np.isfinite(A).all(-1)
        s.by_patch[p] = A[ok]
        s.dropped_invalid += int((~ok).sum())
    return s

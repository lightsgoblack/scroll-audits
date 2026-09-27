"""Load a SwitchBench corpus file and the patch geometry it refers to.

Corpus file (e.g. results/switchbench_natural_v0_events.json), fields the kit reads:
  events[]:    patch, status, transitions[] {rc_a, rc_b}; xyz is used only as a consistency check
  negatives[]: patch, status, axis ('row' | 'col'), rc0, rc1; len_mm, xyz0, xyz1 only as checks
  optional:    scroll, frame (shown), voxel_mm (default 0.0096), patch_source {bucket, prefix}
               (used by fetch), scoring {match_mm, per_patch_cap, bootstrap, seed, fa_dedup_mm}
               (defaults for score), geometry_sha256 (expected geometry fingerprint)
Scored patches: patches with >= 1 confirmed event or >= 1 confirmed negative run (v0 rule).
Only 'confirmed' events count toward recall and only 'confirmed' runs toward false alarms; every
candidate event of a scored patch, confirmed or not, is excluded from false-alarm counting.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import geometry

CONFIRMED = "confirmed"
REPO = Path(__file__).resolve().parents[2]
LOCAL_MIRROR = REPO / "data" / "paris4" / "unverified_patches"

# Geometry fingerprints of the patch files each released corpus was built on (corpus sha256 ->
# fingerprint). A corpus file may also carry its own "geometry_sha256" field, which wins.
KNOWN_GEOMETRY = {
    # results/switchbench_natural_v0_events.json (SwitchBench-natural v0): 67 scored patches
    "30d0cf0768d83aba5144deef40e7860cfdcd9c3f47193e4efac49190aeebf9e7":
        "5efaf7ac4b2ba34a6a018fba88e37e83d438ccc4fbee39a00a47577d714852c9",
}

XYZ_TOL = 0.05 + 1e-6      # the corpus file rounds coordinates to 0.1 voxel
MM_TOL = 0.005 + 1e-6      # and lengths to 0.01 mm


class CorpusError(ValueError):
    """The corpus file or the patch geometry cannot be scored as given."""


@dataclass
class Event:
    index: int                 # position in the corpus file's events list
    patch: str
    status: str
    n_transitions: int
    xyz_file: list
    points: np.ndarray = None  # transition points + centre, (n + 1, 3) voxels
    centre: np.ndarray = None


@dataclass
class Negative:
    index: int                 # position in the corpus file's negatives list
    patch: str
    status: str
    axis: str
    rc0: list
    rc1: list
    len_mm_file: float
    verts: np.ndarray = None   # run vertices, (n, 3) voxels
    length_mm: float = None


@dataclass
class Benchmark:
    path: Path
    sha256: str
    raw: dict
    patches_dir: Path
    voxel_mm: float
    mm: float                                   # voxels per mm
    patches: list                               # scored patch ids, sorted
    geometry: dict = field(default_factory=dict)            # patch -> (H, W, 3) grid
    events: dict = field(default_factory=dict)              # patch -> [Event] (all statuses, file order)
    negatives: dict = field(default_factory=dict)           # patch -> [Negative] (all statuses, file order)
    geometry_sha256: str = None
    geometry_expected: str = None

    @property
    def scroll(self):
        return self.raw.get("scroll")

    @property
    def frame(self):
        return self.raw.get("frame")

    @property
    def all_patch_ids(self) -> set:
        r = self.raw
        return {x["patch"] for k in ("events", "negatives", "multi_wrap") for x in r.get(k) or [] if "patch" in x}

    @property
    def scoring_defaults(self) -> dict:
        return dict(self.raw.get("scoring") or {})

    @property
    def geometry_check(self) -> str:
        if self.geometry_expected is None:
            return "no reference"
        return "match" if self.geometry_expected == self.geometry_sha256 else "MISMATCH"

    def confirmed_events(self):
        return [e for p in self.patches for e in self.events[p] if e.status == CONFIRMED]

    def confirmed_negatives(self):
        return [n for p in self.patches for n in self.negatives[p] if n.status == CONFIRMED]


def sha256_file(p: Path | str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_corpus(path: Path | str) -> dict:
    """Parse and validate the corpus JSON (no geometry)."""
    path = Path(path)
    try:
        raw = json.load(open(path))
    except (OSError, json.JSONDecodeError) as e:
        raise CorpusError(f"cannot read corpus file {path}: {e}")
    if not isinstance(raw, dict) or not isinstance(raw.get("events"), list) or not isinstance(raw.get("negatives"), list):
        raise CorpusError(f"{path}: a corpus file is a JSON object with 'events' and 'negatives' lists")
    for i, e in enumerate(raw["events"]):
        for k in ("patch", "status", "transitions"):
            if k not in e:
                raise CorpusError(f"{path}: events[{i}] has no '{k}'")
        if not e["transitions"]:
            raise CorpusError(f"{path}: events[{i}] has no transitions")
        for j, t in enumerate(e["transitions"]):
            if "rc_a" not in t or "rc_b" not in t:
                raise CorpusError(f"{path}: events[{i}].transitions[{j}] needs rc_a and rc_b")
    for i, n in enumerate(raw["negatives"]):
        for k in ("patch", "status", "axis", "rc0", "rc1"):
            if k not in n:
                raise CorpusError(f"{path}: negatives[{i}] has no '{k}'")
    return raw


def scored_patch_ids(raw: dict) -> list:
    """Patches with >= 1 confirmed event or >= 1 confirmed negative run, sorted by name."""
    s = {e["patch"] for e in raw["events"] if e["status"] == CONFIRMED}
    s |= {n["patch"] for n in raw["negatives"] if n["status"] == CONFIRMED}
    return sorted(s)


def default_patches_dir() -> Path | None:
    return LOCAL_MIRROR if LOCAL_MIRROR.is_dir() else None


def load_benchmark(corpus_path: Path | str, patches_dir: Path | str | None = None) -> Benchmark:
    """Read the corpus, load every scored patch, rebuild event points and runs, check them.

    Raises CorpusError if a patch is missing or its geometry disagrees with the corpus file
    (wrong or re-exported patch files): scores on other geometry would not be comparable.
    """
    corpus_path = Path(corpus_path)
    raw = read_corpus(corpus_path)
    if patches_dir is None:
        patches_dir = default_patches_dir()
        if patches_dir is None:
            raise CorpusError("no --patches-dir given and no local mirror found; run "
                              "`python -m tools.switchbench_kit fetch --corpus ... --out DIR` first")
    patches_dir = Path(patches_dir)
    voxel_mm = float(raw.get("voxel_mm", geometry.VOXEL_MM))
    b = Benchmark(path=corpus_path, sha256=sha256_file(corpus_path), raw=raw, patches_dir=patches_dir,
                  voxel_mm=voxel_mm, mm=geometry.vx_per_mm(voxel_mm), patches=scored_patch_ids(raw))
    missing = [p for p in b.patches if not all((patches_dir / p / f).exists() for f in geometry.GRID_FILES)]
    if missing:
        raise CorpusError(f"{len(missing)} of {len(b.patches)} scored patches are missing from {patches_dir} "
                          f"(first: {missing[0]}); run `python -m tools.switchbench_kit fetch --corpus "
                          f"{corpus_path} --out {patches_dir}`")
    scored = set(b.patches)
    for p in b.patches:
        b.geometry[p] = geometry.load_tifxyz(patches_dir / p)
        b.events[p], b.negatives[p] = [], []
    problems = []
    for i, e in enumerate(raw["events"]):
        if e["patch"] not in scored:
            continue
        P = b.geometry[e["patch"]]
        ev = Event(index=i, patch=e["patch"], status=e["status"], n_transitions=len(e["transitions"]),
                   xyz_file=e.get("xyz"))
        bad = _check_vertices(P, [t[k] for t in e["transitions"] for k in ("rc_a", "rc_b")])
        if bad:
            problems.append(f"events[{i}] ({e['patch']}): {bad}")
            continue
        ev.points, ev.centre = geometry.event_points(P, e["transitions"])
        if ev.xyz_file is not None and np.max(np.abs(ev.centre - np.asarray(ev.xyz_file, float))) > XYZ_TOL:
            problems.append(f"events[{i}] ({e['patch']}): centre {np.round(ev.centre, 2).tolist()} from the patch "
                            f"grid, {ev.xyz_file} in the corpus file")
        b.events[e["patch"]].append(ev)
    for i, n in enumerate(raw["negatives"]):
        if n["patch"] not in scored:
            continue
        P = b.geometry[n["patch"]]
        ng = Negative(index=i, patch=n["patch"], status=n["status"], axis=n["axis"], rc0=n["rc0"], rc1=n["rc1"],
                      len_mm_file=n.get("len_mm"))
        try:
            vv = geometry.run_vertices(n["axis"], n["rc0"], n["rc1"])
        except ValueError as ex:
            problems.append(f"negatives[{i}] ({n['patch']}): {ex}")
            continue
        bad = _check_vertices(P, vv)
        if bad:
            problems.append(f"negatives[{i}] ({n['patch']}): {bad}")
            continue
        ng.verts = np.array([P[v] for v in vv])
        ng.length_mm = geometry.arc_mm(P, vv, b.mm)
        if ng.len_mm_file is not None and abs(ng.length_mm - float(ng.len_mm_file)) > MM_TOL:
            problems.append(f"negatives[{i}] ({n['patch']}): run length {ng.length_mm:.4f} mm from the patch grid, "
                            f"{ng.len_mm_file} mm in the corpus file")
        for key, v in (("xyz0", vv[0]), ("xyz1", vv[-1])):
            if n.get(key) is not None and np.max(np.abs(P[v] - np.asarray(n[key], float))) > XYZ_TOL:
                problems.append(f"negatives[{i}] ({n['patch']}): {key} {np.round(P[v], 2).tolist()} from the patch "
                                f"grid, {n[key]} in the corpus file")
        b.negatives[n["patch"]].append(ng)
    if problems:
        raise CorpusError(f"patch geometry in {patches_dir} does not match the corpus file ({len(problems)} "
                          "problems; wrong or re-exported patch files?):\n  " + "\n  ".join(problems[:20]))
    b.geometry_sha256 = geometry.fingerprint(b.geometry)
    b.geometry_expected = raw.get("geometry_sha256") or KNOWN_GEOMETRY.get(b.sha256)
    return b


def _check_vertices(P, rcs):
    H, W = P.shape[:2]
    for rc in rcs:
        r, c = (int(v) for v in rc)
        if not (0 <= r < H and 0 <= c < W):
            return f"grid vertex {list(rc)} outside the {H} x {W} grid"
        if not np.isfinite(P[r, c]).all():
            return f"grid vertex {list(rc)} is not a valid vertex"
    return None

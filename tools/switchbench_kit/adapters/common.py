"""Shared helpers for the detector adapters."""
from __future__ import annotations

import json
from pathlib import Path


class AdapterError(Exception):
    pass


def iter_patch_inputs(path: Path, want: str = "file"):
    """Yield (patch_id, input_path) pairs from `path`.

    If `path` is itself a single file/dir, yields one pair (patch id = its stem/name).
    If `path` is a directory of per-patch files or per-patch subdirectories, yields one pair per
    entry (patch id = the entry's stem/name). `want` = "file" (JSON files) or "dir" (subdirectories,
    for tools whose native output is a directory per patch, e.g. windcheck, windaudit).
    """
    path = Path(path)
    if not path.exists():
        raise AdapterError(f"{path} does not exist")
    if want == "file" and path.is_file():
        yield path.stem, path
        return
    if want == "dir" and path.is_dir() and any(p.suffix == ".json" for p in path.glob("*.json")):
        # path itself looks like one patch's native output directory
        yield path.name, path
        return
    if not path.is_dir():
        raise AdapterError(f"{path}: expected a directory of per-patch native outputs")
    entries = sorted(path.iterdir())
    found = False
    for e in entries:
        if want == "file" and e.is_file() and e.suffix == ".json":
            yield e.stem, e
            found = True
        elif want == "dir" and e.is_dir():
            yield e.name, e
            found = True
    if not found:
        raise AdapterError(f"{path}: no per-patch native {'files' if want == 'file' else 'directories'} found")


def load_json(p: Path) -> dict:
    try:
        return json.loads(Path(p).read_text())
    except json.JSONDecodeError as e:
        raise AdapterError(f"{p} is not valid JSON: {e}")


def write_alarms(alarms: dict, out: Path, detector: str, fmt: str) -> None:
    Path(out).write_text(json.dumps({"detector": detector, "format": fmt, "alarms": alarms}, indent=1))

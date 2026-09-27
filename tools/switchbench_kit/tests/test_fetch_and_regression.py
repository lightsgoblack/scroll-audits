"""fetch logic with a fake bucket (no network), and the v0 regression when the v0 data is present."""
from __future__ import annotations

import json
import shutil
import types
from pathlib import Path

import pytest

from _synth import make_patches, write_corpus
from tools.switchbench_kit import fetch as kfetch
from tools.switchbench_kit import load_benchmark

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def fake_bucket(tmp_path, monkeypatch):
    """A 'remote' folder served through stand-ins for the two huggingface_hub calls fetch makes."""
    remote = make_patches(tmp_path / "remote" / "pfx")
    calls = {"downloaded": []}

    def paths_info(bucket, paths, token=None):
        for p in paths:
            f = tmp_path / "remote" / p
            if f.exists():
                yield types.SimpleNamespace(path=p, size=f.stat().st_size)

    def download(bucket, pairs, raise_on_missing_files=False, token=None):
        for rp, lp in pairs:
            shutil.copy(tmp_path / "remote" / rp, lp)
            calls["downloaded"].append(rp)

    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "get_bucket_paths_info", paths_info)
    monkeypatch.setattr(huggingface_hub, "download_bucket_files", download)
    return remote, calls


def _corpus(tmp_path):
    p = write_corpus(tmp_path / "corpus.json")
    d = json.loads(p.read_text())
    d["patch_source"] = {"bucket": "fake/bucket", "prefix": "pfx"}
    p.write_text(json.dumps(d))
    return p


def test_fetch_downloads_only_scored_patches_and_existing_files(tmp_path, fake_bucket):
    remote, calls = fake_bucket
    corpus = _corpus(tmp_path)
    s = kfetch.fetch(corpus, tmp_path / "out", mirror="none", log=lambda m: None)
    assert s["patches"] == 2 and s["downloaded"] == 7              # pA: x y z mask; pB: x y z (no mask, no meta)
    assert not (tmp_path / "out" / "pC").exists()                  # unscored patch is not fetched
    man = json.loads((tmp_path / "out" / kfetch.MANIFEST).read_text())
    assert man["patches"]["pA"] == ["mask.tif", "x.tif", "y.tif", "z.tif"] and man["verified_against_bucket"]
    assert "pB/mask.tif" in man["absent_in_bucket"]
    load_benchmark(corpus, tmp_path / "out")                        # the fetched folder scores
    s = kfetch.fetch(corpus, tmp_path / "out", mirror="none", log=lambda m: None)
    assert s["downloaded"] == 0 and s["files_present"] == 7        # second run: nothing to do


def test_fetch_prefers_a_local_mirror(tmp_path, fake_bucket):
    remote, calls = fake_bucket
    s = kfetch.fetch(_corpus(tmp_path), tmp_path / "out", mirror=remote, log=lambda m: None)
    assert s["copied_from_mirror"] == 7 and s["downloaded"] == 0 and not calls["downloaded"]


def test_fetch_without_network_falls_back_to_the_mirror(tmp_path, monkeypatch):
    remote = make_patches(tmp_path / "mirror")
    monkeypatch.setattr(kfetch, "WAITS", ())

    def offline(*a, **k):
        raise OSError("no network")
    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "get_bucket_paths_info", offline)
    s = kfetch.fetch(_corpus(tmp_path), tmp_path / "out", mirror=remote, log=lambda m: None)
    assert not s["verified_against_bucket"] and s["copied_from_mirror"] == 7


V0_DATA = REPO / "data" / "paris4" / "detect" / "tifxyz_doctor"


@pytest.mark.skipif(not V0_DATA.is_dir(), reason="v0 detector outputs (data/paris4) not present")
def test_v0_regression_is_exact(tmp_path):
    from tools.switchbench_kit import regression
    r = regression.run(out=None, work=tmp_path, cli=False, log=lambda m: None)
    assert r["exact_match_v0_semantics"], r["verdict"]
    assert r["kit_default_differences_all_explained"], r["kit_default_unexplained"]
    d = r["detectors"]["tifxyz-doctor (coherent-normal-step)"]["kit_default"]
    assert (d["hits"], d["events"], d["false_alarms"]) == (6, 54, 5)

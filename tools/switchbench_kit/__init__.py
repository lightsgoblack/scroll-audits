"""SwitchBench scorer kit: score any sheet-switch detector on the SwitchBench natural-switch corpus.

CLI:  python -m tools.switchbench_kit {list,fetch,score} ...   (see README.md)
API:  bench = load_benchmark(corpus_json, patches_dir)
      alarms = load_alarms(path, bench)            # or from_xyz(bench, {patch: [[x, y, z], ...]})
      result = score(bench, alarms)                # JSON-ready dict; format_report(result) for text
"""
__version__ = "1.0.0"

from .alarms import AlarmSet, AlarmsError, from_xyz, load_alarms  # noqa: E402
from .corpus import Benchmark, CorpusError, load_benchmark  # noqa: E402
from .report import format_report, write_json  # noqa: E402
from .scoring import score  # noqa: E402

__all__ = ["AlarmSet", "AlarmsError", "Benchmark", "CorpusError", "format_report", "from_xyz", "load_alarms",
           "load_benchmark", "score", "write_json", "__version__"]

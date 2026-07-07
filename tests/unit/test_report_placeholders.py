"""Report placeholder tests for Phase 1.

No real reports are produced by these tests.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_report_directories_contain_only_placeholders_initially():
    report_dirs = [
        ROOT / "reports" / "summary",
        ROOT / "reports" / "backtests",
        ROOT / "reports" / "paper",
    ]

    for report_dir in report_dirs:
        assert report_dir.exists()
        files = [path.name for path in report_dir.iterdir() if path.is_file()]
        assert files == [".gitkeep"]

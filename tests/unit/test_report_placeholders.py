"""Report directory safety tests."""

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
        if report_dir.name == "backtests":
            assert ".gitkeep" in files
            assert all(name == ".gitkeep" or name.endswith((".json", ".txt")) for name in files)
        else:
            assert files == [".gitkeep"]

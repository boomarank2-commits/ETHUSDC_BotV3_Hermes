"""Regression tests for Windows/POSIX path containment semantics."""

from pathlib import Path

from ethusdc_bot.path_safety import is_path_within


def test_windows_data_root_is_not_reinterpreted_inside_posix_checkout(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"

    assert is_path_within("C:/TradingBot/data/ETHUSDC_BotV3_Hermes", repository_root) is False


def test_windows_path_containment_uses_windows_semantics() -> None:
    repository_root = "C:/TradingBot/hermes-agent/ETHUSDC_BotV3_Hermes"

    assert is_path_within(repository_root, repository_root) is True
    assert is_path_within(repository_root + "/reports", repository_root) is True
    assert is_path_within("C:/TradingBot/data/ETHUSDC_BotV3_Hermes", repository_root) is False
    assert is_path_within("D:/TradingBot/data/ETHUSDC_BotV3_Hermes", repository_root) is False


def test_posix_path_containment_uses_native_semantics(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"
    inside = repository_root / "reports"
    outside = tmp_path / "data"

    assert is_path_within(repository_root, repository_root) is True
    assert is_path_within(inside, repository_root) is True
    assert is_path_within(outside, repository_root) is False


def test_mixed_absolute_path_flavours_are_disjoint(tmp_path: Path) -> None:
    repository_root = tmp_path / "repo"

    assert is_path_within("C:/repo/file.txt", repository_root) is False
    assert is_path_within(repository_root, "C:/repo") is False

"""Minimal import tests for the Phase 1 package skeleton."""


def test_package_imports():
    import ethusdc_bot

    assert ethusdc_bot.__version__ == "0.1.0"


def test_phase1_placeholder_packages_import():
    import ethusdc_bot.config
    import ethusdc_bot.data_pipeline
    import ethusdc_bot.reports
    import ethusdc_bot.runtime
    import ethusdc_bot.safety

    assert ethusdc_bot.config is not None
    assert ethusdc_bot.data_pipeline is not None
    assert ethusdc_bot.reports is not None
    assert ethusdc_bot.runtime is not None
    assert ethusdc_bot.safety is not None

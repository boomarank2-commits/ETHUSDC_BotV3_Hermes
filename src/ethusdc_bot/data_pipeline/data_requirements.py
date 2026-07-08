"""Backtest data requirement catalog for ETHUSDC_BotV3_Hermes.

This module defines the data matrix only. It does not download data, read market
contents, run backtests, produce reports, create trades, or unlock live modes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy


_REQUIREMENTS: list[dict[str, object]] = [
    {
        "requirement_id": "ethusdc_klines_1m",
        "symbol": "ETHUSDC",
        "data_type": "klines_1m",
        "interval": "1m",
        "role": "trade_market",
        "required": True,
        "context_only": False,
        "trade_market": True,
        "may_trigger_orders": True,
        "publicly_downloadable": True,
        "live_collected": False,
        "required_days": 1095,
        "minimum_days": 1095,
        "blocks_backtest": True,
        "included_by_default": True,
        "diagnostic_until_minimum_history": False,
        "source_kind": "public_binance_data",
        "implemented_downloader": True,
        "description": "Primary ETHUSDC Binance Spot 1m klines used as the only trade market.",
    },
    {
        "requirement_id": "btcusdc_klines_1m",
        "symbol": "BTCUSDC",
        "data_type": "klines_1m",
        "interval": "1m",
        "role": "market_context",
        "required": False,
        "context_only": True,
        "trade_market": False,
        "may_trigger_orders": False,
        "publicly_downloadable": True,
        "live_collected": False,
        "required_days": 1095,
        "minimum_days": 1095,
        "blocks_backtest": False,
        "included_by_default": True,
        "diagnostic_until_minimum_history": False,
        "source_kind": "public_binance_data",
        "implemented_downloader": False,
        "description": "BTCUSDC 1m context only; never an order trigger.",
    },
    {
        "requirement_id": "ethbtc_klines_1m",
        "symbol": "ETHBTC",
        "data_type": "klines_1m",
        "interval": "1m",
        "role": "market_context",
        "required": False,
        "context_only": True,
        "trade_market": False,
        "may_trigger_orders": False,
        "publicly_downloadable": True,
        "live_collected": False,
        "required_days": 1095,
        "minimum_days": 1095,
        "blocks_backtest": False,
        "included_by_default": True,
        "diagnostic_until_minimum_history": False,
        "source_kind": "public_binance_data",
        "implemented_downloader": False,
        "description": "ETHBTC 1m context only; never an order trigger.",
    },
    {
        "requirement_id": "ethusdc_aggtrades",
        "symbol": "ETHUSDC",
        "data_type": "aggTrades",
        "interval": "daily",
        "role": "microstructure_tradeflow",
        "required": False,
        "context_only": False,
        "trade_market": False,
        "may_trigger_orders": False,
        "publicly_downloadable": True,
        "live_collected": False,
        "required_days": None,
        "minimum_days": 7,
        "blocks_backtest": False,
        "included_by_default": False,
        "diagnostic_until_minimum_history": True,
        "source_kind": "public_binance_data",
        "implemented_downloader": False,
        "description": "ETHUSDC aggregate trades for microstructure/tradeflow diagnostics and later validated features.",
    },
    {
        "requirement_id": "ethusdc_trades",
        "symbol": "ETHUSDC",
        "data_type": "trades",
        "interval": "daily",
        "role": "microstructure_tradeflow",
        "required": False,
        "context_only": False,
        "trade_market": False,
        "may_trigger_orders": False,
        "publicly_downloadable": True,
        "live_collected": False,
        "required_days": None,
        "minimum_days": 1,
        "blocks_backtest": False,
        "included_by_default": False,
        "diagnostic_until_minimum_history": True,
        "source_kind": "public_binance_data",
        "implemented_downloader": False,
        "description": "ETHUSDC raw trades for microstructure/tradeflow diagnostics and later validated features.",
    },
    {
        "requirement_id": "exchange_info",
        "symbol": "ETHUSDC",
        "data_type": "exchange_info",
        "interval": None,
        "role": "rules_cost_basis",
        "required": True,
        "context_only": False,
        "trade_market": False,
        "may_trigger_orders": False,
        "publicly_downloadable": True,
        "live_collected": False,
        "required_days": None,
        "minimum_days": 0,
        "blocks_backtest": False,
        "included_by_default": True,
        "diagnostic_until_minimum_history": False,
        "source_kind": "public_binance_data",
        "implemented_downloader": False,
        "description": "Binance symbol filters such as tickSize, stepSize, minNotional and minQty.",
    },
    {
        "requirement_id": "fee_reference",
        "symbol": "ETHUSDC",
        "data_type": "fee_reference",
        "interval": None,
        "role": "rules_cost_basis",
        "required": True,
        "context_only": False,
        "trade_market": False,
        "may_trigger_orders": False,
        "publicly_downloadable": False,
        "live_collected": False,
        "required_days": None,
        "minimum_days": 0,
        "blocks_backtest": False,
        "included_by_default": True,
        "diagnostic_until_minimum_history": False,
        "source_kind": "config_model",
        "implemented_downloader": False,
        "description": "Conservative or manually configured fee model; no fake account-specific fee.",
    },
    {
        "requirement_id": "slippage_model",
        "symbol": "ETHUSDC",
        "data_type": "slippage_model",
        "interval": None,
        "role": "rules_cost_basis",
        "required": True,
        "context_only": False,
        "trade_market": False,
        "may_trigger_orders": False,
        "publicly_downloadable": False,
        "live_collected": False,
        "required_days": None,
        "minimum_days": 0,
        "blocks_backtest": False,
        "included_by_default": True,
        "diagnostic_until_minimum_history": False,
        "source_kind": "config_model",
        "implemented_downloader": False,
        "description": "Conservative slippage model, later improvable with validated spread/book/orderbook history.",
    },
    {
        "requirement_id": "ethusdc_bookticker_live",
        "symbol": "ETHUSDC",
        "data_type": "bookTicker",
        "interval": "live",
        "role": "live_microstructure",
        "required": False,
        "context_only": False,
        "trade_market": False,
        "may_trigger_orders": False,
        "publicly_downloadable": False,
        "live_collected": True,
        "required_days": None,
        "minimum_days": 30,
        "blocks_backtest": False,
        "included_by_default": False,
        "diagnostic_until_minimum_history": True,
        "source_kind": "live_collection",
        "implemented_downloader": False,
        "description": "ETHUSDC live bookTicker, diagnostic until at least 30 validated days exist.",
    },
    {
        "requirement_id": "ethusdc_orderbook_snapshots_live",
        "symbol": "ETHUSDC",
        "data_type": "orderbook_snapshots",
        "interval": "live",
        "role": "live_microstructure",
        "required": False,
        "context_only": False,
        "trade_market": False,
        "may_trigger_orders": False,
        "publicly_downloadable": False,
        "live_collected": True,
        "required_days": None,
        "minimum_days": 30,
        "blocks_backtest": False,
        "included_by_default": False,
        "diagnostic_until_minimum_history": True,
        "source_kind": "live_collection",
        "implemented_downloader": False,
        "description": "ETHUSDC orderbook snapshots, diagnostic until at least 30 validated days exist.",
    },
]


def build_backtest_data_requirements() -> list[dict[str, object]]:
    """Return the static data matrix for the later realistic backtest."""

    return deepcopy(_REQUIREMENTS)


def get_requirement_by_id(requirements: Sequence[Mapping[str, object]], requirement_id: str) -> dict[str, object]:
    """Return a requirement by id or raise KeyError."""

    for requirement in requirements:
        if requirement["requirement_id"] == requirement_id:
            return dict(requirement)
    raise KeyError(requirement_id)


def classify_requirement_role(requirement: Mapping[str, object]) -> str:
    """Return the canonical role for a requirement."""

    return str(requirement["role"])


def requirement_blocks_backtest(requirement: Mapping[str, object]) -> bool:
    """Return whether missing/invalid data blocks the first normal backtest gate."""

    return bool(requirement.get("blocks_backtest"))


def requirement_can_be_downloaded_publicly(requirement: Mapping[str, object]) -> bool:
    """Return whether Binance public-data download can provide this source historically."""

    return bool(requirement.get("publicly_downloadable"))


def requirement_is_live_collected(requirement: Mapping[str, object]) -> bool:
    """Return whether this source must be collected live over time."""

    return bool(requirement.get("live_collected"))

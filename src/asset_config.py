from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class AssetConfig:
    key: str
    display_name: str
    data_symbol: str  # yfinance symbol used to pull OHLCV candles
    yahoo_news_symbol: str  # yfinance ticker to pull attached headlines from
    broker_symbol: str  # default broker (e.g. XM) symbol shown in the guardrails panel
    unit_label: str  # "oz", "MMBtu", "units", ...
    contract_size_per_lot: float
    min_lot: float
    lot_step: float
    max_lot: float
    spread_estimate: float
    default_account_balance: float
    macro_drivers: tuple[dict, ...]  # each: symbol/name/weight/direction (relative to this asset)
    news_feed_focus_terms: tuple[str, ...]
    bullish_keywords: tuple[str, ...]
    bearish_keywords: tuple[str, ...]
    event_checklist_extra: tuple[str, ...]
    prop_firm_phase_key: str | None = None  # key into src.prop_firm_rules, or None to disable
    challenge_starting_balance: float | None = None  # funded account's initial size, for max-loss %


GOLD = AssetConfig(
    key="gold",
    display_name="Gold",
    data_symbol="PAXG-USD",  # PAX Gold: token backed 1:1 by physical gold, trades 24/7,
    # tracks spot/CFD gold (e.g. XM's XAUUSD) far more closely than GC=F futures,
    # which can drift ~$50-60 away from spot due to contract roll and session gaps.
    yahoo_news_symbol="GC=F",
    broker_symbol="XAUUSD",
    unit_label="oz",
    contract_size_per_lot=100.0,
    min_lot=0.01,
    lot_step=0.01,
    max_lot=50.0,
    spread_estimate=0.5,
    default_account_balance=64.18,
    macro_drivers=(
        {"symbol": "DX-Y.NYB", "name": "US Dollar Index (DXY)", "weight": 30, "direction": -1},
        {"symbol": "^TNX", "name": "US 10Y Yield", "weight": 25, "direction": -1},
        {"symbol": "^VIX", "name": "VIX", "weight": 15, "direction": 1},
        {"symbol": "CL=F", "name": "WTI Crude", "weight": 10, "direction": 1},
        {"symbol": "SI=F", "name": "Silver", "weight": 10, "direction": 1},
        {"symbol": "^GSPC", "name": "S&P 500", "weight": 10, "direction": -1},
        {"symbol": "TLT", "name": "US 20Y Bond ETF (TLT)", "weight": 5, "direction": 1},
        {"symbol": "BTC-USD", "name": "Bitcoin", "weight": 5, "direction": -1},
        {"symbol": "GDX", "name": "Gold Miners ETF (GDX)", "weight": 5, "direction": 1},
    ),
    news_feed_focus_terms=("gold", "xau", "fed", "inflation", "yield", "dollar", "treasury", "geopolitical"),
    bullish_keywords=(
        "safe haven", "geopolitical", "war", "tension", "inflation", "recession",
        "rate cut", "dovish", "debt", "uncertainty",
    ),
    bearish_keywords=(
        "rate hike", "hawkish", "strong dollar", "yield rise", "risk-on",
        "cooling inflation", "ceasefire", "equity rally",
    ),
    event_checklist_extra=("Geopolitical escalations and central bank gold reserve headlines",),
    prop_firm_phase_key="two_step",
)

NATURAL_GAS = AssetConfig(
    key="natural_gas",
    display_name="Natural Gas",
    data_symbol="NG=F",  # Henry Hub natural gas futures, front month (Yahoo Finance)
    yahoo_news_symbol="NG=F",
    broker_symbol="NGASCash",
    unit_label="MMBtu",
    contract_size_per_lot=10000.0,
    min_lot=0.01,
    lot_step=0.01,
    max_lot=50.0,
    spread_estimate=0.02,
    default_account_balance=64.18,
    macro_drivers=(
        {"symbol": "CL=F", "name": "WTI Crude Oil", "weight": 35, "direction": 1},
        {"symbol": "DX-Y.NYB", "name": "US Dollar Index (DXY)", "weight": 25, "direction": -1},
        {"symbol": "XLE", "name": "Energy Sector ETF (XLE)", "weight": 20, "direction": 1},
        {"symbol": "^VIX", "name": "VIX", "weight": 10, "direction": 1},
        {"symbol": "^TNX", "name": "US 10Y Yield", "weight": 10, "direction": -1},
    ),
    news_feed_focus_terms=("natural gas", "henry hub", "natgas", "lng", "gas prices", "pipeline"),
    bullish_keywords=(
        "cold snap", "polar vortex", "freeze", "heating demand", "storage draw",
        "supply disruption", "pipeline outage", "hurricane", "production cut", "heatwave",
    ),
    bearish_keywords=(
        "mild weather", "warm winter", "storage build", "oversupply",
        "production surge", "record output", "storage surplus", "weak demand",
    ),
    event_checklist_extra=(
        "Weekly EIA Natural Gas Storage Report (Thursdays)",
        "NOAA extended weather outlook (heating/cooling demand)",
    ),
)


BRENT_CRUDE = AssetConfig(
    key="brent_crude",
    display_name="Brent Crude Oil",
    data_symbol="BZ=F",  # ICE Brent Crude futures, front month (Yahoo Finance)
    yahoo_news_symbol="BZ=F",
    broker_symbol="BRENTCash",
    unit_label="barrels",
    contract_size_per_lot=1000.0,
    min_lot=0.01,
    lot_step=0.01,
    max_lot=50.0,
    spread_estimate=0.05,
    default_account_balance=64.18,
    macro_drivers=(
        {"symbol": "CL=F", "name": "WTI Crude Oil", "weight": 30, "direction": 1},
        {"symbol": "DX-Y.NYB", "name": "US Dollar Index (DXY)", "weight": 25, "direction": -1},
        {"symbol": "XLE", "name": "Energy Sector ETF (XLE)", "weight": 20, "direction": 1},
        {"symbol": "^VIX", "name": "VIX", "weight": 15, "direction": 1},
        {"symbol": "^TNX", "name": "US 10Y Yield", "weight": 10, "direction": -1},
    ),
    news_feed_focus_terms=("brent", "oil", "opec", "crude", "barrel", "energy", "supply"),
    bullish_keywords=(
        "opec cut", "production cut", "supply disruption", "sanctions", "pipeline outage",
        "geopolitical", "war", "tension", "inventory draw", "demand surge",
    ),
    bearish_keywords=(
        "opec increase", "output hike", "oversupply", "demand slowdown", "recession",
        "inventory build", "ceasefire", "strong dollar", "record output",
    ),
    event_checklist_extra=(
        "Weekly EIA Crude Oil Inventory Report (Wednesdays)",
        "OPEC+ meeting announcements and production quota changes",
    ),
)


_REGISTRY: dict[str, AssetConfig] = {
    GOLD.key: GOLD,
    NATURAL_GAS.key: NATURAL_GAS,
    BRENT_CRUDE.key: BRENT_CRUDE,
}

DEFAULT_ASSET_KEY = "natural_gas"


def list_assets() -> list[AssetConfig]:
    return list(_REGISTRY.values())


def get_asset(key: str) -> AssetConfig:
    try:
        return _REGISTRY[key]
    except KeyError as exc:
        available = ", ".join(sorted(_REGISTRY))
        raise KeyError(f"Unknown asset '{key}'. Available: {available}") from exc


def get_active_asset() -> AssetConfig:
    """Resolve the asset to trade from the ASSET_KEY env var, for scripts/automation."""
    key = os.environ.get("ASSET_KEY", DEFAULT_ASSET_KEY)
    return get_asset(key)

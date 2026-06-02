"""Data ingestion: Polymarket Gamma API client and TradFi probability models."""

from poly_alpha.data.polymarket import PolymarketClient, fetch_active_markets

__all__ = ["fetch_active_markets", "PolymarketClient"]

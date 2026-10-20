"""Compatibility facade for runtime routing services."""

from .runtime.routing import FAST_ROUTE_CANDIDATES, cohere_rank, decide

__all__ = ["FAST_ROUTE_CANDIDATES", "cohere_rank", "decide"]

"""Read product development, specification, and technology-transfer records."""

from __future__ import annotations

from typing import Any

from .context_records import lookup_context_records


def lookup_rnd_evidence(context_id: Any) -> dict[str, Any]:
    """Read product development, specification, and transfer evidence."""
    return lookup_context_records(context_id, lookup="rnd_evidence", snapshots=("rnd",))

"""
Allow-List Checker

Loads the organization's approved instance type allow-list from YAML
and provides lookup methods for validation.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Category mapping based on instance family prefix
FAMILY_CATEGORY = {
    "m": "General Purpose",
    "c": "Compute Optimized",
    "r": "Memory Optimized",
    "i": "Storage Optimized",
    "t": "Burstable",
}


class AllowListChecker:
    """Loads and queries the approved instance type allow-list."""

    def __init__(self, allowlist_path: str | Path | None = None):
        """
        Args:
            allowlist_path: Path to the allowlist YAML file.
                            Defaults to part2/allowlist.yaml.
        """
        if allowlist_path is None:
            allowlist_path = Path(__file__).resolve().parent.parent / "allowlist.yaml"
        self._path = Path(allowlist_path)
        self._type_to_tier: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def load(self) -> "AllowListChecker":
        """Load the allow-list YAML and build the internal lookup."""
        with open(self._path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self._type_to_tier = {}
        for tier in data.get("tiers", []):
            tier_name = tier["name"]
            discount_pct = tier["discount_percent"]

            for family_entry in tier.get("families", []):
                family = family_entry["family"]
                category = self._get_category(family)

                for size in family_entry.get("sizes", []):
                    instance_type = f"{family}.{size}"
                    self._type_to_tier[instance_type] = {
                        "tier_name": tier_name,
                        "discount_percent": discount_pct,
                        "family": family,
                        "category": category,
                    }

        self._loaded = True
        logger.info(
            "Loaded allow-list with %d instance types from %s",
            len(self._type_to_tier),
            self._path,
        )
        return self

    def is_allowed(self, instance_type: str) -> bool:
        """Check if an instance type is in the allow-list."""
        self._ensure_loaded()
        return instance_type in self._type_to_tier

    def get_tier(self, instance_type: str) -> dict[str, Any] | None:
        """
        Get tier info for an instance type.

        Returns:
            Dict with tier_name, discount_percent, family, category.
            None if not in allow-list.
        """
        self._ensure_loaded()
        return self._type_to_tier.get(instance_type)

    def get_all_allowed_types(self) -> list[dict[str, Any]]:
        """
        Get all allowed instance types with their tier info.

        Returns:
            List of dicts with instance_type, tier_name, discount_percent,
            family, category.
        """
        self._ensure_loaded()
        result = []
        for itype, info in sorted(self._type_to_tier.items()):
            result.append({"instance_type": itype, **info})
        return result

    def _ensure_loaded(self) -> None:
        """Auto-load if not yet loaded."""
        if not self._loaded:
            self.load()

    @staticmethod
    def _get_category(family: str) -> str:
        """Map instance family to a workload category."""
        # Extract the letter prefix (e.g., "m" from "m5", "c" from "c6g")
        prefix = family[0] if family else ""
        return FAMILY_CATEGORY.get(prefix, "Other")

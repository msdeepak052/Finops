"""
EKS / Kubernetes Instance Filter

Identifies and excludes EC2 instances that belong to EKS clusters or
Kubernetes workloads based on their tags.

Exclusion tags:
  - kubernetes.io/cluster/<anything>
  - eks:cluster-name
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Tag keys (or prefixes) that indicate an EKS/Kubernetes workload
EKS_TAG_EXACT_KEYS = {
    "eks:cluster-name",
    "eks:nodegroup-name",
    "aws:eks:cluster-name",
}

EKS_TAG_PREFIXES = (
    "kubernetes.io/cluster/",
    "k8s.io/cluster/",
)


class EKSFilter:
    """Filters EC2 recommendations to exclude EKS/Kubernetes instances."""

    @staticmethod
    def is_eks_instance(tags: dict[str, str]) -> bool:
        """
        Determine if an instance belongs to an EKS/Kubernetes cluster.

        Args:
            tags: Dict of tag key-value pairs for the instance.

        Returns:
            True if the instance is part of EKS/Kubernetes.
        """
        for key in tags:
            # Check exact match keys
            if key.lower() in {k.lower() for k in EKS_TAG_EXACT_KEYS}:
                return True
            # Check prefix match keys (kubernetes.io/cluster/<cluster-name>)
            for prefix in EKS_TAG_PREFIXES:
                if key.lower().startswith(prefix.lower()):
                    return True
        return False

    @classmethod
    def filter_recommendations(
        cls, recommendations: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Split recommendations into non-EKS (included) and EKS (excluded).

        Args:
            recommendations: List of enriched recommendation dicts with tags.

        Returns:
            Tuple of (non_eks_recommendations, eks_recommendations).
        """
        non_eks = []
        eks = []

        for rec in recommendations:
            tags = rec.get("tags", {})
            if cls.is_eks_instance(tags):
                eks.append(rec)
                logger.debug(
                    "EXCLUDED (EKS): %s (%s)", rec["instance_id"], rec["instance_name"]
                )
            else:
                non_eks.append(rec)

        logger.info(
            "Filter results: %d non-EKS (included), %d EKS (excluded)",
            len(non_eks),
            len(eks),
        )
        return non_eks, eks

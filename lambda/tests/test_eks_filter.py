"""Tests for EKS/Kubernetes instance filtering."""

import pytest
from compute_optimizer.eks_filter import EKSFilter


class TestIsEksInstance:
    def test_eks_cluster_name_tag(self):
        tags = {"eks:cluster-name": "my-cluster", "Name": "worker-1"}
        assert EKSFilter.is_eks_instance(tags) is True

    def test_kubernetes_io_cluster_tag(self):
        tags = {"kubernetes.io/cluster/my-cluster": "owned", "Name": "k8s-node"}
        assert EKSFilter.is_eks_instance(tags) is True

    def test_k8s_io_cluster_tag(self):
        tags = {"k8s.io/cluster/prod-cluster": "owned"}
        assert EKSFilter.is_eks_instance(tags) is True

    def test_eks_nodegroup_tag(self):
        tags = {"eks:nodegroup-name": "ng-1"}
        assert EKSFilter.is_eks_instance(tags) is True

    def test_non_eks_instance(self):
        tags = {"Name": "web-server", "Environment": "production"}
        assert EKSFilter.is_eks_instance(tags) is False

    def test_empty_tags(self):
        assert EKSFilter.is_eks_instance({}) is False

    def test_case_insensitive_eks_tag(self):
        tags = {"EKS:Cluster-Name": "test"}
        assert EKSFilter.is_eks_instance(tags) is True


class TestFilterRecommendations:
    def _make_rec(self, instance_id: str, tags: dict) -> dict:
        return {
            "instance_id": instance_id,
            "instance_name": tags.get("Name", ""),
            "tags": tags,
        }

    def test_mixed_instances(self):
        recs = [
            self._make_rec("i-001", {"Name": "web-1"}),
            self._make_rec("i-002", {"eks:cluster-name": "prod", "Name": "k8s-node"}),
            self._make_rec("i-003", {"Name": "api-server"}),
            self._make_rec("i-004", {"kubernetes.io/cluster/dev": "owned"}),
        ]

        non_eks, eks = EKSFilter.filter_recommendations(recs)

        assert len(non_eks) == 2
        assert len(eks) == 2
        assert {r["instance_id"] for r in non_eks} == {"i-001", "i-003"}
        assert {r["instance_id"] for r in eks} == {"i-002", "i-004"}

    def test_all_non_eks(self):
        recs = [
            self._make_rec("i-001", {"Name": "web-1"}),
            self._make_rec("i-002", {"Name": "db-1"}),
        ]
        non_eks, eks = EKSFilter.filter_recommendations(recs)
        assert len(non_eks) == 2
        assert len(eks) == 0

    def test_all_eks(self):
        recs = [
            self._make_rec("i-001", {"eks:cluster-name": "prod"}),
            self._make_rec("i-002", {"kubernetes.io/cluster/staging": "shared"}),
        ]
        non_eks, eks = EKSFilter.filter_recommendations(recs)
        assert len(non_eks) == 0
        assert len(eks) == 2

    def test_empty_list(self):
        non_eks, eks = EKSFilter.filter_recommendations([])
        assert non_eks == []
        assert eks == []

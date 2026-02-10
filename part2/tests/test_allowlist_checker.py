"""Tests for AllowListChecker."""

import pytest

from bedrock_validator.allowlist_checker import AllowListChecker


@pytest.fixture
def checker():
    """Load the allow-list checker with the default allowlist.yaml."""
    return AllowListChecker().load()


class TestIsAllowed:
    def test_tier1_instance_allowed(self, checker):
        assert checker.is_allowed("m5.xlarge") is True

    def test_tier2_instance_allowed(self, checker):
        assert checker.is_allowed("t3.medium") is True

    def test_unlisted_instance_not_allowed(self, checker):
        assert checker.is_allowed("p3.2xlarge") is False

    def test_unlisted_size_not_allowed(self, checker):
        # m5.metal is not in the allowlist
        assert checker.is_allowed("m5.metal") is False

    def test_empty_string_not_allowed(self, checker):
        assert checker.is_allowed("") is False


class TestGetTier:
    def test_tier1_info(self, checker):
        tier = checker.get_tier("m5.xlarge")
        assert tier is not None
        assert tier["discount_percent"] == 50
        assert "Tier 1" in tier["tier_name"]
        assert tier["family"] == "m5"
        assert tier["category"] == "General Purpose"

    def test_tier2_info(self, checker):
        tier = checker.get_tier("t3.medium")
        assert tier is not None
        assert tier["discount_percent"] == 35
        assert "Tier 2" in tier["tier_name"]
        assert tier["family"] == "t3"
        assert tier["category"] == "Burstable"

    def test_compute_optimized_category(self, checker):
        tier = checker.get_tier("c5.xlarge")
        assert tier is not None
        assert tier["category"] == "Compute Optimized"

    def test_memory_optimized_category(self, checker):
        tier = checker.get_tier("r5.large")
        assert tier is not None
        assert tier["category"] == "Memory Optimized"

    def test_storage_optimized_category(self, checker):
        tier = checker.get_tier("i3.large")
        assert tier is not None
        assert tier["category"] == "Storage Optimized"

    def test_unlisted_returns_none(self, checker):
        assert checker.get_tier("p3.2xlarge") is None


class TestGetAllAllowedTypes:
    def test_returns_list(self, checker):
        types = checker.get_all_allowed_types()
        assert isinstance(types, list)
        assert len(types) > 0

    def test_entries_have_required_keys(self, checker):
        types = checker.get_all_allowed_types()
        for entry in types:
            assert "instance_type" in entry
            assert "tier_name" in entry
            assert "discount_percent" in entry
            assert "family" in entry
            assert "category" in entry

    def test_sorted_by_instance_type(self, checker):
        types = checker.get_all_allowed_types()
        names = [t["instance_type"] for t in types]
        assert names == sorted(names)


class TestAutoLoad:
    def test_auto_loads_on_first_query(self):
        checker = AllowListChecker()
        # Should auto-load when is_allowed is called
        assert checker.is_allowed("m5.xlarge") is True

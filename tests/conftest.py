"""Pytest configuration for the eval_audit test suite.

Adds a `slow` marker that's deselected by default. Pass `--run-slow` to
include slow-marked tests. The full suite takes ~4 min when slow tests
run; the fast subset is ~30 s.
"""
from __future__ import annotations

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="include tests marked @pytest.mark.slow (skipped by default)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-slow"):
        return
    skip_slow = pytest.mark.skip(reason="slow; pass --run-slow to include")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)

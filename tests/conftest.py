"""Shared test configuration.

The default suite never contacts the network: tests that hit the real model
are marked ``real_model`` and skipped unless explicitly requested with
``--run-real-model``.  That keeps ``pytest tests/ -q`` fully offline and
green while still making real-model coverage a first-class, opt-in target
(AGENTS.md: no mocks, real models only).
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--run-real-model",
        action="store_true",
        default=False,
        help="run tests that call the real model configured in .env",
    )


def pytest_collection_modifyitems(config, items) -> None:
    if config.getoption("--run-real-model"):
        return
    skip_real = pytest.mark.skip(
        reason="requires network + real model; pass --run-real-model"
    )
    for item in items:
        if "real_model" in item.keywords:
            item.add_marker(skip_real)

"""Registry re-export.

The ModuleRegistry class is defined in ``waycast.protocols`` so that the
protocols module stays the single home of the module contracts; this module
re-exports it for callers that prefer ``from waycast.registry import ...``.
"""
from waycast.protocols import ModuleRegistry, WaycastError  # noqa: F401

__all__ = ["ModuleRegistry", "WaycastError"]

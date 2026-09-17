"""Compatibility imports for generation recovery.

New code should import from :mod:`utu.practice.generation.recovery`.
"""

from .generation.recovery import (
    CACHE_VERSION,
    GenerationOutputError,
    GenerationRecovery,
    GenerationServiceUnavailable,
    error_detail,
    transient_error,
)

__all__ = [
    "CACHE_VERSION",
    "GenerationOutputError",
    "GenerationRecovery",
    "GenerationServiceUnavailable",
    "error_detail",
    "transient_error",
]

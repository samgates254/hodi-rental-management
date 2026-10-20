"""Allocation facade. Delegates to rental_os.algorithms.allocation."""

from .facade import (
    AllocationCharge,
    AllocationError,
    AllocationFacadeResult,
    MoneyError,
    allocate,
)

__all__ = [
    "AllocationCharge",
    "AllocationError",
    "AllocationFacadeResult",
    "MoneyError",
    "allocate",
]

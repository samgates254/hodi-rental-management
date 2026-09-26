"""Allocation facade. Delegates to rental_os.algorithms.allocation."""

from .facade import AllocationCharge, AllocationFacadeResult, allocate

__all__ = ["AllocationCharge", "AllocationFacadeResult", "allocate"]

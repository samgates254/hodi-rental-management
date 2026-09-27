"""Deposit facade. Delegates to rental_os.algorithms.deposit."""

from .facade import DepositCharge, DepositFacadeResult, apply_deposit

__all__ = ["DepositCharge", "DepositFacadeResult", "apply_deposit"]

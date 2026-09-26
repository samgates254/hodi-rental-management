"""Delinquency facade. Delegates to rental_os.algorithms.delinquency."""

from .facade import DelinquencyObligation, assess

__all__ = ["DelinquencyObligation", "assess"]

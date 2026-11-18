"""Exceptions for Trenitalia Commuter API clients."""

from __future__ import annotations


class TrenitaliaApiError(Exception):
    """Base error for API communication failures."""


class LeFrecceApiError(TrenitaliaApiError):
    """Error communicating with LeFrecce BFF API."""


class ViaggiaTrenoApiError(TrenitaliaApiError):
    """Error communicating with ViaggiaTreno API."""
"""DataUpdateCoordinator for Trenitalia Commuter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api.exceptions import LeFrecceApiError, ViaggiaTrenoApiError
from .api.lefrecce import LeFrecceClient
from .api.viaggiatreno import ViaggiaTrenoClient
from .const import (
    CONF_DELAY_THRESHOLD,
    CONF_DEST_LF_ID,
    CONF_DEST_VT_ID,
    CONF_LEFRECCE_INTERVAL,
    CONF_MAX_TRAINS,
    CONF_NO_CHANGES,
    CONF_ORIGIN_LF_ID,
    CONF_ORIGIN_VT_ID,
    CONF_PAST_WINDOW,
    CONF_REGIONAL_ONLY,
    CONF_VT_INTERVAL,
    DEFAULT_DELAY_THRESHOLD_MINUTES,
    DEFAULT_LEFRECCE_SCAN_INTERVAL_MINUTES,
    DEFAULT_MAX_TRAINS,
    DEFAULT_PAST_WINDOW_MINUTES,
    DEFAULT_SOLUTIONS_LIMIT,
    DEFAULT_VT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    ROME_TZ,
)
from .merger import build_route_snapshot
from .models import JourneySolution, RouteSnapshot

_LOGGER = logging.getLogger(__name__)

_MAX_CONSECUTIVE_VT_ERRORS = 3


@dataclass(slots=True)
class CoordinatorData:
    """Container exposed to entities."""

    snapshot: RouteSnapshot
    lefrecce_last_sync: datetime
    vt_last_sync: datetime
    cached_solutions_count: int
    last_error: str | None = None


class TrenitaliaCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Two-speed coordinator combining LeFrecce schedules and ViaggiaTreno live data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        session: aiohttp.ClientSession,
    ) -> None:
        self.config_entry = entry
        self._lf_client = LeFrecceClient(session)
        self._vt_client = ViaggiaTrenoClient(session)

        self._cached_solutions: list[JourneySolution] = []
        self._last_lf_sync: datetime | None = None
        self._consecutive_vt_errors = 0

        vt_interval = self._get_option(
            CONF_VT_INTERVAL, DEFAULT_VT_SCAN_INTERVAL_MINUTES
        )
        update_interval = (
            timedelta(minutes=vt_interval) if vt_interval > 0 else None
        )

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=update_interval,
        )

    def _get_option(self, key: str, default: Any) -> Any:
        if key in self.config_entry.options:
            return self.config_entry.options[key]
        return self.config_entry.data.get(key, default)

    def _should_refresh_lefrecce(self, now: datetime) -> bool:
        if self._last_lf_sync is None or not self._cached_solutions:
            return True

        lf_interval = self._get_option(
            CONF_LEFRECCE_INTERVAL, DEFAULT_LEFRECCE_SCAN_INTERVAL_MINUTES
        )
        if now - self._last_lf_sync >= timedelta(minutes=lf_interval):
            return True

        # Refresh early if fewer than 2 upcoming scheduled trains remain in cache
        remaining = sum(
            1
            for sol in self._cached_solutions
            if sol.departure_time >= now - timedelta(minutes=5)
        )
        return remaining < 2

    async def _async_update_data(self) -> CoordinatorData:
        now = datetime.now(ROME_TZ)
        origin_lf_id = int(self.config_entry.data[CONF_ORIGIN_LF_ID])
        dest_lf_id = int(self.config_entry.data[CONF_DEST_LF_ID])
        origin_vt_id = str(self.config_entry.data[CONF_ORIGIN_VT_ID])
        dest_vt_id: str | None = self.config_entry.data.get(CONF_DEST_VT_ID)

        no_changes = bool(self._get_option(CONF_NO_CHANGES, True))
        regional_only = bool(self._get_option(CONF_REGIONAL_ONLY, False))
        max_trains = int(self._get_option(CONF_MAX_TRAINS, DEFAULT_MAX_TRAINS))
        delay_threshold = int(
            self._get_option(CONF_DELAY_THRESHOLD, DEFAULT_DELAY_THRESHOLD_MINUTES)
        )
        past_window = int(
            self._get_option(CONF_PAST_WINDOW, DEFAULT_PAST_WINDOW_MINUTES)
        )

        last_error: str | None = None

        if self._should_refresh_lefrecce(now):
            try:
                self._cached_solutions = await self._lf_client.get_solutions(
                    origin_id=origin_lf_id,
                    destination_id=dest_lf_id,
                    departure_time=now - timedelta(minutes=past_window),
                    no_changes=no_changes,
                    regional_only=regional_only,
                    limit=DEFAULT_SOLUTIONS_LIMIT,
                )
                self._last_lf_sync = now
            except LeFrecceApiError as err:
                if not self._cached_solutions or (
                    self._last_lf_sync is not None
                    and now - self._last_lf_sync > timedelta(hours=2)
                ):
                    raise UpdateFailed(f"LeFrecce update failed: {err}") from err
                _LOGGER.warning(
                    "LeFrecce refresh failed, using cached schedule: %s", err
                )
                last_error = str(err)

        try:
            departures = await self._vt_client.get_departures(origin_vt_id, now)
            self._consecutive_vt_errors = 0
        except ViaggiaTrenoApiError as err:
            self._consecutive_vt_errors += 1
            if (
                self.data is not None
                and self._consecutive_vt_errors < _MAX_CONSECUTIVE_VT_ERRORS
            ):
                _LOGGER.warning(
                    "ViaggiaTreno temporary failure (%d/%d), keeping stale data: %s",
                    self._consecutive_vt_errors,
                    _MAX_CONSECUTIVE_VT_ERRORS,
                    err,
                )
                return CoordinatorData(
                    snapshot=self.data.snapshot,
                    lefrecce_last_sync=self.data.lefrecce_last_sync,
                    vt_last_sync=self.data.vt_last_sync,
                    cached_solutions_count=len(self._cached_solutions),
                    last_error=str(err),
                )
            raise UpdateFailed(f"ViaggiaTreno update failed: {err}") from err

        snapshot = await build_route_snapshot(
            self._cached_solutions,
            departures,
            vt_client=self._vt_client,
            user_origin_vt_id=origin_vt_id,
            user_dest_vt_id=dest_vt_id,
            now=now,
            max_trains=max_trains,
            delay_threshold=delay_threshold,
            enable_andamento_fallback=True,
        )

        return CoordinatorData(
            snapshot=snapshot,
            lefrecce_last_sync=self._last_lf_sync or now,
            vt_last_sync=now,
            cached_solutions_count=len(self._cached_solutions),
            last_error=last_error,
        )
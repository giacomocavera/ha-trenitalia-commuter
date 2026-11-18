"""Async client for LeFrecce BFF API."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import aiohttp

from ..const import DEFAULT_REQUEST_TIMEOUT_SECONDS, LEFRECCE_BASE_URL, ROME_TZ
from ..models import JourneySolution, LeFrecceStation, SolutionLeg
from .exceptions import LeFrecceApiError


class LeFrecceClient:
    """Client for querying LeFrecce stations and journey solutions."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def search_stations(
        self, query: str, *, include_multistation: bool = False
    ) -> list[LeFrecceStation]:
        """Search stations by name."""
        cleaned = query.strip()
        if not cleaned:
            return []

        url = f"{LEFRECCE_BASE_URL}/locations/search"
        try:
            async with self._session.get(
                url,
                params={"name": cleaned},
                headers={"Accept": "application/json"},
                timeout=self._timeout,
            ) as resp:
                if resp.status != 200:
                    raise LeFrecceApiError(
                        f"LeFrecce locations search failed with status {resp.status}"
                    )
                payload = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise LeFrecceApiError(f"LeFrecce locations search error: {err}") from err

        if not isinstance(payload, list):
            raise LeFrecceApiError("Unexpected LeFrecce locations payload format")

        stations: list[LeFrecceStation] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            multistation = bool(item.get("multistation", False))
            if not include_multistation and multistation:
                continue
            station_id = item.get("id")
            name = item.get("name")
            if station_id is None or not name:
                continue
            stations.append(
                LeFrecceStation(
                    id=int(station_id),
                    name=str(name),
                    display_name=str(item.get("displayName") or name),
                    timezone=str(item.get("timezone") or "Europe/Rome"),
                    multistation=multistation,
                )
            )
        return stations

    async def get_solutions(
        self,
        origin_id: int,
        destination_id: int,
        departure_time: datetime,
        *,
        no_changes: bool = True,
        regional_only: bool = False,
        limit: int = 15,
    ) -> list[JourneySolution]:
        """Fetch journey solutions from origin to destination."""
        dt_rome = departure_time.astimezone(ROME_TZ)
        body: dict[str, Any] = {
            "departureLocationId": origin_id,
            "arrivalLocationId": destination_id,
            "departureTime": dt_rome.isoformat(timespec="milliseconds"),
            "adults": 1,
            "children": 0,
            "criteria": {
                "frecceOnly": False,
                "regionalOnly": regional_only,
                "noChanges": no_changes,
                "order": "DEPARTURE_DATE",
                "limit": limit,
                "offset": 0,
            },
            "advancedSearchRequest": {
                "bestFare": False,
                "bikeFilter": False,
            },
        }

        url = f"{LEFRECCE_BASE_URL}/ticket/solutions"
        try:
            async with self._session.post(
                url,
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=self._timeout,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise LeFrecceApiError(
                        f"LeFrecce solutions failed ({resp.status}): {text[:200]}"
                    )
                payload = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise LeFrecceApiError(f"LeFrecce solutions error: {err}") from err

        if not isinstance(payload, dict):
            raise LeFrecceApiError("Unexpected LeFrecce solutions payload format")

        raw_solutions = payload.get("solutions") or []
        results: list[JourneySolution] = []
        for entry in raw_solutions:
            sol = entry.get("solution") if isinstance(entry, dict) else None
            if not isinstance(sol, dict):
                continue
            parsed = _parse_solution(sol)
            if parsed is not None:
                results.append(parsed)
        return results


def _parse_iso_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ROME_TZ)
    return dt.astimezone(ROME_TZ)


def _parse_solution(sol: dict[str, Any]) -> JourneySolution | None:
    dep_dt = _parse_iso_dt(sol.get("departureTime"))
    arr_dt = _parse_iso_dt(sol.get("arrivalTime"))
    if dep_dt is None or arr_dt is None:
        return None

    raw_nodes = sol.get("nodes") or []
    legs: list[SolutionLeg] = []
    for node in raw_nodes:
        if not isinstance(node, dict):
            continue
        node_dep = _parse_iso_dt(node.get("departureTime"))
        node_arr = _parse_iso_dt(node.get("arrivalTime"))
        train = node.get("train") or {}
        if node_dep is None or node_arr is None or not isinstance(train, dict):
            continue

        train_num = str(
            train.get("name") or train.get("description") or ""
        ).strip()
        if not train_num:
            continue

        bdo_origin = node.get("bdoOrigin")
        legs.append(
            SolutionLeg(
                train_number=train_num,
                raw_denomination=_opt_str(train.get("denomination")),
                acronym=_opt_str(train.get("acronym")),
                train_category=_opt_str(train.get("trainCategory")),
                origin=str(node.get("origin") or ""),
                destination=str(node.get("destination") or ""),
                departure_time=node_dep,
                arrival_time=node_arr,
                bdo_origin=_opt_str(bdo_origin),
            )
        )

    if not legs:
        return None

    return JourneySolution(
        departure_time=dep_dt,
        arrival_time=arr_dt,
        duration=str(sol.get("duration") or ""),
        status=str(sol.get("status") or ""),
        legs=legs,
    )


def _opt_str(val: Any) -> str | None:
    if val is None:
        return None
    text = str(val).strip()
    return text or None
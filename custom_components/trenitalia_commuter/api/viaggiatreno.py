"""Async client for ViaggiaTreno REST API."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from urllib.parse import quote

import aiohttp

from ..const import (
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ROME_TZ,
    VIAGGIATRENO_BASE_URL,
    VIAGGIATRENO_USER_AGENT,
)
from ..models import LiveTrainInfo, ViaggiaTrenoStation
from .exceptions import ViaggiaTrenoApiError

_EN_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_EN_MONTHS = (
    "",
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def format_viaggiatreno_date(dt: datetime) -> str:
    """Format datetime into ViaggiaTreno's English JS Date URL segment."""
    local_dt = dt.astimezone(ROME_TZ)
    weekday = _EN_WEEKDAYS[local_dt.weekday()]
    month = _EN_MONTHS[local_dt.month]
    offset = local_dt.strftime("%z") or "+0100"
    raw = (
        f"{weekday} {month} {local_dt.day:02d} {local_dt.year} "
        f"{local_dt.hour:02d}:{local_dt.minute:02d}:{local_dt.second:02d} "
        f"GMT{offset}"
    )
    return raw.replace(" ", "%20")


class ViaggiaTrenoClient:
    """Client for ViaggiaTreno departures, train search, and live train status."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        timeout_seconds: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._headers = {
            "User-Agent": VIAGGIATRENO_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        }

    async def autocomplete_station(self, query: str) -> list[ViaggiaTrenoStation]:
        """Search ViaggiaTreno stations by name."""
        cleaned = query.strip()
        if not cleaned:
            return []

        url = f"{VIAGGIATRENO_BASE_URL}/autocompletaStazione/{quote(cleaned)}"
        text = await self._get_text(url)
        stations: list[ViaggiaTrenoStation] = []
        for line in text.splitlines():
            line = line.strip()
            if "|" not in line:
                continue
            name, vt_id = line.split("|", 1)
            name = name.strip()
            vt_id = vt_id.strip()
            if name and vt_id:
                stations.append(ViaggiaTrenoStation(name=name, vt_id=vt_id))
        return stations

    async def get_departures(
        self, station_vt_id: str, when: datetime
    ) -> list[LiveTrainInfo]:
        """Fetch departure board for a station."""
        encoded_date = format_viaggiatreno_date(when)
        url = f"{VIAGGIATRENO_BASE_URL}/partenze/{quote(station_vt_id)}/{encoded_date}"
        payload = await self._get_json(url)
        if payload is None:
            return []
        if not isinstance(payload, list):
            raise ViaggiaTrenoApiError("Unexpected ViaggiaTreno departures payload")

        results: list[LiveTrainInfo] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            parsed = _parse_departure_item(item)
            if parsed is not None:
                results.append(parsed)
        return results

    async def find_train_origins(
        self, train_number: str
    ) -> list[tuple[str, str, int]]:
        """Return list of (train_number, origin_vt_id, departure_date_ms)."""
        cleaned = str(train_number).strip()
        if not cleaned:
            return []

        url = (
            f"{VIAGGIATRENO_BASE_URL}/cercaNumeroTrenoTrenoAutocomplete/"
            f"{quote(cleaned)}"
        )
        text = await self._get_text(url)
        matches: list[tuple[str, str, int]] = []
        for line in text.splitlines():
            line = line.strip()
            if "|" not in line:
                continue
            _, right = line.split("|", 1)
            parts = right.strip().split("-")
            if len(parts) != 3:
                continue
            num, origin_id, epoch_str = parts
            try:
                epoch_ms = int(epoch_str)
            except ValueError:
                continue
            matches.append((num.strip(), origin_id.strip(), epoch_ms))
        return matches

    async def get_train_status(
        self,
        origin_vt_id: str,
        train_number: str,
        departure_date_ms: int,
        user_origin_vt_id: str | None = None,
    ) -> LiveTrainInfo | None:
        """Fetch live status of a single train via andamentoTreno."""
        url = (
            f"{VIAGGIATRENO_BASE_URL}/andamentoTreno/"
            f"{quote(origin_vt_id)}/{quote(str(train_number).strip())}/{departure_date_ms}"
        )
        payload = await self._get_json(url, allow_empty=True)
        if not isinstance(payload, dict):
            return None
        return _parse_andamento(
            payload,
            origin_vt_id=origin_vt_id,
            departure_date_ms=departure_date_ms,
            user_origin_vt_id=user_origin_vt_id,
        )

    async def _get_text(self, url: str) -> str:
        try:
            async with self._session.get(
                url, headers=self._headers, timeout=self._timeout
            ) as resp:
                if resp.status == 204:
                    return ""
                if resp.status != 200:
                    raise ViaggiaTrenoApiError(
                        f"ViaggiaTreno GET {url} returned HTTP {resp.status}"
                    )
                return await resp.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise ViaggiaTrenoApiError(f"ViaggiaTreno network error: {err}") from err

    async def _get_json(self, url: str, *, allow_empty: bool = False) -> Any:
        try:
            async with self._session.get(
                url, headers=self._headers, timeout=self._timeout
            ) as resp:
                if resp.status == 204:
                    return None
                if resp.status != 200:
                    raise ViaggiaTrenoApiError(
                        f"ViaggiaTreno GET {url} returned HTTP {resp.status}"
                    )
                text = await resp.text()
                if not text.strip():
                    if allow_empty:
                        return None
                    return []
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise ViaggiaTrenoApiError(f"ViaggiaTreno JSON error: {err}") from err


def _clean_platform(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_category(cat: Any, cat_desc: Any) -> str:
    desc = str(cat_desc or "").strip()
    if desc:
        return desc
    return str(cat or "").strip()


def _parse_departure_item(item: dict[str, Any]) -> LiveTrainInfo | None:
    num = item.get("numeroTreno")
    cod_origine = item.get("codOrigine")
    if num is None or not cod_origine:
        return None

    non_partito = bool(item.get("nonPartito", False))
    raw_delay = item.get("ritardo")
    delay = 0 if raw_delay is None else int(raw_delay)
    raw_dep_ms = item.get("dataPartenzaTreno")

    return LiveTrainInfo(
        train_number=str(num).strip(),
        origin_vt_id=str(cod_origine).strip(),
        departure_date_ms=int(raw_dep_ms) if raw_dep_ms is not None else None,
        category=_clean_category(
            item.get("categoria"), item.get("categoriaDescrizione")
        ),
        destination=str(item.get("destinazione") or "").strip(),
        delay=delay,
        non_partito=non_partito,
        in_station=bool(item.get("inStazione", False)),
        circulating=bool(item.get("circolante", False)),
        arrived=bool(item.get("arrivato", False)),
        provvedimento=int(item.get("provvedimento") or 0),
        scheduled_platform=_clean_platform(
            item.get("binarioProgrammatoPartenzaDescrizione")
        ),
        actual_platform=_clean_platform(
            item.get("binarioEffettivoPartenzaDescrizione")
        ),
        departed_from_user_origin=None,
        suppressed_stops=[],
        source="departures",
    )


def _parse_andamento(
    payload: dict[str, Any],
    *,
    origin_vt_id: str,
    departure_date_ms: int,
    user_origin_vt_id: str | None,
) -> LiveTrainInfo | None:
    num = payload.get("numeroTreno")
    if num is None:
        return None

    non_partito = bool(payload.get("nonPartito", False))
    raw_delay = payload.get("ritardo")
    delay = 0 if raw_delay is None else int(raw_delay)

    sched_platform: str | None = None
    actual_platform: str | None = None
    departed_from_user_origin: bool | None = None

    fermate = payload.get("fermate")
    if isinstance(fermate, list) and user_origin_vt_id:
        for stop in fermate:
            if not isinstance(stop, dict):
                continue
            if str(stop.get("id") or "").strip() == user_origin_vt_id:
                departed_from_user_origin = stop.get("partenzaReale") is not None
                sched_platform = _clean_platform(
                    stop.get("binarioProgrammatoPartenzaDescrizione")
                )
                actual_platform = _clean_platform(
                    stop.get("binarioEffettivoPartenzaDescrizione")
                )
                break

    suppressed_stops: list[str] = []
    raw_suppressed = payload.get("fermateSoppresse")
    if isinstance(raw_suppressed, list):
        for stop in raw_suppressed:
            if isinstance(stop, str) and stop.strip():
                suppressed_stops.append(stop.strip())
            elif isinstance(stop, dict):
                stop_id = stop.get("id") or stop.get("idStazione")
                if stop_id:
                    suppressed_stops.append(str(stop_id).strip())

    return LiveTrainInfo(
        train_number=str(num).strip(),
        origin_vt_id=str(payload.get("idOrigine") or origin_vt_id).strip(),
        departure_date_ms=departure_date_ms,
        category=_clean_category(
            payload.get("categoria"), payload.get("categoriaDescrizione")
        ),
        destination=str(payload.get("destinazione") or "").strip(),
        delay=delay,
        non_partito=non_partito,
        in_station=bool(payload.get("inStazione", False)),
        circulating=bool(payload.get("circolante", False)),
        arrived=False,
        provvedimento=int(payload.get("provvedimento") or 0),
        scheduled_platform=sched_platform,
        actual_platform=actual_platform,
        departed_from_user_origin=departed_from_user_origin,
        suppressed_stops=suppressed_stops,
        source="andamento",
    )
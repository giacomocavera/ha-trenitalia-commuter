"""Merge LeFrecce scheduled solutions with ViaggiaTreno real-time status."""

from __future__ import annotations

from datetime import datetime, timedelta

from .api.exceptions import ViaggiaTrenoApiError
from .api.viaggiatreno import ViaggiaTrenoClient
from .const import ROME_TZ
from .models import (
    CommuterTrain,
    JourneySolution,
    LiveTrainInfo,
    MergedLeg,
    RouteSnapshot,
    SolutionLeg,
    TrainStatus,
)


def sanitize_train_category(
    leg: SolutionLeg, live: LiveTrainInfo | None = None
) -> str:
    """Return a clean train category avoiding raw LeFrecce translation keys."""
    denom = leg.raw_denomination
    if denom and not denom.startswith("label.") and "." not in denom:
        return denom

    if live and live.category:
        return live.category

    if leg.acronym:
        return leg.acronym.upper()

    if leg.train_category:
        return leg.train_category.upper()

    return "TRAIN"


def _build_departure_lookup(
    departures: list[LiveTrainInfo],
) -> tuple[dict[tuple[str, str], LiveTrainInfo], dict[str, list[LiveTrainInfo]]]:
    by_pair: dict[tuple[str, str], LiveTrainInfo] = {}
    by_num: dict[str, list[LiveTrainInfo]] = {}
    for item in departures:
        by_pair[(item.train_number, item.origin_vt_id)] = item
        by_num.setdefault(item.train_number, []).append(item)
    return by_pair, by_num


def _midnight_ms(dt: datetime) -> int:
    local = dt.astimezone(ROME_TZ)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(midnight.timestamp() * 1000)


async def _fetch_fallback_live(
    vt_client: ViaggiaTrenoClient,
    leg: SolutionLeg,
    user_origin_vt_id: str,
    cached_dep_date_ms: int | None,
) -> LiveTrainInfo | None:
    origin_vt_id = leg.bdo_origin
    dep_ms = cached_dep_date_ms

    if origin_vt_id is None or dep_ms is None:
        try:
            origins = await vt_client.find_train_origins(leg.train_number)
        except ViaggiaTrenoApiError:
            origins = []

        if origin_vt_id:
            for num, orig, ms in origins:
                if num == leg.train_number and orig == origin_vt_id:
                    dep_ms = ms
                    break
        elif len(origins) == 1:
            _, origin_vt_id, dep_ms = origins[0]

    if not origin_vt_id:
        return None

    if dep_ms is None:
        dep_ms = _midnight_ms(leg.departure_time)

    try:
        return await vt_client.get_train_status(
            origin_vt_id=origin_vt_id,
            train_number=leg.train_number,
            departure_date_ms=dep_ms,
            user_origin_vt_id=user_origin_vt_id,
        )
    except ViaggiaTrenoApiError:
        return None


def _compute_status(
    live: LiveTrainInfo | None,
    user_origin_vt_id: str,
    user_dest_vt_id: str | None,
) -> tuple[TrainStatus, bool, bool]:
    """Return (status, cancelled, partially_cancelled)."""
    if live is None:
        return "regular", False, False

    if live.provvedimento == 1:
        return "cancelled", True, False

    if live.provvedimento == 2:
        suppressed = set(live.suppressed_stops)
        if user_origin_vt_id in suppressed or (
            user_dest_vt_id and user_dest_vt_id in suppressed
        ):
            return "cancelled", True, True
        return "partially_cancelled", False, True

    if live.non_partito:
        return "not_departed", False, False

    if live.delay > 0:
        return "delayed", False, False

    return "regular", False, False


async def build_route_snapshot(
    solutions: list[JourneySolution],
    departures: list[LiveTrainInfo],
    *,
    vt_client: ViaggiaTrenoClient | None,
    user_origin_vt_id: str,
    user_dest_vt_id: str | None,
    now: datetime,
    max_trains: int = 8,
    delay_threshold: int = 5,
    enable_andamento_fallback: bool = True,
) -> RouteSnapshot:
    """Merge LeFrecce solutions and ViaggiaTreno departures into a RouteSnapshot."""
    now_rome = now.astimezone(ROME_TZ)
    by_pair, by_num = _build_departure_lookup(departures)

    # Window after which departures board likely covers ~1h40m; only query
    # andamentoTreno fallback for imminent trains (<= 2h ahead) or disrupted ones.
    imminent_cutoff = now_rome + timedelta(minutes=20)

    merged_trains: list[CommuterTrain] = []
    fallback_calls = 0

    for sol in solutions:
        first_leg = sol.legs[0]
        live: LiveTrainInfo | None = None

        if first_leg.bdo_origin:
            live = by_pair.get((first_leg.train_number, first_leg.bdo_origin))
        elif len(by_num.get(first_leg.train_number, [])) == 1:
            live = by_num[first_leg.train_number][0]

        needs_fallback = False
        if vt_client is not None and enable_andamento_fallback:
            if live is None and first_leg.departure_time <= imminent_cutoff:
                needs_fallback = True
            elif live is not None and live.provvedimento == 2:
                # Fetch suppressed stops list to know if our origin/dest is affected
                needs_fallback = True

        if needs_fallback and vt_client is not None:
            fallback_live = await _fetch_fallback_live(
                vt_client,
                first_leg,
                user_origin_vt_id,
                live.departure_date_ms if live else None,
            )
            fallback_calls += 1
            if fallback_live is not None:
                # Keep departure board fields if andamento missed platform/delay
                if live is not None and fallback_live.delay == 0 and live.delay > 0:
                    fallback_live = LiveTrainInfo(
                        **{
                            **fallback_live.__dict__,
                            "delay": live.delay,
                        }
                    )
                live = fallback_live

        # Skip trains confirmed to have already departed user's origin station
        if live and live.departed_from_user_origin is True:
            continue

        delay = live.delay if live else 0
        expected_dep = first_leg.departure_time + timedelta(minutes=delay)

        status, cancelled, partially_cancelled = _compute_status(
            live, user_origin_vt_id, user_dest_vt_id
        )

        # Keep upcoming trains; also keep recently cancelled trains (last 5 min)
        # so commuters clearly see their train was cancelled.
        if cancelled:
            if first_leg.departure_time < now_rome - timedelta(minutes=5):
                continue
        else:
            if expected_dep < now_rome - timedelta(minutes=1):
                continue

        first_cat = sanitize_train_category(first_leg, live)
        merged_legs = [
            MergedLeg(
                train_number=leg.train_number,
                category=(
                    first_cat if idx == 0 else sanitize_train_category(leg, None)
                ),
                origin=leg.origin,
                destination=leg.destination,
                scheduled_departure=leg.departure_time,
                scheduled_arrival=leg.arrival_time,
            )
            for idx, leg in enumerate(sol.legs)
        ]

        merged_trains.append(
            CommuterTrain(
                train_number=first_leg.train_number,
                category=first_cat,
                origin=first_leg.origin,
                destination=(live.destination if live and live.destination else first_leg.destination),
                bdo_origin=first_leg.bdo_origin,
                scheduled_departure=sol.departure_time,
                expected_departure=expected_dep,
                scheduled_arrival=sol.arrival_time,
                duration=sol.duration,
                delay=delay,
                scheduled_platform=live.scheduled_platform if live else None,
                actual_platform=live.actual_platform if live else None,
                status=status,
                cancelled=cancelled,
                partially_cancelled=partially_cancelled,
                not_departed=live.non_partito if live else False,
                in_station=live.in_station if live else False,
                changes=max(0, len(sol.legs) - 1),
                legs=merged_legs,
            )
        )

    merged_trains.sort(key=lambda t: t.expected_departure)
    limited_trains = merged_trains[:max_trains]

    first_scheduled = limited_trains[0] if limited_trains else None
    next_operating = next((t for t in limited_trains if not t.cancelled), None)

    cancelled_count = sum(1 for t in limited_trains if t.cancelled)
    affected: list[str] = []
    reason: str = "ok"

    if first_scheduled and first_scheduled.cancelled:
        reason = "cancelled"
        affected.append(f"{first_scheduled.category} {first_scheduled.train_number}")
    elif next_operating and next_operating.partially_cancelled:
        reason = "partially_cancelled"
        affected.append(f"{next_operating.category} {next_operating.train_number}")
    elif next_operating and next_operating.delay >= delay_threshold:
        reason = "delay"
        affected.append(
            f"{next_operating.category} {next_operating.train_number} (+{next_operating.delay}m)"
        )

    return RouteSnapshot(
        trains=limited_trains,
        next_train=next_operating,
        first_scheduled_train=first_scheduled,
        disruption=reason != "ok",
        disruption_reason=reason,  # type: ignore[arg-type]
        affected_trains=affected,
        cancelled_count=cancelled_count,
        fallback_calls=fallback_calls,
    )
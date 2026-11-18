"""Unit tests for LeFrecce + ViaggiaTreno snapshot merging."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from custom_components.trenitalia_commuter.const import ROME_TZ
from custom_components.trenitalia_commuter.merger import (
    build_route_snapshot,
    sanitize_train_category,
)
from custom_components.trenitalia_commuter.models import (
    JourneySolution,
    LiveTrainInfo,
    SolutionLeg,
)


def _dt(hour: int, minute: int) -> datetime:
    return datetime(2026, 11, 18, hour, minute, 0, tzinfo=ROME_TZ)


def _solution(
    train_number: str,
    dep_hm: tuple[int, int],
    arr_hm: tuple[int, int],
    *,
    bdo_origin: str | None = "S00517",
    denomination: str | None = "SFM2",
    acronym: str | None = "SF",
) -> JourneySolution:
    dep = _dt(*dep_hm)
    arr = _dt(*arr_hm)
    return JourneySolution(
        departure_time=dep,
        arrival_time=arr,
        duration="00:14",
        status="SALEABLE",
        legs=[
            SolutionLeg(
                train_number=train_number,
                raw_denomination=denomination,
                acronym=acronym,
                train_category="sfm",
                origin="Settimo",
                destination="Torino Porta Susa",
                departure_time=dep,
                arrival_time=arr,
                bdo_origin=bdo_origin,
            )
        ],
    )


def _live(
    train_number: str,
    origin_vt_id: str,
    *,
    delay: int = 0,
    non_partito: bool = False,
    provvedimento: int = 0,
    platform: str | None = "1",
    departed_from_user_origin: bool | None = None,
    suppressed_stops: list[str] | None = None,
) -> LiveTrainInfo:
    return LiveTrainInfo(
        train_number=train_number,
        origin_vt_id=origin_vt_id,
        departure_date_ms=1794956400000,
        category="SFM",
        destination="CHIVASSO",
        delay=delay,
        non_partito=non_partito,
        in_station=False,
        circulating=not non_partito,
        arrived=False,
        provvedimento=provvedimento,
        scheduled_platform=platform,
        actual_platform=platform,
        departed_from_user_origin=departed_from_user_origin,
        suppressed_stops=suppressed_stops or [],
    )


def test_sanitize_train_category_ignores_raw_label() -> None:
    leg = _solution(
        "26660",
        (9, 18),
        (9, 32),
        denomination="label.train.info.denomination.sf",
        acronym="SF",
    ).legs[0]
    assert sanitize_train_category(leg) == "SF"


async def test_homonym_train_178_matches_bdo_origin() -> None:
    now = _dt(9, 0)
    sol = _solution("178", (9, 15), (9, 45), bdo_origin="S01700", denomination="EC")
    departures = [
        _live("178", "S01765", delay=0, platform="3"),   # Como Lago
        _live("178", "S01700", delay=14, platform="8"),  # Milano Centrale
    ]
    snap = await build_route_snapshot(
        [sol],
        departures,
        vt_client=None,
        user_origin_vt_id="S00229",
        user_dest_vt_id="S00035",
        now=now,
    )
    assert snap.next_train is not None
    assert snap.next_train.delay == 14
    assert snap.next_train.platform == "8"
    assert snap.disruption is True
    assert snap.disruption_reason == "delay"


async def test_cancelled_first_train_is_kept_in_list_and_skipped_for_next_train() -> None:
    now = _dt(9, 0)
    sol_cancelled = _solution("26224", (9, 5), (9, 19), bdo_origin="S00517")
    sol_next = _solution("26130", (9, 25), (9, 39), bdo_origin="S00518")
    departures = [
        _live("26224", "S00517", provvedimento=1, platform="1"),
        _live("26130", "S00518", delay=0, platform="4"),
    ]
    snap = await build_route_snapshot(
        [sol_cancelled, sol_next],
        departures,
        vt_client=None,
        user_origin_vt_id="S00229",
        user_dest_vt_id="S00035",
        now=now,
    )
    assert len(snap.trains) == 2
    assert snap.trains[0].cancelled is True
    assert snap.next_train is not None
    assert snap.next_train.train_number == "26130"
    assert snap.disruption is True
    assert snap.disruption_reason == "cancelled"
    assert snap.cancelled_count == 1


async def test_partially_cancelled_checks_suppressed_stops_via_fallback() -> None:
    now = _dt(9, 0)
    sol = _solution("26152", (9, 10), (9, 24), bdo_origin="S00517")
    departures = [_live("26152", "S00517", provvedimento=2, platform="2")]

    vt_mock = AsyncMock()
    vt_mock.get_train_status.return_value = _live(
        "26152",
        "S00517",
        provvedimento=2,
        suppressed_stops=["S00035"],  # User destination is suppressed!
    )

    snap = await build_route_snapshot(
        [sol],
        departures,
        vt_client=vt_mock,
        user_origin_vt_id="S00229",
        user_dest_vt_id="S00035",
        now=now,
    )
    assert snap.fallback_calls == 1
    assert snap.trains[0].cancelled is True
    assert snap.next_train is None
    assert snap.disruption is True


async def test_delayed_past_train_recovered_via_andamento_when_not_departed() -> None:
    now = _dt(9, 15)
    # Scheduled 10 mins ago, dropped from partenze, but delayed +18 mins!
    sol = _solution("26224", (9, 5), (9, 19), bdo_origin="S00517")

    vt_mock = AsyncMock()
    vt_mock.find_train_origins.return_value = [("26224", "S00517", 1794956400000)]
    vt_mock.get_train_status.return_value = _live(
        "26224",
        "S00517",
        delay=18,
        platform="2",
        departed_from_user_origin=False,
    )

    snap = await build_route_snapshot(
        [sol],
        [],
        vt_client=vt_mock,
        user_origin_vt_id="S00229",
        user_dest_vt_id="S00035",
        now=now,
    )
    assert snap.next_train is not None
    assert snap.next_train.delay == 18
    assert snap.next_train.expected_departure == _dt(9, 5) + timedelta(minutes=18)


async def test_already_departed_train_is_excluded() -> None:
    now = _dt(9, 15)
    sol = _solution("26224", (9, 5), (9, 19), bdo_origin="S00517")

    vt_mock = AsyncMock()
    vt_mock.find_train_origins.return_value = [("26224", "S00517", 1794956400000)]
    vt_mock.get_train_status.return_value = _live(
        "26224",
        "S00517",
        delay=15,
        departed_from_user_origin=True,
    )

    snap = await build_route_snapshot(
        [sol],
        [],
        vt_client=vt_mock,
        user_origin_vt_id="S00229",
        user_dest_vt_id="S00035",
        now=now,
    )
    assert snap.trains == []
    assert snap.next_train is None
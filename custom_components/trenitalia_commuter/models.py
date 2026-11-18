"""Data models for Trenitalia Commuter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

TrainStatus = Literal[
    "regular",
    "delayed",
    "not_departed",
    "cancelled",
    "partially_cancelled",
]


@dataclass(frozen=True, slots=True)
class LeFrecceStation:
    """Station returned by LeFrecce locations search."""

    id: int
    name: str
    display_name: str
    timezone: str
    multistation: bool


@dataclass(frozen=True, slots=True)
class ViaggiaTrenoStation:
    """Station returned by ViaggiaTreno autocomplete."""

    name: str
    vt_id: str


@dataclass(frozen=True, slots=True)
class StationMatchResult:
    """Result of matching a LeFrecce station to ViaggiaTreno."""

    matched: ViaggiaTrenoStation | None
    candidates: list[ViaggiaTrenoStation]
    confident: bool
    reason: str


@dataclass(frozen=True, slots=True)
class SolutionLeg:
    """Single leg of a LeFrecce journey solution."""

    train_number: str
    raw_denomination: str | None
    acronym: str | None
    train_category: str | None
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    bdo_origin: str | None


@dataclass(frozen=True, slots=True)
class JourneySolution:
    """Journey solution returned by LeFrecce."""

    departure_time: datetime
    arrival_time: datetime
    duration: str
    status: str
    legs: list[SolutionLeg]


@dataclass(frozen=True, slots=True)
class LiveTrainInfo:
    """Normalized real-time status from ViaggiaTreno."""

    train_number: str
    origin_vt_id: str
    departure_date_ms: int | None
    category: str
    destination: str
    delay: int
    non_partito: bool
    in_station: bool
    circulating: bool
    arrived: bool
    provvedimento: int
    scheduled_platform: str | None
    actual_platform: str | None
    departed_from_user_origin: bool | None
    suppressed_stops: list[str] = field(default_factory=list)
    source: Literal["departures", "andamento"] = "departures"


@dataclass(frozen=True, slots=True)
class MergedLeg:
    """Serializable leg inside a merged train entry."""

    train_number: str
    category: str
    origin: str
    destination: str
    scheduled_departure: datetime
    scheduled_arrival: datetime

    def to_dict(self) -> dict[str, str]:
        """Serialize to Home Assistant attribute dict."""
        return {
            "train_number": self.train_number,
            "category": self.category,
            "origin": self.origin,
            "destination": self.destination,
            "scheduled_departure": self.scheduled_departure.isoformat(),
            "scheduled_arrival": self.scheduled_arrival.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class CommuterTrain:
    """Merged scheduled + live train ready for Home Assistant entities."""

    train_number: str
    category: str
    origin: str
    destination: str
    bdo_origin: str | None
    scheduled_departure: datetime
    expected_departure: datetime
    scheduled_arrival: datetime
    duration: str
    delay: int
    scheduled_platform: str | None
    actual_platform: str | None
    status: TrainStatus
    cancelled: bool
    partially_cancelled: bool
    not_departed: bool
    in_station: bool
    changes: int
    legs: list[MergedLeg]

    @property
    def platform(self) -> str | None:
        """Return actual platform if assigned, otherwise scheduled platform."""
        return self.actual_platform or self.scheduled_platform

    @property
    def platform_confirmed(self) -> bool:
        """Return True if an actual platform has been assigned."""
        return bool(self.actual_platform)

    def to_dict(self) -> dict[str, object]:
        """Serialize to Home Assistant attribute dict."""
        return {
            "train_number": self.train_number,
            "category": self.category,
            "origin": self.origin,
            "destination": self.destination,
            "bdo_origin": self.bdo_origin,
            "scheduled_departure": self.scheduled_departure.isoformat(),
            "expected_departure": self.expected_departure.isoformat(),
            "scheduled_arrival": self.scheduled_arrival.isoformat(),
            "duration": self.duration,
            "delay": self.delay,
            "scheduled_platform": self.scheduled_platform,
            "actual_platform": self.actual_platform,
            "platform": self.platform,
            "platform_confirmed": self.platform_confirmed,
            "status": self.status,
            "cancelled": self.cancelled,
            "partially_cancelled": self.partially_cancelled,
            "not_departed": self.not_departed,
            "in_station": self.in_station,
            "changes": self.changes,
            "legs": [leg.to_dict() for leg in self.legs],
        }


@dataclass(frozen=True, slots=True)
class RouteSnapshot:
    """Computed snapshot consumed by Home Assistant sensor entities."""

    trains: list[CommuterTrain]
    next_train: CommuterTrain | None
    first_scheduled_train: CommuterTrain | None
    disruption: bool
    disruption_reason: Literal["ok", "delay", "cancelled", "partially_cancelled"]
    affected_trains: list[str]
    cancelled_count: int
    fallback_calls: int
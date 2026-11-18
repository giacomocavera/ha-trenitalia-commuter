"""Unit tests for LeFrecce <-> ViaggiaTreno station matching."""

from __future__ import annotations

from custom_components.trenitalia_commuter.matcher import (
    match_lefrecce_to_viaggiatreno,
    normalize_station_name,
)
from custom_components.trenitalia_commuter.models import (
    LeFrecceStation,
    ViaggiaTrenoStation,
)


def _lf(station_id: int, name: str) -> LeFrecceStation:
    return LeFrecceStation(
        id=station_id,
        name=name,
        display_name=name,
        timezone="Europe/Rome",
        multistation=False,
    )


def test_normalize_station_name() -> None:
    assert normalize_station_name("Ciriè") == "CIRIE"
    assert normalize_station_name("Cirie'") == "CIRIE'"
    assert normalize_station_name("  Torino   Porta Susa ") == "TORINO PORTA SUSA"


def test_torino_porta_susa_different_codes() -> None:
    lf = _lf(830000222, "Torino Porta Susa")
    candidates = [
        ViaggiaTrenoStation("TORINO PORTA NUOVA", "S00219"),
        ViaggiaTrenoStation("TORINO PORTA SUSA", "S00035"),
    ]
    res = match_lefrecce_to_viaggiatreno(lf, candidates)
    assert res.confident is True
    assert res.matched is not None
    assert res.matched.vt_id == "S00035"
    assert res.reason == "exact_normalized_name"


def test_roma_balduina_avoids_wrong_numeric_code() -> None:
    # LeFrecce Roma Balduina is 830008325, whereas VT S08325 is Roma S. Filippo Neri!
    lf = _lf(830008325, "Roma Balduina")
    candidates = [
        ViaggiaTrenoStation("ROMA SAN FILIPPO NERI", "S08325"),
        ViaggiaTrenoStation("ROMA BALDUINA", "S08327"),
    ]
    res = match_lefrecce_to_viaggiatreno(lf, candidates)
    assert res.confident is True
    assert res.matched is not None
    assert res.matched.vt_id == "S08327"


def test_reggio_emilia_av_suffix_fallback() -> None:
    lf = _lf(830005254, "Reggio Emilia Av")
    candidates = [
        ViaggiaTrenoStation("REGGIO EMILIA", "S05050"),
        ViaggiaTrenoStation("REGGIO EMILIA AV MEDIOPADANA", "S05254"),
    ]
    res = match_lefrecce_to_viaggiatreno(lf, candidates)
    assert res.confident is True
    assert res.matched is not None
    assert res.matched.vt_id == "S05254"
    assert res.reason == "suffix_id_fallback"


def test_cirie_apostrophe_match() -> None:
    lf = _lf(830000090, "Cirie'")
    candidates = [ViaggiaTrenoStation("CIRIE'", "S00090")]
    res = match_lefrecce_to_viaggiatreno(lf, candidates)
    assert res.confident is True
    assert res.matched is not None
    assert res.matched.vt_id == "S00090"


def test_ambiguous_candidates_not_confident() -> None:
    lf = _lf(830099999, "San Marco")
    candidates = [
        ViaggiaTrenoStation("SAN MARCO VECCHIO", "S06001"),
        ViaggiaTrenoStation("SAN MARCO RIONE", "S06002"),
    ]
    res = match_lefrecce_to_viaggiatreno(lf, candidates)
    assert res.confident is False
    assert res.matched is None
    assert res.reason == "ambiguous"
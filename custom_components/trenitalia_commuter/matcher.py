"""Station matching utilities between LeFrecce and ViaggiaTreno."""

from __future__ import annotations

import re
import unicodedata

from .api.viaggiatreno import ViaggiaTrenoClient
from .models import LeFrecceStation, StationMatchResult, ViaggiaTrenoStation


def normalize_station_name(name: str) -> str:
    """Normalize station name for reliable cross-API comparison."""
    decomposed = unicodedata.normalize("NFD", name)
    no_accents = "".join(
        ch for ch in decomposed if unicodedata.category(ch) != "Mn"
    )
    upper = no_accents.upper()
    upper = upper.replace("’", "'").replace("`", "'")
    upper = re.sub(r"\s+", " ", upper).strip()
    return upper


def _strip_punctuation(name: str) -> str:
    return re.sub(r"[^A-Z0-9 ]+", "", normalize_station_name(name)).strip()


def match_lefrecce_to_viaggiatreno(
    lf_station: LeFrecceStation,
    vt_candidates: list[ViaggiaTrenoStation],
) -> StationMatchResult:
    """Match a LeFrecce station against ViaggiaTreno autocomplete candidates."""
    if not vt_candidates:
        return StationMatchResult(
            matched=None,
            candidates=[],
            confident=False,
            reason="no_candidates",
        )

    target_norm = normalize_station_name(lf_station.name)
    target_alpha = _strip_punctuation(lf_station.name)

    # 1. Exact normalized name match (handles Torino Porta Susa -> S00035,
    #    Roma Balduina -> S08327, Cirie' -> S00090).
    exact_matches = [
        cand
        for cand in vt_candidates
        if normalize_station_name(cand.name) == target_norm
    ]
    if len(exact_matches) == 1:
        return StationMatchResult(
            matched=exact_matches[0],
            candidates=vt_candidates,
            confident=True,
            reason="exact_normalized_name",
        )

    # 2. Alphanumeric normalized match (ignoring apostrophes/hyphens/dots).
    alpha_matches = [
        cand
        for cand in vt_candidates
        if _strip_punctuation(cand.name) == target_alpha
    ]
    if len(alpha_matches) == 1:
        return StationMatchResult(
            matched=alpha_matches[0],
            candidates=vt_candidates,
            confident=True,
            reason="exact_alpha_name",
        )

    # 3. Fallback: S + last 5 digits of LeFrecce ID present in VT candidates
    #    (handles Reggio Emilia Av 830005254 -> REGGIO EMILIA AV MEDIOPADANA S05254).
    lf_id_str = str(lf_station.id)
    if len(lf_id_str) >= 5:
        expected_vt_id = f"S{lf_id_str[-5:]}"
        id_matches = [
            cand for cand in vt_candidates if cand.vt_id == expected_vt_id
        ]
        if len(id_matches) == 1:
            return StationMatchResult(
                matched=id_matches[0],
                candidates=vt_candidates,
                confident=True,
                reason="suffix_id_fallback",
            )

    # 4. Single candidate returned for a specific query -> probable, ask confirmation.
    if len(vt_candidates) == 1:
        return StationMatchResult(
            matched=vt_candidates[0],
            candidates=vt_candidates,
            confident=False,
            reason="single_candidate_unverified",
        )

    return StationMatchResult(
        matched=None,
        candidates=vt_candidates,
        confident=False,
        reason="ambiguous",
    )


async def resolve_viaggiatreno_station(
    vt_client: ViaggiaTrenoClient,
    lf_station: LeFrecceStation,
) -> StationMatchResult:
    """Query ViaggiaTreno and resolve the matching station for a LeFrecce station."""
    queries = [lf_station.name]
    alpha_only = re.sub(r"[^A-Za-z0-9 ]+", " ", lf_station.name).strip()
    alpha_only = re.sub(r"\s+", " ", alpha_only)
    if alpha_only and alpha_only != lf_station.name:
        queries.append(alpha_only)

    tokens = alpha_only.split()
    if len(tokens) >= 2:
        queries.append(" ".join(tokens[:2]))

    seen_ids: set[str] = set()
    all_candidates: list[ViaggiaTrenoStation] = []

    for q in queries:
        candidates = await vt_client.autocomplete_station(q)
        for cand in candidates:
            if cand.vt_id not in seen_ids:
                seen_ids.add(cand.vt_id)
                all_candidates.append(cand)
        result = match_lefrecce_to_viaggiatreno(lf_station, all_candidates)
        if result.confident:
            return result

    return match_lefrecce_to_viaggiatreno(lf_station, all_candidates)
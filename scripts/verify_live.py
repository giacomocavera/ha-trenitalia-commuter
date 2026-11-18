"""Live end-to-end verification script against LeFrecce and ViaggiaTreno APIs."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from custom_components.trenitalia_commuter.api.lefrecce import LeFrecceClient
from custom_components.trenitalia_commuter.api.viaggiatreno import ViaggiaTrenoClient
from custom_components.trenitalia_commuter.const import ROME_TZ
from custom_components.trenitalia_commuter.matcher import resolve_viaggiatreno_station
from custom_components.trenitalia_commuter.merger import build_route_snapshot


async def run_check(
    origin_query: str,
    dest_query: str,
    *,
    no_changes: bool = True,
    regional_only: bool = False,
) -> None:
    now = datetime.now(ROME_TZ)
    print(f"\n=== LIVE CHECK ({now.strftime('%Y-%m-%d %H:%M:%S %Z')}) ===")
    print(f"Route: {origin_query} -> {dest_query} (no_changes={no_changes})")

    async with aiohttp.ClientSession() as session:
        lf = LeFrecceClient(session)
        vt = ViaggiaTrenoClient(session)

        orig_results = await lf.search_stations(origin_query)
        dest_results = await lf.search_stations(dest_query)
        if not orig_results or not dest_results:
            print("Station search returned no results.")
            return

        orig_lf = orig_results[0]
        dest_lf = dest_results[0]
        print(f"LeFrecce Origin: {orig_lf.name} (id={orig_lf.id})")
        print(f"LeFrecce Dest:   {dest_lf.name} (id={dest_lf.id})")

        orig_match = await resolve_viaggiatreno_station(vt, orig_lf)
        dest_match = await resolve_viaggiatreno_station(vt, dest_lf)
        print(
            f"VT Origin Match: {orig_match.matched} "
            f"(confident={orig_match.confident}, reason={orig_match.reason})"
        )
        print(
            f"VT Dest Match:   {dest_match.matched} "
            f"(confident={dest_match.confident}, reason={dest_match.reason})"
        )

        if orig_match.matched is None:
            print("Cannot proceed without ViaggiaTreno origin ID.")
            return

        solutions = await lf.get_solutions(
            orig_lf.id,
            dest_lf.id,
            now - timedelta(minutes=45),
            no_changes=no_changes,
            regional_only=regional_only,
            limit=15,
        )
        departures = await vt.get_departures(orig_match.matched.vt_id, now)
        print(
            f"Fetched {len(solutions)} LeFrecce solutions, "
            f"{len(departures)} VT departures."
        )

        snapshot = await build_route_snapshot(
            solutions,
            departures,
            vt_client=vt,
            user_origin_vt_id=orig_match.matched.vt_id,
            user_dest_vt_id=dest_match.matched.vt_id if dest_match.matched else None,
            now=now,
            max_trains=8,
            delay_threshold=5,
        )

        print(f"\nFallback andamentoTreno calls: {snapshot.fallback_calls}")
        print(
            f"Disruption: {snapshot.disruption} ({snapshot.disruption_reason}) "
            f"affected={snapshot.affected_trains}"
        )
        if snapshot.next_train:
            nt = snapshot.next_train
            print(
                f"NEXT TRAIN SENSOR: {nt.category} {nt.train_number} | "
                f"sched={nt.scheduled_departure.strftime('%H:%M')} -> "
                f"exp={nt.expected_departure.strftime('%H:%M')} (+{nt.delay}m) | "
                f"plat={nt.platform or '--'} (confirmed={nt.platform_confirmed}) | "
                f"status={nt.status}"
            )
        else:
            print("NEXT TRAIN SENSOR: None (no upcoming trains)")

        print("\nUpcoming trains:")
        for t in snapshot.trains:
            print(
                f"  - {t.scheduled_departure.strftime('%H:%M')} "
                f"{t.category:6s} {t.train_number:6s} -> {t.destination:24s} | "
                f"delay=+{t.delay:<2d}m | plat={str(t.platform or '--'):4s} | "
                f"status={t.status} | changes={t.changes}"
            )


async def main() -> None:
    if len(sys.argv) >= 3:
        await run_check(sys.argv[1], sys.argv[2])
    else:
        await run_check("Settimo", "Torino Porta Susa")
        await run_check("Torino Porta Susa", "Settimo")


if __name__ == "__main__":
    asyncio.run(main())
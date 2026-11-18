# Trenitalia Commuter for Home Assistant

[![HACS Validation](https://github.com/giacomocavera/ha-trenitalia-commuter/actions/workflows/validate.yml/badge.svg)](https://github.com/giacomocavera/ha-trenitalia-commuter/actions/workflows/validate.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/giacomocavera/ha-trenitalia-commuter)](https://github.com/giacomocavera/ha-trenitalia-commuter/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Home Assistant custom integration for Italian train commuters. It tracks any direct or connecting route across Italy (Trenitalia, Trenord, SFM, Frecciarossa, EuroCity), providing live departure schedules, delays, assigned platforms, and disruption status.

---

## Features

- **Universal Italian Coverage:** Works for any station pair in Italy (e.g., *Settimo ↔ Torino Porta Susa*, *Milano ↔ Roma*, *Roma Balduina ↔ Roma Ostiense*).
- **Hybrid API Architecture:**
  - Uses **LeFrecce API** to discover actual journey solutions, intermediate stops, and operational codes (`bdoOrigin`).
  - Uses **ViaggiaTreno API** for real-time delays, live platform tracking (scheduled vs actual), and cancellation detection.
- **Smart Disambiguation:** Resolves LeFrecce station IDs to ViaggiaTreno codes automatically, with fallbacks for station naming differences (e.g., *Torino Porta Susa*, *Reggio Emilia AV Mediopadana*).
- **Low-impact 2-Speed Polling:**
  - Long-term schedule cache (LeFrecce, every 20 minutes by default).
  - Fast live departure board refresh (ViaggiaTreno, every 2 minutes or disabled for on-demand automations).
- **Entities Provided per Route:**
  - `sensor.<route>_next_train` (Timestamp of the next operating train with full `trains` upcoming list in attributes)
  - `sensor.<route>_delay` (Live delay in minutes)
  - `sensor.<route>_platform` (Live or scheduled platform, supporting roman numerals)
  - `sensor.<route>_next_train_status` (Human-readable summary, e.g., `SFM2 26266 • 12:38 (+2m) • P.1`)
  - `binary_sensor.<route>_disruption` (Turns `on` when delay exceeds threshold or trains are cancelled)
  - `sensor.<route>_last_sync` (Diagnostic timestamp and API health)

---

## Screenshots

![Trenitalia Commuter Dashboard](https://github.com/user-attachments/assets/b5d59adb-fd2f-4de4-a6f8-8963d5179c73)

---

## Installation

### Via HACS (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed.
2. In Home Assistant, open **HACS** > **Integrations**.
3. Click the three dots in the top right corner > **Custom repositories**.
4. Enter `https://github.com/giacomocavera/ha-trenitalia-commuter` and select category **Integration**.
5. Click **Download**, then restart Home Assistant.

### Manual Installation

1. Download the latest release from the [Releases](https://github.com/giacomocavera/ha-trenitalia-commuter/releases) page.
2. Copy the `custom_components/trenitalia_commuter` folder into your Home Assistant `<config>/custom_components/` directory.
3. Restart Home Assistant.

---

## Configuration

1. In Home Assistant, navigate to **Settings** > **Devices & Services**.
2. Click **Add Integration** and search for **Trenitalia Commuter**.
3. Follow the guided setup:
   - Search and select your **Origin station**.
   - Search and select your **Destination station**.
   - Set route preferences (Direct trains only, Regional only, Delay threshold, Route name).
4. You can configure multiple routes independently (e.g., one for *Home → Work* and another for *Work → Home*).

### Options

After setup, click **Configure** on the integration card to adjust:
- Polling intervals (ViaggiaTreno live polling, LeFrecce schedule refresh).
- Lookback window for delayed past departures.
- Disruption delay threshold.

---

## Automation Example

Send a mobile notification when your morning train is delayed or cancelled:

```yaml
alias: "Alert: Morning Train Delay"
trigger:
  - platform: state
    entity_id: binary_sensor.settimo_torino_porta_susa_disagio
    to: "on"
condition:
  - condition: time
    after: "07:00:00"
    before: "09:00:00"
action:
  - action: notify.notify
    data:
      title: "Train Alert!"
      message: "{{ states('sensor.settimo_torino_porta_susa_stato_prossimo_treno') }}"
```

---

## Disclaimer

This integration is an independent open-source project and is not affiliated with, endorsed by, or connected to Trenitalia S.p.A. or Ferrovie dello Stato Italiane.
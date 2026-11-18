# Trenitalia Commuter per Home Assistant

[![HACS Validation](https://github.com/giacomocavera/ha-trenitalia-commuter/actions/workflows/validate.yml/badge.svg)](https://github.com/giacomocavera/ha-trenitalia-commuter/actions/workflows/validate.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/giacomocavera/ha-trenitalia-commuter)](https://github.com/giacomocavera/ha-trenitalia-commuter/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Un'integrazione personalizzata per Home Assistant dedicata ai pendolari ferroviari italiani. Monitora qualsiasi tratta diretta o con cambi in tutta Italia (Trenitalia, Trenord, SFM, Frecciarossa, EuroCity), fornendo orari di partenza in tempo reale, ritardi, binari assegnati e stato dei disagi.

---

## Funzionalità

* **Copertura Italiana Universale:** Funziona per qualsiasi coppia di stazioni in Italia (es. *Settimo ↔ Torino Porta Susa*, *Milano ↔ Roma*, *Roma Balduina ↔ Roma Ostiense*).
* **Architettura API Ibrida:**
  * Utilizza le **API LeFrecce** per rilevare le soluzioni di viaggio effettive, le fermate intermedie e i codici operativi (`bdoOrigin`).
  * Utilizza le **API ViaggiaTreno** per i ritardi in tempo reale, il tracciamento live dei binari (previsto vs effettivo) e il rilevamento delle cancellazioni.
* **Disambiguazione Intelligente:** Risolve automaticamente gli ID delle stazioni LeFrecce nei codici ViaggiaTreno, con sistemi di fallback per le differenze nei nomi delle stazioni (es. *Torino Porta Susa*, *Reggio Emilia AV Mediopadana*).
* **Polling a 2 Velocità a Basso Impatto:**
  * Cache degli orari a lungo termine (LeFrecce, ogni 20 minuti per impostazione predefinita).
  * Aggiornamento rapido del tabellone delle partenze live (ViaggiaTreno, ogni 2 minuti oppure disabilitato per automazioni su richiesta).
* **Entità Fornite per Tratta:**
  * `sensor.<route>_next_train` (Timestamp del prossimo treno operativo con l'elenco completo `trains` dei prossimi treni negli attributi)
  * `sensor.<route>_delay` (Ritardo in tempo reale in minuti)
  * `sensor.<route>_platform` (Binario effettivo o previsto, con supporto per i numeri romani)
  * `sensor.<route>_next_train_status` (Riepilogo leggibile, es. `SFM2 26266 • 12:38 (+2m) • P.1`)
  * `binary_sensor.<route>_disruption` (Si attiva su `on` quando il ritardo supera la soglia impostata o i treni vengono cancellati)
  * `sensor.<route>_last_sync` (Timestamp diagnostico e stato di salute delle API)

---

## Screenshot

![Dashboard Trenitalia Commuter](https://github.com/user-attachments/assets/b5d59adb-fd2f-4de4-a6f8-8963d5179c73)

---

## Installazione

### Tramite HACS (Consigliato)

1. Assicurati che [HACS](https://hacs.xyz/) sia installato.
2. In Home Assistant, apri **HACS** > **Integrazioni**.
3. Clicca sui tre puntini in alto a destra > **Repository personalizzati**.
4. Inserisci `https://github.com/giacomocavera/ha-trenitalia-commuter` e seleziona la categoria **Integrazione**.
5. Clicca su **Scarica**, quindi riavvia Home Assistant.

### Installazione Manuale

1. Scarica l'ultima versione dalla pagina delle [Releases](https://github.com/giacomocavera/ha-trenitalia-commuter/releases).
2. Copia la cartella `custom_components/trenitalia_commuter` nella directory `<config>/custom_components/` del tuo Home Assistant.
3. Riavvia Home Assistant.

---

## Configurazione

1. In Home Assistant, vai su **Impostazioni** > **Dispositivi e servizi**.
2. Clicca su **Aggiungi integrazione** e cerca **Trenitalia Commuter**.
3. Segui la configurazione guidata:
   * Cerca e seleziona la tua **Stazione di partenza**.
   * Cerca e seleziona la tua **Stazione di destinazione**.
   * Imposta le preferenze della tratta (Solo treni diretti, Solo regionali, Soglia di ritardo, Nome della tratta).
4. Puoi configurare più tratte in modo indipendente (es. una per *Casa → Lavoro* e un'altra per *Lavoro → Casa*).

### Opzioni

Dopo la configurazione, clicca su **Configura** nella scheda dell'integrazione per regolare:

* Intervalli di polling (polling live di ViaggiaTreno, aggiornamento orari di LeFrecce).
* Finestra temporale retrospettiva (lookback) per le partenze passate in ritardo.
* Soglia di ritardo per la segnalazione dei disagi.

---

## Esempio di Automazione

Invia una notifica sul telefono quando il tuo treno del mattino è in ritardo o cancellato:

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

Questa integrazione è un progetto open-source indipendente e non è affiliata, approvata o collegata a Trenitalia S.p.A. o a Ferrovie dello Stato Italiane.
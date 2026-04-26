# ha-herold — Projekt-Kontext für Claude

## Was ist das

Home Assistant Custom Component — Ziel: zentrale Meldungs-Vermittlung mit **Rollen-Routing (Pub/Sub + RBAC)**.

**Status (2026-04-26):** Live im Produktivsystem seit 2026-04-17. MVP komplett, plus User-Override-Layer (Producer-Defaults vs. User-Overrides getrennt) und mobile_app silent-reject Catcher. 13 Services, 9 Sensoren, 2 Custom Cards. GitHub: https://github.com/cnc-lasercraft/ha-herold

Siehe `README.md`, `docs/PROBLEM.md`, `docs/ARCHITECTURE.md`, `docs/OPEN_QUESTIONS.md`.

## Nachbar-Projekte

- **HA-Produktivsystem:** `/Volumes/Daten/ClaudeCode/home-assistant/` — Ziel-Installation, 2026.4.x HAOS, ~5400 Entities. `CLAUDE.md` dort hat den HA-Kontext (Namenskonventionen, Integrationen, Arbeitsregeln).
- **HA-Quirks:** `/Volumes/Daten/ClaudeCode/ha_quirks.md` — zentrale Wissensbasis für HA-Eigenheiten. Beim Arbeiten an Herold relevanter HA-Spezifika dort nachschlagen und neue Erkenntnisse nachtragen.

## Arbeitsregeln (übernommen vom HA-Projekt)

- **Deutsch** als primäre Sprache (Code-Kommentare, Docs, UI-Labels). Englische Bezeichner nur wo technisch sinnvoll (API-Namen, Standard-Begriffe).
- **Vor Änderungen fragen** — keine unbesprochenen Architektur-Entscheidungen.
- **Root Cause fixen** — keine Workarounds.
- **Wiederholbare Muster als Blueprint anbieten.**
- **HA NIE** über Docker/Proxmox neustarten (wenn wir später im Produktivsystem testen) — `ha_restart` MCP-Tool oder HA UI.

## Namens-Konvention

- **Repo/Verzeichnis:** `ha-herold`
- **Integrations-Domain:** `herold` (→ `custom_components/herold/`, Service-Calls `herold.*`)

## Aktueller Stand

Live, MVP + Override-Layer. Producer-Defaults (am `Topic`-Modell) vs. User-Overrides (separater `topic_overrides`-Speicher + `topic_rolle_mapping`) sauber getrennt — Producer-Reregistrierung überschreibt User-Edits nicht mehr. Lese-Pfad geht über `HeroldConfigStore.effective_*()`. Aktive Producer: wallbox/ladeplanung, zeekr, ekz_tariff, tariff_saver. Soak-Phase im Alltag. v2-Themen (Regeln-Engine, Lifecycle/Ack, weitere Empfänger-Typen) auf der Bank.

## Kontext aus Gründungs-Session (Chat davor)

Diskussion entstand aus dem konkreten Schmerz: `notify.mobile_app_iphone_17_ul` ist überall hart verdrahtet. User will bei Handy-Wechsel / neuem Gerät **eine Stelle anfassen**, nicht hundert Automationen. Erste Kandidaten (Script-Hub, `notify.person`, Alert2, Universal Notifier) evaluiert — keiner bietet **Topic-Registrierung durch Producer + Rollen-Mapping** in Kombination. Daher Eigenbau gerechtfertigt.

Namens-Findung: `hermes` kollidiert mit Rhasspy-Voice-Protokoll, `relay` semantisch mit Hardware-Relais. `herold` gewählt — semantisch frei, Metapher präzise (Bote/Ausrufer).

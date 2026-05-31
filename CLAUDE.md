# ha-herold — Projekt-Kontext für Claude

## Was ist das

Home Assistant Custom Component — Ziel: zentrale Meldungs-Vermittlung mit **Rollen-Routing (Pub/Sub + RBAC)**.

**Status (2026-05-31):** Live im Produktivsystem seit 2026-04-17. MVP komplett, plus User-Override-Layer, mobile_app silent-reject Catcher, **4-Schichten-Push-Resilienz** (Sanity-Check für `payload.data.data`, Retry ohne Payload bei warnung/kritisch, `persistent_notification`-Notbremse bei Total-Ausfall kritischer Meldungen) und **Empfänger-Typ `tts`** (Sprachausgabe via `tts.speak`, mit `media_player` als Komma-Liste für Multi-Lautsprecher-Ansagen). 13 Services, 9 Sensoren, 2 Custom Cards. GitHub: https://github.com/cnc-lasercraft/ha-herold

**Soak-Bilanz (6 Wochen, Stand 2026-05-31):** Code seit 2026-04-29 eingefroren, reiner Produktivbetrieb. **0 Exceptions** im HA-Log über die gesamte Periode. Gewachsen von ~5 auf **73 aktive Topics** / ~258 Meldungen pro Tag (1.809/Woche). Resilienz arbeitet messbar im Alltag: Fallback-Routing feuert (unzugeordnete Topics → `techn_support`), Sanity-Check entschachtelt laufend kaputte `payload.data.data`-Producer-Payloads. Herold ist damit faktisch der zentrale Meldungs-Bus des Hauses — breiter als ursprünglich dokumentiert.

Siehe `README.md`, `docs/PROBLEM.md`, `docs/ARCHITECTURE.md`, `docs/OPEN_QUESTIONS.md`.

## Nachbar-Projekte

- **HA-Produktivsystem:** Ziel-Installation, 2026.5.x HAOS, ~5400 Entities. Lokaler Ordner `/Volumes/Daten/ClaudeCode/home-assistant/` ist nur ein Teil-Abzug — die **echte Config liegt auf dem Host** (`ssh has`, `/config` → Symlink auf `/homeassistant`; Datei-Edits brauchen `sudo`, Owner root). `CLAUDE.md` dort hat den HA-Kontext (Namenskonventionen, Integrationen, Arbeitsregeln).
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

Live, MVP + Override-Layer. Producer-Defaults (am `Topic`-Modell) vs. User-Overrides (separater `topic_overrides`-Speicher + `topic_rolle_mapping`) sauber getrennt — Producer-Reregistrierung überschreibt User-Edits nicht mehr. Lese-Pfad geht über `HeroldConfigStore.effective_*()`. **Aktive Producer (Stand 2026-05-31, 73 Topics):** pool, wallbox/ladeplanung, zeekr, ekz_tariff, tariff_saver — plus seit Doku-Stand dazugekommen: miele/watchdog, huawei_solar, wasser/leck_alarm, haus/verlassen, garage, klingel, nfc/*, anwesenheit, batterie, licht, einkauf, alarm. **Producer-Log-View-Konvention** etabliert (2026-04-26): jeder Producer hat eine eigene Lovelace-View in seinem Dashboard, gefiltert via `lock_filters` + `topic`-Prefix der `herold-log-card` (v5: Sortier-Header, Sev-Cycle, Datalist-Fix). **4-Schichten-Push-Resilienz** (2026-04-28): Sanity-Check fängt `payload.data.data`-Falle automatisch, severity-gated Retry ohne Payload bei silent-reject, `persistent_notification`-Notbremse bei Total-Ausfall kritischer Meldungen. **Empfänger-Typ `tts`** (2026-04-29): Sprachausgabe via `tts.speak` mit `target.entity_id`, `media_player` als Komma-Liste für Multi-Lautsprecher (alle 6 Voice-Lautsprecher als Sammel-Empfänger `voice_haus` plus 6 raum-spezifische Empfänger angelegt). Rezept zum Nachbauen in `docs/PRODUCER_GUIDE.md` Schritt 6. **Recorder-Exclude (2026-05-31):** die 5 Listen-/Config-Sensoren (`topic_mapping`, `aktive_topics`, `unzugeordnete_topics`, `empfanger`, `einstellungen`) tragen große Attribute → `topic_mapping` sprengte mit 73 Topics die 16-KB-Recorder-Grenze. Gefixt via `recorder: exclude.entities` in der HA-`configuration.yaml` (greift beim nächsten Neustart). Verhältnismäßig, weil die Sensoren quasi statisch sind — der WS-Command-Refactor aus `ha_quirks.md` ist hier nicht nötig. uniali als nächster Producer-Kandidat (Anbindung steht aus). Soak-Phase im Alltag. **Offene Producer-Schulden:** (1) diverse Producer schreiben weiter `payload.data.data` (Resilienz fängt's, Cleanup steht aus); (2) `tariff_saver/boiler/uebertemperatur` ist `kritisch`, hat aber leere Rollen → nur Fallback statt gezielt. v2-Themen (Regeln-Engine, Lifecycle/Ack, weitere Empfänger-Typen) auf der Bank.

## Kontext aus Gründungs-Session (Chat davor)

Diskussion entstand aus dem konkreten Schmerz: `notify.mobile_app_iphone_17_ul` ist überall hart verdrahtet. User will bei Handy-Wechsel / neuem Gerät **eine Stelle anfassen**, nicht hundert Automationen. Erste Kandidaten (Script-Hub, `notify.person`, Alert2, Universal Notifier) evaluiert — keiner bietet **Topic-Registrierung durch Producer + Rollen-Mapping** in Kombination. Daher Eigenbau gerechtfertigt.

Namens-Findung: `hermes` kollidiert mit Rhasspy-Voice-Protokoll, `relay` semantisch mit Hardware-Relais. `herold` gewählt — semantisch frei, Metapher präzise (Bote/Ausrufer).

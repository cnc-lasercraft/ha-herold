# ha-herold

[![Validate](https://github.com/cnc-lasercraft/ha-herold/actions/workflows/validate.yml/badge.svg)](https://github.com/cnc-lasercraft/ha-herold/actions/workflows/validate.yml)
[![Release](https://img.shields.io/github/v/release/cnc-lasercraft/ha-herold)](https://github.com/cnc-lasercraft/ha-herold/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Home Assistant Custom Component — **zentrale Meldungs-Vermittlung mit Rollen-Routing**.

**Status:** Produktiv seit 2026-04-17, seit 2026-04-29 im eingefrorenen Code-Stand. Sechs Wochen Soak ohne eine einzige Exception, **73 aktive Topics**, rund 258 Meldungen pro Tag. Herold ist im Betreiber-Haushalt faktisch der zentrale Meldungs-Bus: Pool, Wallbox/Ladeplanung, Zeekr, EKZ-Tarif, Tarif-Saver, Miele-Watchdog, Huawei-Solar, Leck-Alarm, Garage, Klingel, NFC, Anwesenheit, Batterie, Licht, Einkauf, Alarm.

## Idee in einem Satz

Eine HA-Integration, bei der Producer (Automationen, Scripts, andere CCs) **Meldungstypen** anmelden, Admin diese Typen auf **Rollen** ("Techn. Support", "Erwachsener", "Familie", …) mappt, und Geräte (iPhones, Walldisplays, TTS, Mail, …) Mitglieder von Rollen sind. Bei Handy-Wechsel oder neuem Empfänger wird **eine Stelle** angefasst — nicht hundert Automationen. **Alle Meldungen werden zentral protokolliert** (History mit Filter, Abfrage-Service, Logbook-Integration).

## Features

- **Topics** mit Default-Severity, Default-Rollen und `log_only`-Flag (nur History, keine Zustellung — für gesprächige Producer ohne Spam-Risiko)
- **Rollen** mit Mitgliederliste; Admin-Override pro Topic (Topic-Rollen-Mapping) schlägt Producer-Default
- **Empfänger-Registry** mit zwei Typen: `notify_service` (beliebige `notify.*`-Dienste) und `tts` (Sprachausgabe via `tts.speak`, `media_player` als Komma-Liste für Multi-Lautsprecher-Ansagen)
- **`interruption_level`** (iOS) als Topic-Default oder Override pro Aufruf
- **4-Schichten-Push-Resilienz** — Sanity-Check gegen fehlerhafte `payload.data.data`-Payloads, Erkennung von `mobile_app`-silent-rejects, severity-gated Retry ohne Payload, `persistent_notification` als Notbremse
- **Fallback-Rolle** + Last-Resort `persistent_notification` bei fehlender Zuordnung
- **History** mit Filter-Abfrage (Topic-Prefix `pool/*`, Severity, Rolle, Zeitraum, Limit)
- **Täglicher Retention-Cleanup** um 03:00 (konfigurierbar)
- **Config-Flow + Options-Flow** (Topics, Rollen, Empfänger, Mapping, Einstellungen)
- **Admin-Custom-Card** (Tabs für alle Bereiche, Inline-Edit, Warn-Banner bei Inkonsistenzen)
- **Log-Custom-Card** (Filter, Textsuche, Severity-Farben, Live-Refresh)
- **Logbook-Integration** (alle Herold-Events formatiert)
- **9 Sensoren** für Dashboard-Nutzung (Topics-Liste, Rollen-Liste, Mapping-Übersicht, Zähler, …)
- **12 Services** inkl. Delete-Operationen für Scripting-Parität

## Installation

### HACS

1. HACS → Integrationen → Drei-Punkt-Menü → **Custom repositories**
2. `https://github.com/cnc-lasercraft/ha-herold`, Kategorie **Integration**
3. „Herold" herunterladen, **Home Assistant neu starten**
4. Einstellungen → Geräte & Dienste → **Integration hinzufügen** → „Herold"

### Manuell

1. `custom_components/herold/` nach `<config>/custom_components/` kopieren
2. HA neu starten
3. `herold:` (leer) in `configuration.yaml` hinzufügen **oder** via Einstellungen → Geräte & Dienste → Integration hinzufügen → „Herold"

### Dashboard-Setup

Die beiden Custom Cards liefert die Integration selbst aus (serviert unter `/herold/…`, automatisch ins Frontend geladen). **Es müssen keine Dateien nach `<config>/www/` kopiert und keine Lovelace-Ressourcen registriert werden.** Cards einfach in einem Dashboard einbinden:

```yaml
views:
  - title: Herold-Verwaltung
    type: panel
    cards:
      - type: custom:herold-admin-card

  - title: Herold-Log
    type: panel
    cards:
      - type: custom:herold-log-card
        limit: 200   # Optional, Default 200
```

Die Admin-Card erwartet keine `entity`-Parameter — sie liest aus `sensor.herold_*` direkt.

> **Update von einer Version vor 1.0.0:** Bisher mussten die Karten von Hand nach `<config>/www/` kopiert und als Ressource eingetragen werden. Beides nach dem Update entfernen — die Karten kommen jetzt aus der Integration.

## Services (Kurzübersicht)

| Service | Zweck |
|---|---|
| `herold.senden` | Meldung auf ein Topic senden (Hauptaufruf) |
| `herold.topic_registrieren` | Topic mit Defaults anlegen/aktualisieren |
| `herold.topic_entfernen` | Topic löschen |
| `herold.rolle_setzen` | Rolle + Mitglieder setzen |
| `herold.rolle_entfernen` | Rolle löschen (bereinigt Topics/Mapping/Fallback) |
| `herold.empfaenger_setzen` | Empfänger anlegen/aktualisieren |
| `herold.empfaenger_entfernen` | Empfänger löschen (bereinigt Rollen) |
| `herold.topic_rolle_mapping` | Admin-Override für Topic → Rollen |
| `herold.topic_override_setzen` | User-Override für Topic-Felder (schlägt Producer-Default) |
| `herold.einstellungen_setzen` | Fallback-Rolle, Retention-Grenzen |
| `herold.history_abfragen` | Meldungs-History gefiltert abrufen |
| `herold.history_aufraeumen` | Manueller Retention-Cleanup |

## REST-API (lesend)

Für Oberflächen ausserhalb von Home Assistant. Alle Endpunkte verlangen ein
HA-Token (`Authorization: Bearer …`) und sind rein lesend — geschrieben wird
weiterhin ausschliesslich über die `herold.*`-Services, damit ein externer
Client Fernbedienung bleibt und nie zweite Wahrheit wird.

| Endpunkt | Inhalt |
|---|---|
| `GET /api/herold/config` | Topics, Rollen, Empfänger, Einstellungen in einem Roundtrip |
| `GET /api/herold/topics` | Topics; Filter `?unzugeordnet=1`, `?override=1`, `?praefix=pool/` |
| `GET /api/herold/topics/<id>` | Einzelnes Topic (ID darf Slashes enthalten) |
| `GET /api/herold/rollen` | Rollen inkl. Mitglieder und Anzahl adressierter Topics |
| `GET /api/herold/empfaenger` | Empfänger inkl. Typ, Ziel und zugehöriger Rollen |
| `GET /api/herold/einstellungen` | Fallback-Rolle, Retention, Kennzahlen |
| `GET /api/herold/history` | Log; Filter `topic`, `severity`, `rolle`, `von`/`bis`, `seit`, `zugestellt`, `limit` |

Jedes Topic trägt beide Konfigurationsebenen **und** den Effektivwert im selben
Objekt — Konsumenten müssen Producer-Default und User-Override nicht selbst
zusammenführen:

```json
{
  "id": "pool/tank_leer_notaus",
  "rollen":     { "producer_default": ["techn_support"], "override": null,  "wirksam": ["techn_support"] },
  "log_only":   { "producer_default": false, "override": null, "wirksam": false },
  "hat_override": false,
  "unzugeordnet": false,
  "wirksam": { "rollen": ["techn_support"], "log_only": false,
               "interruption_level": "critical", "default_severity": "kritisch" }
}
```

`GET /api/herold/history` liefert zusätzlich `cursor` (Zeitstempel des jüngsten
Eintrags). Wer ihn beim nächsten Aufruf als `?seit=` zurückgibt, bekommt nur
Neues — gedacht für pollende Clients.

## Warum nicht bestehende Lösungen

Siehe [`docs/ALTERNATIVES.md`](docs/ALTERNATIVES.md). Kurzfassung:
- **Alert2** löst Lifecycle/Ack/Severity, aber **kein Rollen-Modell**.
- **Universal Notifier** verwaltet Geräte/Kanäle, aber **keine Topic-Registrierung, kein Rollen-Mapping**.
- **`notify.person`** (eingebaut) hilft bei Handy-Wechsel, löst aber das Rollen-Routing nicht.

Die Lücke: **Pub/Sub + RBAC** für Notifications. Gibt's in HA-Community soweit recherchiert nicht.

## Dokumente

- [Problem & Motivation](docs/PROBLEM.md) — was genau ist das Problem, konkrete Beispiele.
- [Architektur](docs/ARCHITECTURE.md) — Domain-Modell, Services, Resolution-Flow.
- [Alternativen](docs/ALTERNATIVES.md) — existierende HA-Lösungen und warum sie nicht reichen.
- [Design-Entscheidungen](docs/OPEN_QUESTIONS.md) — die 10 MVP-Design-Fragen mit Begründungen.
- [Producer-Guide](docs/PRODUCER_GUIDE.md) — Anleitung für CCs, die Herold als Notification-Broker nutzen wollen.

## Name

- **Repo / lokales Verzeichnis:** `ha-herold` (HA-Community-Konvention)
- **Integrations-Domain / Python-Package:** `herold`
- **Service-Calls:** `herold.senden`, `herold.topic_registrieren`, `herold.rolle_setzen`, …

Der Name "Herold" = Bote/Ausrufer: nimmt Meldungen entgegen, ruft sie gezielt an die zuständigen Rollen/Personen aus. `hermes` ist durch das Rhasspy/Snips-Voice-Protokoll belegt, `relay` in HA mit Schaltrelais. `herold` ist frei und metaphorisch passend.

## Zielsystem & Kompatibilität

- Entwickelt und im Dauerbetrieb erprobt auf **HA 2026.4/2026.5** (HAOS, Python 3.14)
- Mindestversion **HA 2024.11** (`OptionsFlow`-API ohne gesetzte `config_entry`-Property)
- Python 3.12+

## Lizenz

MIT — siehe [`LICENSE`](LICENSE).

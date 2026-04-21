# ha-herold

Home Assistant Custom Component — **zentrale Meldungs-Vermittlung mit Rollen-Routing**.

**Status:** Live seit 2026-04-17. Config-Flow, Admin-Custom-Card und Log-Custom-Card produktiv. Erste Producer (Wallbox-Ladeplanung, Zeekr-CC) senden.

## Idee in einem Satz

Eine HA-Integration, bei der Producer (Automationen, Scripts, andere CCs) **Meldungstypen** anmelden, Admin diese Typen auf **Rollen** ("Techn. Support", "Erwachsener", "Familie", …) mappt, und Geräte (iPhones, Walldisplays, TTS, Mail, …) Mitglieder von Rollen sind. Bei Handy-Wechsel oder neuem Empfänger wird **eine Stelle** angefasst — nicht hundert Automationen. **Alle Meldungen werden zentral protokolliert** (History mit Filter, Abfrage-Service, Logbook-Integration).

## Features

- **Topics** mit Default-Severity, Default-Rollen und `log_only`-Flag (nur History, keine Zustellung — für gesprächige Producer ohne Spam-Risiko)
- **Rollen** mit Mitgliederliste; Admin-Override pro Topic (Topic-Rollen-Mapping) schlägt Producer-Default
- **Empfänger-Registry** (aktuell `notify_service`, erweiterbar)
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

### Manuell

1. `custom_components/herold/` nach `<config>/custom_components/` kopieren
2. Custom Cards nach `<config>/www/` kopieren:
   - `custom_components/herold/www/herold-admin-card.js`
   - `custom_components/herold/www/herold-log-card.js`
3. `herold:` (leer) in `configuration.yaml` hinzufügen **oder** via Settings → Geräte & Dienste → Integration hinzufügen → "Herold"
4. HA neu starten

### Dashboard-Setup

Zuerst die zwei JS-Ressourcen registrieren (Settings → Dashboards → Drei-Punkt-Menü → Resources, oder YAML-Mode):

```yaml
resources:
  - url: /local/herold-admin-card.js
    type: module
  - url: /local/herold-log-card.js
    type: module
```

Dann Cards in einem Dashboard/View einbinden:

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
| `herold.einstellungen_setzen` | Fallback-Rolle, Retention-Grenzen |
| `herold.history_abfragen` | Meldungs-History gefiltert abrufen |
| `herold.history_aufraeumen` | Manueller Retention-Cleanup |

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

- Entwickelt und getestet auf **HA 2026.4** (HAOS, Python 3.14)
- Benötigt HA mit `OptionsFlow`-API ab 2024.11 (siehe `ha_quirks.md` zu `config_entry`-Property)
- Python 3.12+

## Lizenz

MIT — siehe `LICENSE` (folgt).

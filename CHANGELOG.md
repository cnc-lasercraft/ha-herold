# Changelog

Alle nennenswerten Änderungen an diesem Projekt.
Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung nach [Semantic Versioning](https://semver.org/lang/de/).

## [1.0.0] — 2026-08-29

Erster öffentlicher Release. Der Code läuft seit dem 2026-04-17 im
Produktivsystem des Autors; die Version 1.0.0 bildet den seit 2026-04-29
eingefrorenen, im Alltag erprobten Stand ab (6 Wochen Soak ohne eine einzige
Exception, 73 aktive Topics, rund 258 Meldungen pro Tag).

### Hinzugefügt

- **Topic-Registrierung durch Producer** — Automationen, Scripts und andere
  Custom Components melden Meldungstypen mit Default-Severity, Default-Rollen
  und `log_only`-Flag an (`herold.topic_registrieren`).
- **Rollen-Routing (Pub/Sub + RBAC)** — Topics werden auf Rollen gemappt,
  Rollen haben Empfänger als Mitglieder. Bei Gerätewechsel wird eine Stelle
  angefasst statt hundert Automationen.
- **User-Override-Layer** — Producer-Defaults am Topic-Modell und
  Admin-Overrides (`topic_overrides`, `topic_rolle_mapping`) sind sauber
  getrennt; eine Re-Registrierung durch den Producer überschreibt manuelle
  Anpassungen nicht mehr.
- **Empfänger-Typ `notify_service`** — Zustellung an beliebige `notify.*`-Dienste,
  inklusive `interruption_level` (iOS) als Topic-Default oder Aufruf-Override.
- **Empfänger-Typ `tts`** — Sprachausgabe via `tts.speak`; `media_player` als
  Komma-Liste erlaubt Multi-Lautsprecher-Ansagen, `tts_message` einen vom
  Meldungstext abweichenden Sprechtext.
- **4-Schichten-Push-Resilienz** — Sanity-Check entschachtelt fehlerhafte
  `payload.data.data`-Producer-Payloads, silent-rejects von `mobile_app` werden
  als Fehler erkannt, severity-gated Retry ohne Payload bei warnung/kritisch,
  `persistent_notification` als Notbremse bei Total-Ausfall kritischer Meldungen.
- **Fallback-Routing** — unzugeordnete Topics gehen an eine konfigurierbare
  Fallback-Rolle statt verloren.
- **History** mit gefilterter Abfrage (Topic-Prefix, Severity, Rolle, Zeitraum,
  Limit), täglichem Retention-Cleanup um 03:00 und manuellem Aufräum-Service.
- **Config-Flow und Options-Flow** für Topics, Rollen, Empfänger, Mapping und
  Einstellungen.
- **Admin-Custom-Card** und **Log-Custom-Card** (Filter, Textsuche,
  Severity-Farben, Sortier-Header, Live-Refresh) — werden ab dieser Version von
  der Integration selbst ausgeliefert.
- **Logbook-Integration** — alle Herold-Events erscheinen formatiert im Logbuch.
- **9 Sensoren** für Dashboards und **12 Services** inklusive Delete-Operationen
  für vollständige Scripting-Parität.

### Hinweise zur Installation

- Die Custom Cards werden jetzt aus dem Integrations-Verzeichnis serviert
  (`/herold/…`) und automatisch ins Frontend geladen. Wer sie bisher manuell
  nach `<config>/www/` kopiert und als Lovelace-Ressource registriert hat, kann
  beides nach dem Update entfernen — die alte Kopie würde die Karte sonst ein
  zweites Mal definieren.

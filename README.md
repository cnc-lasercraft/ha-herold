# ha-herold

Home Assistant Custom Component — **zentrale Meldungs-Vermittlung mit Rollen-Routing**.

**Status:** Design-Entscheidungen getroffen (2026-04-16), MVP-Skelett folgt. Noch kein Code.

## Idee in einem Satz

Eine HA-Integration, bei der Producer (Automationen, Scripts, andere CCs) **Meldungstypen** anmelden, Admin diese Typen auf **Rollen** ("Techn. Support", "Erwachsener", "Familie", …) mappt, und Geräte (iPhones, Walldisplays, TTS, Mail, …) Mitglieder von Rollen sind. Bei Handy-Wechsel oder neuem Empfänger wird **eine Stelle** angefasst — nicht hundert Automationen. **Alle Meldungen werden zentral protokolliert** (History mit Filter, Abfrage-Service, Logbook-Integration).

## Warum nicht bestehende Lösungen

Siehe [`docs/ALTERNATIVES.md`](docs/ALTERNATIVES.md). Kurzfassung:
- **Alert2** löst Lifecycle/Ack/Severity, aber **kein Rollen-Modell**.
- **Universal Notifier** verwaltet Geräte/Kanäle, aber **keine Topic-Registrierung, kein Rollen-Mapping**.
- **`notify.person`** (eingebaut) hilft bei Handy-Wechsel, löst aber das Rollen-Routing nicht.

Die Lücke: **Pub/Sub + RBAC** für Notifications. Das gibt es in HA-Community soweit recherchiert **nicht**.

## Dokumente

- [Problem & Motivation](docs/PROBLEM.md) — was genau ist das Problem, konkrete Beispiele.
- [Architektur](docs/ARCHITECTURE.md) — Domain-Modell, Services, Resolution-Flow.
- [Alternativen](docs/ALTERNATIVES.md) — existierende HA-Lösungen und warum sie nicht reichen.
- [Design-Entscheidungen](docs/OPEN_QUESTIONS.md) — die 10 MVP-Design-Fragen mit getroffenen Entscheidungen und Begründungen.
- [Producer-Guide](docs/PRODUCER_GUIDE.md) — Anleitung für CCs, die Herold als Notification-Broker nutzen wollen.

## Zielsystem

Projekt läuft im Haushalt des Autors:
- HA 2026.4.x (HAOS auf Proxmox), ~5400 Entities, Schweiz
- Details zum HA-Setup siehe `/Volumes/Daten/ClaudeCode/home-assistant/CLAUDE.md`
- HA-Spezialitäten (Quirks) siehe `/Volumes/Daten/ClaudeCode/ha_quirks.md`

## Name

- **Repo / lokales Verzeichnis:** `ha-herold` (HA-Community-Konvention)
- **Integrations-Domain / Python-Package:** `herold`
- **Service-Calls:** `herold.senden`, `herold.topic_registrieren`, `herold.rolle_setzen`, …

Der Name "Herold" = Bote/Ausrufer: nimmt Meldungen entgegen, ruft sie gezielt an die zuständigen Rollen/Personen aus. Name-Kollisions-Check: `hermes` ist durch das Rhasspy/Snips-Voice-Protokoll semantisch vorbelegt, `relay` in HA mit Schaltrelais. `herold` ist frei (GitHub/HACS/Forum) und metaphorisch passend.

## Status & nächste Schritte

1. ✅ Design-Entscheidungen getroffen (2026-04-16, siehe `docs/OPEN_QUESTIONS.md`).
2. **Jetzt:** Skelett `custom_components/herold/` anlegen (manifest, `__init__`, `const`, `services.yaml`), Storage-Gerüst, Basis-Services `senden` + `topic_registrieren` + `history_abfragen`.
3. Danach: Config Flow (Empfänger / Rollen / Topics / Einstellungen), Sensoren, Logbook-Integration.
4. Danach: Pilot-Einsatz mit der neuen Pool-CC als erstem Producer.
5. Danach: schrittweise Migration bestehender HA-Notifications.

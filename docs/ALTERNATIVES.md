# Alternativen — was es in HA-Welt schon gibt

Recherche-Stand: April 2026.

## 1. `notify.person_urs` (HA Core, eingebaut)

Jede `person` in HA kennt die zugeordneten Mobile-App-Devices. Call an `notify.person_urs` geht an alle Geräte dieser Person.

- ✅ Offizieller Weg, kostet nichts.
- ✅ Handy-Wechsel = in Person-Config Gerät austauschen, Automationen unverändert.
- ❌ **Keine Topic-Registrierung** — jede Automation ruft direkt auf, Kontext fehlt.
- ❌ **Keine Rollen** — nur "eine Person". Keine Gruppenlogik wie "alle Erwachsenen".
- ❌ Keine Severity, keine Tageszeit-/Presence-Regeln.

**Verdikt:** Baustein — löst einen Teil (Device-Aliasing pro Person), aber nicht das Rollen-Problem.

## 2. Notify-Gruppen (`notify: platform: group`)

Mehrere Notify-Targets zu einem bündeln, z.B. `notify.familie = [urs, partner, kind]`.

- ✅ Einfach, YAML, schnell.
- ❌ Nur YAML-Config (nicht UI).
- ❌ Statisch, keine Regeln.
- ❌ Kein Topic-Konzept.

**Verdikt:** Hilft beim Bündeln, ersetzt aber kein Routing-System.

## 3. [Alert2](https://github.com/redstone99/hass-alert2)

HACS-Integration, Fokus **Alerting mit Lifecycle**.

**Kann:**
- Event-/Condition-basierte Alerts
- Severity (low/medium/high)
- Acknowledge / Unack / Reminder bis quittiert
- Snooze, Throttle, Supersede
- Template-basierte Notifier-Wahl
- Eigene UI-Cards (Overview, Manager)
- Events auf Bus (`alert2_alert_fire`, `alert2_alert_ack`, …)
- YAML + UI Config

**Kann nicht (für unseren Use Case):**
- ❌ **Kein Rollen-Modell** — Empfänger werden pro Alert (oder per Template) gewählt, nicht rollenbasiert.
- ❌ Kein Topic-Registrierungs-API für Producer.
- Zielgeräte sind am Alert verdrahtet (oder im Default); bei neuem Handy muss mindestens der Default angefasst werden.

**Verdikt:** Löst **Lifecycle/Ack/Severity** — orthogonal zu Herold. Kann später als Downstream kombiniert werden (Herold ruft Alert2 für einzelne Topics).

- 56 Stars, aktiv (v1.19.5), MIT, HACS-installierbar.

## 4. [Universal Notifier](https://github.com/jumping2000/universal_notifier)

HACS-Integration, Fokus **Ausgabe-Routing & TTS-Management**.

**Kann:**
- Single Service `universal_notifier.send`
- Mehrere Kanäle gebündelt (Telegram, Mobile, Alexa, Google Home, …)
- Config Flow (UI), keine YAML nötig
- DND / Quiet Hours mit Critical-Bypass (`priority: true`)
- Zeit-Slots mit Volume-Regelung für TTS
- Presence-basierte Auslieferung
- FIFO-Queue für Audio-Ausgaben

**Kann nicht (für unseren Use Case):**
- ❌ **Kein Severity-System** — nur Binärflag `priority: true`.
- ❌ **Kein Acknowledge/Lifecycle**, keine History.
- ❌ **Kein Topic-Registrierungs-API**.
- ❌ **Kein echtes Rollen-Modell** — Config Flow kennt Kanäle/Targets/Presence, aber keine funktionalen Gruppen über Topics hinweg.

**Verdikt:** Sehr gute **Ausspiel-Schicht** (TTS-Volume, DND). Kann als nachgelagerter Kanal unter Herold laufen ("Herold routet zu Rolle X, die hat UN als Ausspiel-Empfänger").

- 192 Stars, aktiv (v0.7.1), HACS.

## 5. Built-in `alert:` Integration

Die ursprüngliche HA-Alert-Integration, auf der Alert2 aufsetzt. YAML-only, reduzierter Funktionsumfang, kein Severity. Für unseren Scope irrelevant.

## 6. Weitere gesichtete Projekte

- **Ticker** — "Smart Notification Management", kein Rollen-Fokus.
- **[Notification Center Hub](https://github.com/3vasi0n89/Home-Assistant-Notification-Center-Hub)** — zentralisiert TTS + Device Notifications, aber ohne Topic/Rollen-Konzept.
- **[HA-NotifyHelper](https://github.com/kukuxx/HA-NotifyHelper)** — Notification-Helfer, primär UI-fokussiert.

## Fazit

Keine der gesichteten Lösungen implementiert **Pub/Sub (Topic-Registrierung durch Producer) + RBAC (Rollen-Mapping)** in Kombination. Die existierenden Lösungen adressieren jeweils **eine** Dimension:

- **Alert2** → Lifecycle
- **Universal Notifier** → Ausgabe-Kanäle & TTS-Kontext
- **`notify.person`** → Device-Aliasing

**Herold füllt die Lücke** als Routing-/Registry-Schicht, kann die anderen downstream nutzen.

# Problem & Motivation

## Ausgangslage

Im HA-Setup sind Notifications über dutzende Stellen verteilt (Automationen, Scripts, Custom Components). Das **Empfänger-Gerät ist überall hart verdrahtet**, typischerweise `notify.mobile_app_iphone_17_ul`.

## Die Schmerzpunkte

1. **Handy-Wechsel** → an jeder Stelle Entity-ID anpassen.
2. **Zweites / drittes Gerät** (Partner, Kind, Gast-Handy) → Notifications müssen überall zusätzlich eingebaut werden.
3. **Kontext-Logik fehlt** — "das ist eine technische Warnung, die geht an mich als Admin" vs. "das geht an alle Erwachsenen" ist heute nur via copy-paste-if-else in jeder Automation abbildbar.
4. **Neue Producer** (z.B. eine neu installierte CC, ein neues Script) wissen nicht, *wem* sie was schicken sollen — sie picken sich ein notify-Target aus der Vergangenheit und verdrahten es hart.

## Was der User wirklich will

Eine zentrale Registry in Form einer CC, bei der sich Producer **anmelden** und **Meldungstypen registrieren** (eine CC kann 1, 3 oder 25 Typen haben). Diese Typen werden administrativ auf **funktionale Rollen / Personengruppen** gemappt — Beispiele:

- `Techn. Support`
- `Erwachsener`
- `Familie`
- `Hauseigentümer`
- `Gärtner` / Gäste
- `Alle`

Auf der Empfänger-Seite werden physische **Geräte / Kanäle** diesen Rollen zugeordnet. Mein iPhone 17 ist z.B. Mitglied von `Techn. Support` **und** `Erwachsener` **und** `Hauseigentümer`. Ein Kind-Handy ist nur Mitglied von `Familie`.

## Was das löst

- **Handy-Wechsel**: Das neue Gerät wird den Rollen zugeordnet, bestehende Zuordnung abgehängt. Nichts an Automationen ändern.
- **Neuer Empfänger** (Partner kommt dazu): Gerät zu den passenden Rollen hinzufügen, fertig.
- **Kontext-Logik** lebt an einer Stelle (im Mapping Topic → Rollen), nicht verstreut in Automationen.
- **Neue Producer** registrieren ihre Topics beim Startup, Admin entscheidet **einmal**, wer diese Topics bekommt.

## Analogie

Das Muster ist **RBAC für Notifications** — wie PagerDuty: Services → Escalation Policies → Users. Oder klassisches **Pub/Sub**: Producer publiziert, Broker entscheidet nach Regeln, Consumer bekommt.

## Nicht-Ziele (bewusst erstmal weggelassen)

- **Lifecycle/Ack/Reminder** (wie Alert2): interessant, aber orthogonal. Kann später via Alert2-Bridge oder eigenes Modul ergänzt werden.
- **TTS-Volume / Quiet Hours / Begrüssungen** (wie Universal Notifier): auch orthogonal. Kann als Downstream-Kanal genutzt werden (Herold → UN).
- **Eigene Messenger-Implementierungen**: Herold nutzt bestehende `notify.*` Services. Kein Selber-Senden via Telegram/SMS/etc.

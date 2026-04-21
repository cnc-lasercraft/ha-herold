# Design-Entscheidungen

**Status:** Alle 10 MVP-Design-Fragen entschieden am **2026-04-16**.

Dieses Dokument ist der **Contract** für den MVP. Jede Sektion zeigt die getroffene Entscheidung, kurz die Begründung und die erwogenen Alternativen als Rückblick. Wenn eine Entscheidung revidiert wird, hier aktualisieren — nicht in Code oder anderen Docs "nebenher" ändern.

---

## 1. Topic-Registrierung

**→ Hybrid (C) + idempotent-mit-Update.**

`senden()` akzeptiert jedes Topic — unbekannte Topics entstehen automatisch beim ersten Call und landen auf der Liste "unzugeordnet". `topic_registrieren()` ist optional; wird es gerufen, liefert es reiche Metadaten (Beschreibung, Default-Severity, Default-Rollen, Quelle). Mehrfacher Aufruf **aktualisiert** die Metadaten (idempotent mit Update), so kann ein Producer seine Beschreibung ändern, ohne dass der Admin im UI nachzieht.

**Begründung:** Niedrige Hürde für Producer, aber sauberer Pfad zur Reife. Update-Semantik vermeidet UI/Code-Divergenz.

<details><summary>Erwogene Alternativen</summary>

- **A (explizit, Pflicht):** Saubere API, aber Boilerplate für jede Automation (Startup-Trigger).
- **B (rein implizit):** Null Hürde, aber Topics bleiben ohne Metadaten bis zur manuellen Pflege.
</details>

---

## 2. Fallback für unzugeordnete Topics

**→ Konfigurierbare Fallback-Rolle + `persistent_notification` als Last-Resort.**

Im Config Flow ist eine Rolle als "Fallback-Rolle" markiert (Default: erste angelegte Rolle, typischerweise `techn_support`). Sendet ein Producer ein Topic, dem keine Rolle zugewiesen ist:

1. Zustellung erfolgt an die Fallback-Rolle.
2. Der Log-Eintrag und das `herold_sent`-Event tragen `fallback_verwendet: true`.
3. Das Topic erscheint auf `sensor.herold_unzugeordnete_topics` (Attribut-Liste).
4. **Last-Resort:** Ist die Fallback-Rolle leer (keine Mitglieder), wird `persistent_notification.create` aufgerufen — die Meldung verschwindet nie komplett.

**Begründung:** Garantierte Zustellbarkeit + Sichtbarkeit für Admin.

<details><summary>Erwogene Alternativen</summary>

- **Droppen mit Warn-Log:** Risiko, dass wichtige Meldungen unbemerkt verloren gehen.
- **Hardcoded Admin-Rolle:** Weniger flexibel; manche Setups haben keinen dedizierten `techn_support`.
</details>

---

## 3. Rollen-Hierarchien

**→ Flach. Keine Hierarchien im MVP.**

Rollen sind unabhängige Mengen von Empfängern. Ein Empfänger kann Mitglied **mehrerer** Rollen sein. Der Resolver dedupliziert Empfänger im Schritt "Rollen auflösen → Empfänger-Union bilden" — 90 % des Hierarchie-Nutzens gratis, ohne die UI-/Zyklen-Komplexität.

<details><summary>Erwogene Alternativen</summary>

- **Hierarchisch (Rolle enthält Rolle):** Eleganter bei komplexen Setups, aber UI muss Zyklen verhindern, Resolution wird rekursiv, Debugging härter. v2 erwägen, wenn echter Bedarf auftritt.
</details>

---

## 4. Severity × Rolle — Routing-Matrix?

**→ Nur Topic → Rollen. Severity ist Metadatum, kein Routing-Kriterium.**

Severity (`info` / `warnung` / `kritisch`) reist als Metadatum mit, wird geloggt, landet im `herold_sent`-Event und kann vom Empfänger ausgewertet werden (siehe Frage 6). Sie beeinflusst aber **nicht**, wer benachrichtigt wird. Wer heute schon severity-abhängiges Routing braucht, nutzt zwei Topics (`wasserleck_test`, `wasserleck_echt`).

**Begründung:** MVP bleibt einfach und vorhersagbar. Die Regel-Matrix (Topic × Severity × Zeit × Presence → Rollen) kommt als v2.

---

## 5. Zeit- / Presence-Filter

**→ Producer entscheidet. Keine eingebaute Filter-Logik im MVP.**

Wenn eine Automation nachts nicht an alle senden soll, hat sie ohnehin einen `condition:`-Block. Herold filtert nichts und bleibt damit vorhersagbar: kommt eine Meldung nicht an, ist klar — der Producer hat nicht gesendet.

**Begründung:** Root Cause in der Automation, nicht durch mehrere Filter-Ebenen verschleiert.

<details><summary>Erwogene Alternativen</summary>

- **Rollen-Ebene** (`erwachsen_anwesend` = dynamisch gefilterte Rolle): führt zu Rollen-Inflation.
- **Regel-Ebene** (Regel hat `zeit_filter`/`presence_filter`): flexibel, aber koppelt MVP an Regel-Matrix. v2 gemeinsam mit Frage 4.
</details>

---

## 6. Kanal-Varianz pro Empfänger × Severity

**→ Am Empfänger.**

Jeder Empfänger definiert ein `severity_payload`-Mapping (`info` / `warnung` / `kritisch` → Payload-Override). Das iPhone weiss, wie es auf `kritisch` mit einem Critical-Alert reagiert; ein Walldisplay hat ein eigenes Mapping; ein E-Mail-Notify-Target lässt das Feld leer.

Kein "Default-Payload pro Empfänger-Typ" im MVP — jeder Empfänger pflegt sein eigenes Mapping. Bei Bedarf später "Presets".

**Begründung:** Saubere Trennung — Topic sagt *was*, Empfänger weiss *wie* es sein Device anspricht. Passt zum Pub/Sub-Gedanken: Producer weiss nichts über Devices.

---

## 7. Logging / History

**→ HA-Storage, 30 Tage / 2000 Einträge, Service + Sensoren + Logbook + Event, alles inkl. Fehler.**

| Aspekt | Entscheidung |
|---|---|
| **Speicherformat** | `.storage/herold_history` via `homeassistant.helpers.storage.Store` (strukturiertes JSON). |
| **Retention** | Default **30 Tage** oder **2000 Einträge** — ob das zuerst greift. Im Config Flow änderbar. |
| **Cleanup** | Täglicher Task (z.B. 03:00) via `async_track_time_change`. |
| **Abfrage-Service** | `herold.history_abfragen` (Response-Service ab HA 2024.8): `topic?`, `severity?`, `rolle?`, `zeitraum_von?`, `zeitraum_bis?`, `limit?` → Liste. |
| **Sensoren** | `sensor.herold_letzte_meldung`, `_meldungen_heute`, `_meldungen_7_tage`, `_unzugeordnete_topics`, `_aktive_topics`. |
| **Logbook** | Jeder Send erzeugt `logbook.log`-Eintrag (Filter "herold" im HA-Logbook). |
| **Event-Bus** | `herold_sent` fire auf jeden Send — externe Consumer (Node-RED, InfluxDB, eigene Dashboards) möglich. |
| **Inhalt** | Alle Einträge werden protokolliert, **auch Fehler und Skipped** (pro Empfänger: `ok` / `fehler:<grund>` / `skipped:<grund>`). |
| **Privacy-Redigierung** | v2 — kein MVP. |

**Logging ist automatisch:** `herold.senden` schreibt synchron in History + Event + Logbook. Producer müssen nichts extra tun. `herold.history_abfragen` ist reiner **Lese**-Service.

---

## 8. MVP-Scope

**→ Erster echter Einsatz: neue Pool-CC als Pilot-Producer.**

### Drin (MVP)

- Topics: Hybrid (implizit + optional registrieren, idempotent).
- Rollen: flach, Mehrfach-Mitgliedschaft.
- Empfänger-Typ: **nur `notify_service`** (deckt `notify.*` komplett ab — iPhone, E-Mail-Notify, etc.).
- Fallback-Rolle + `persistent_notification` Last-Resort.
- Services: `herold.senden`, `herold.topic_registrieren`, `herold.rolle_setzen`, `herold.history_abfragen`.
- Config Flow: Tabs *Empfänger / Rollen / Topics / Topic-Rolle-Mapping / Einstellungen* (Fallback-Rolle, Retention).
- Storage: `.storage/herold` (Config), `.storage/herold_history` (Log).
- Severity als Metadatum, Payload-Override pro Empfänger × Severity.
- Entities: `sensor.herold_letzte_meldung`, `_meldungen_heute`, `_meldungen_7_tage`, `_unzugeordnete_topics`, `_aktive_topics`.
- Events: `herold_sent`, `herold_topic_registered`, `herold_delivery_failed`.
- Logbook-Integration.
- Beispiel-Dashboard-YAML (Copy-Paste für Lovelace).

### Draussen (v2+)

- Regel-Matrix (Severity × Zeit × Presence → Rollen).
- Zeit-/Presence-Filter in Herold selbst.
- Empfänger-Typen: TTS, Browser-Mod, Walldisplay-spezifisch, Webhook, direktes E-Mail.
- Acknowledge / Lifecycle (Alert2-Bridge).
- Eigene Lovelace-Card.
- Rollen-Hierarchien.
- Privacy-Redigierung nach N Tagen.
- Migration-Blueprint für bestehende Automationen.

---

## 9. Topic-Namensschema

**→ Slash-Hierarchie, Sprache frei, Regex `^[a-z0-9_/]+$`, ungültige Topics werden abgelehnt.**

- Format: `<bereich>/<was>[/<detail>]`, z.B. `pool/ph/niedrig`, `wasser/leck/waschkueche`, `backup/fehler`.
- Validierung: `^[a-z0-9_/]+$` — Kleinbuchstaben, Ziffern, Unterstrich, Slash. Umlaute via Transkription (`waschkueche` statt `waschküche`, HA-Konvention).
- Ungültige Topics: `herold.senden` wirft `ServiceValidationError` mit klarer Meldung. **Keine Normalisierung** — macht Debugging härter.
- **UI:** Config Flow zeigt Topics als Baum (Split an `/`). Laufzeit behandelt sie als String — keine semantische Hierarchie, nur Anzeige-Gruppierung.
- Sprache: frei wählbar, empfohlen konsistent mit dem sonstigen HA-Setup (deutsch in diesem Haushalt).

---

## 10. Dashboard-Card

**→ Keine eigene Card im MVP. Standard-Entities + Logbook-Card + Beispiel-YAML.**

HA-Boardmittel reichen: die 4 Herold-Sensoren in einer Entities-Card plus eine Logbook-Card gefiltert auf `herold`. Ein Beispiel-Dashboard-YAML wird in `examples/dashboard.yaml` mitgeliefert (Copy-Paste in Lovelace).

**Begründung:** Eine Custom-Card ist ein eigenes Projekt (Lit/TS, Build, HACS-Frontend-Release). Zu viel Overhead für MVP. Wenn echter Bedarf entsteht (Timeline mit Severity-Farbcodierung, Filterchips), kann sie später als separates Repo entstehen — Kopplung ans Backend ist minimal (nur Service-API + Event-Bus).

# Architektur

**Status:** MVP live seit 2026-04-17, alle geplanten Features (Config-Flow, Admin-Card, Retention-Cleanup, `log_only`) implementiert. Grund-Design siehe [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md), Abweichungen/Erweiterungen sind unten in den betroffenen Abschnitten markiert.

## Kernmuster

**Pub/Sub + RBAC**

```
[Producer]  --senden(topic, ...)-->  [Herold-Broker]  --(auflösen via Mapping)-->  [Geräte/Kanäle]
```

## Domain-Modell

### Topic (Meldungstyp)
Eine von einem Producer registrierte Meldungsart.

| Feld | Typ | Beschreibung |
|---|---|---|
| `id` | string | z.B. `wasserleck`, `garage_offen`, `pv_ueberschuss`, `backup_fehler` |
| `name` | string | Anzeigename für UI |
| `beschreibung` | string | Was bedeutet diese Meldung, wann feuert sie |
| `quelle` | string | Name des Producers (z.B. `script.gute_nacht`, `custom_components.ekz_tariff`) |
| `default_severity` | enum `info` / `warnung` / `kritisch` | Vorschlag, kann pro `senden()` überschrieben werden |
| `default_rollen` | list\<Rolle\> | Wer bekommt's standardmässig (Vorschlag, admin kann überstimmen) |
| `log_only` | bool | Wenn `true`: `senden()` schreibt nur History + Event, **keine** Zustellung (auch kein Last-Resort). Für gesprächige Producer. |
| `explizit_registriert` | bool | `false` = implizit beim ersten `senden()` angelegt, `true` = via `topic_registrieren` |

### Rolle (funktionale Gruppe)
Vom Admin definiert, unabhängig von Topics und Geräten.

| Feld | Typ | Beschreibung |
|---|---|---|
| `id` | string | z.B. `techn_support`, `erwachsener`, `familie`, `hauseigentuemer` |
| `name` | string | Anzeigename |
| `mitglieder` | list\<Empfänger\> | siehe nächste Tabelle |

### Empfänger (physisches Ziel)
Ein konkreter Ausspielkanal.

| Feld | Typ | Beschreibung |
|---|---|---|
| `id` | string | eindeutig im Registry |
| `typ` | enum | **MVP: nur `notify_service`.** v2+: `tts` / `persistent_notification` / `walldisplay` / `email` / `webhook` / … |
| `ziel` | string | z.B. `notify.mobile_app_iphone_17_ul` |
| `name` | string | für UI |
| `severity_payload` | dict | optionaler Payload-Override pro Severity (`info` / `warnung` / `kritisch`). Jeder Empfänger entscheidet selbst, wie er auf Severity reagiert (siehe Beispiel unten). |

**Beispiel `severity_payload` für ein iPhone:**

```yaml
severity_payload:
  info: {}                              # leer = nur titel/message
  warnung:
    data:
      push:
        interruption-level: time-sensitive
  kritisch:
    data:
      push:
        interruption-level: critical
        sound:
          critical: 1
          name: default
          volume: 1.0
```

### Regel (Routing-Override) — **v2, nicht im MVP**

Feinere Zuordnung als nur Topic→Default-Rollen. Im MVP nutzen wir ausschliesslich Topic→Rollen; Severity ist Metadatum (kein Routing-Kriterium), Zeit/Presence macht der Producer selbst via `condition:`.

| Feld | Typ | Beschreibung |
|---|---|---|
| `topic_id` | string | |
| `severity_filter` | list\<severity\> | Regel greift nur bei diesen Stufen |
| `rollen` | list\<Rolle\> | wer bei Treffer benachrichtigt wird |
| `zeit_filter` | optional | z.B. "22–07 Uhr" |
| `presence_filter` | optional | z.B. "nur an anwesende Personen" |

## Resolution-Flow (Laufzeit)

```
1. Automation/Script/CC ruft Service:
     herold.senden(topic="wasser/leck/waschkueche", titel="Leck Waschküche",
                   message="...", severity="kritisch", actions=[...])

2. Topic-ID validieren (Regex ^[a-z0-9_/]+$).
   → Ungültig? ServiceValidationError, nichts wird gesendet oder geloggt.

3. Herold schlägt Topic im Registry nach.
   → Unbekannt: Topic wird automatisch angelegt (implizit, explizit_registriert=false).
   → Bekannt ohne Rollen-Zuordnung: Fallback-Rolle greift (fallback_verwendet=true).

4. **log_only-Short-Circuit:** Ist topic.log_only gesetzt,
   überspringe Schritte 5+6 komplett. ausliefer_status = {"log_only": "skipped"},
   aufgeloste_rollen = [], aufgeloste_empfaenger = []. Weiter bei Schritt 7.

5. Rollen-Menge bestimmen:
   - Admin-Mapping (topic_rolle_mapping) hat Vorrang vor topic.default_rollen.
   - Plus senden(..., extra_rollen=[...]).
   - Leer + keine Fallback-Rolle → Last-Resort persistent_notification (siehe 6).

6. Rollen → Empfänger auflösen + Zustellung:
   - Jede Rolle → ihre Mitglieder, Empfänger-Union deduplizieren.
   - Keine Empfänger? Last-Resort persistent_notification.create (fallback_verwendet=true).
   - Pro Empfänger: severity_payload-Override mergen, notify.<ziel> aufrufen.

7. Nebenwirkungen (synchron im selben senden()-Call):
   - Event herold_sent auf EventBus firen.
   - Logbook-Eintrag (via logbook.py async_describe_events).
   - Persistente History-Zeile (.storage/herold_history).
```

## Services (öffentliche API)

### `herold.topic_registrieren`
Idempotent **mit Update**: existiert das Topic bereits, werden die übergebenen Felder aktualisiert (nicht-übergebene bleiben unverändert). Producer ruft beim Startup oder bei Bedarf auf.

```yaml
data:
  topic: "wasser/leck/waschkueche"                  # required, Regex ^[a-z0-9_/]+$
  name: "Wasserleck Waschküche"
  beschreibung: "Leckage-Sensor unter der Waschmaschine hat ausgelöst"
  quelle: "automation.wasserleck_waschkuche"
  default_severity: "kritisch"
  default_rollen: ["techn_support", "erwachsener"]   # optional; default []
  log_only: false                                    # optional; default false
```

### `herold.senden`
Haupt-Aufruf aus Automationen/Scripts.

```yaml
data:
  topic: "wasser/leck/waschkueche"   # required, Regex ^[a-z0-9_/]+$
  titel: "Leck Waschküche"           # required
  message: "Wasser-Sensor unter Waschmaschine"
  severity: "kritisch"               # optional, überschreibt default
  actions:                           # optional, HA Actionable Notification Format
    - action: "WASSER_ABSTELLEN"
      title: "Hauptventil zu"
  extra_rollen: []                   # optional, ad-hoc zusätzlich zu default_rollen
  payload: {}                        # optional, passthrough (Bilder, Sound, …)
                                     # wird mit severity_payload des Empfängers gemerged
```

### `herold.rolle_setzen`
Admin-Operation. Auch via UI Config Flow.

```yaml
data:
  rolle: "techn_support"
  mitglieder:
    - "iphone_17_ul"
    - "admin_pc_mail"
```

### `herold.history_abfragen`
Lese-Service (Response-Service ab HA 2024.8). Gibt Liste der passenden History-Einträge zurück.

```yaml
data:
  topic: "pool/ph/niedrig"     # optional, Prefix-Match erlaubt (z.B. "pool/*")
  severity: "kritisch"          # optional
  rolle: "erwachsener"          # optional (filtert auf aufgelöste_rollen)
  zeitraum_von: "2026-04-01T00:00:00+02:00"  # optional
  zeitraum_bis: "2026-04-16T23:59:59+02:00"  # optional
  limit: 100                    # optional, default 100
```

### `herold.topic_entfernen` / `rolle_entfernen` / `empfaenger_entfernen`
Löschen der jeweiligen Entität. Bereinigen konsistent:
- `topic_entfernen`: löscht auch `topic_rolle_mapping`-Eintrag
- `rolle_entfernen`: entfernt Rolle aus allen `topic.default_rollen`, aus allen `topic_rolle_mapping`-Einträgen, setzt `fallback_rolle=None` wenn betroffen
- `empfaenger_entfernen`: entfernt ID aus allen `rolle.mitglieder`

### `herold.topic_rolle_mapping`
Admin-Override für Topic → Rollen (schlägt Producer-Default).

```yaml
data:
  topic: "pool/ph/niedrig"
  rollen: ["techn_support"]         # optional; leer + zuruecksetzen=false löscht Override
  zuruecksetzen: false               # optional; true entfernt Override explizit
```

### `herold.einstellungen_setzen`
Fallback-Rolle und Retention-Grenzen zur Laufzeit anpassen.

```yaml
data:
  fallback_rolle: "techn_support"    # optional; null = keine Fallback-Rolle
  retention_eintraege: 2000           # optional
  retention_tage: 30                  # optional
```

### `herold.history_aufraeumen`
Manuelles Cleanup. Ohne Parameter = Config-Defaults.

```yaml
data:
  max_eintraege: 1000   # optional; überschreibt Config
  max_tage: 14          # optional; überschreibt Config
```

### `herold.quittieren` — **v3, nicht im MVP**
Wenn Lifecycle später dazukommt oder via Alert2-Bridge.

## Persistenz

- **Config** (Topics, Rollen, Empfänger, Einstellungen): `.storage/herold` via `homeassistant.helpers.storage.Store`.
- **History**: `.storage/herold_history` — getrennte Datei, eigene Store-Instanz, damit Config klein und Backup-freundlich bleibt.
- Backup/Restore kompatibel mit HA-Bordmitteln.

## Entities

| Sensor | State | Attribute | Quell-Event |
|---|---|---|---|
| `sensor.herold_letzte_meldung` | Topic-ID | voller letzter Eintrag | `herold_sent` |
| `sensor.herold_meldungen_heute` | Zähler (Mitternacht UTC) | — | `herold_sent` |
| `sensor.herold_meldungen_7_tage` | Zähler (rollierend) | — | `herold_sent` |
| `sensor.herold_aktive_topics` | Anzahl | `topics[]` mit id/name/severity/`log_only`/explizit | `herold_topic_registered`, `herold_sent` |
| `sensor.herold_unzugeordnete_topics` | Anzahl | `topics[]`, **ohne log_only-Topics** | `herold_topic_registered`, `herold_sent` |
| `sensor.herold_rollen` | Anzahl | `rollen[]` mit mitglieder + ist_fallback | `herold_config_updated` |
| `sensor.herold_empfanger` *)| Anzahl | `empfaenger[]` + welche Rollen | `herold_config_updated` |
| `sensor.herold_topic_mapping` | Anzahl Overrides | `mapping[]` mit producer_default/override/wirksam | `herold_config_updated` |
| `sensor.herold_einstellungen` | Fallback-Rolle-ID | `fallback_rolle`, `retention_eintraege`, `retention_tage` | `herold_config_updated` |

*) Entity-ID ohne `ä` — HA's Slugify macht `Empfänger` → `empfanger`.

Keine Attribut-Listen der "letzten N Einträge" auf einem Sensor — HA-Attribute-Limit (~16 kB) kollidiert mit langen Messages. Für Listen → `herold.history_abfragen` oder Log-Card.

## Events (auf HA Event Bus)

| Event | Payload | Ausgelöst durch |
|---|---|---|
| `herold_sent` | topic, severity, aufgeloste_rollen, aufgeloste_empfaenger, ausliefer_status, fallback_verwendet, eintrag_id, zeitstempel | jeder `senden()`-Call |
| `herold_delivery_failed` | topic, empfaenger, fehler | Einzel-Empfänger-Fehler (zusätzlich zu `herold_sent`) |
| `herold_topic_registered` | topic, status (`neu` / `update` / `implizit` / `entfernt`) | `topic_registrieren`, `topic_entfernen`, implizite Anlage |
| `herold_history_cleaned` | ausloeser (`scheduler`/`service`), entfernt, restliche, max_eintraege, max_tage | Tägliches Cleanup + `history_aufraeumen` |
| `herold_config_updated` | typ (`config`/`options_flow`) | Jede Config-Änderung (Rollen/Empfänger/Mapping/Einstellungen) |

Alle Events sind im Logbook formatiert (siehe `logbook.py`).

## Zentrales Log / History

**First-class Feature.** Jede Meldung wird persistent protokolliert.

### Datenmodell eines Log-Eintrags

| Feld | Beschreibung |
|---|---|
| `id` | eindeutig, z.B. ULID |
| `zeitstempel` | wann kam `senden()` an |
| `topic` | |
| `severity` | |
| `titel`, `message` | wie gesendet |
| `quelle_context` | HA-Context (user_id, parent_id) — nachvollziehbar, welche Automation/Script ausgelöst hat |
| `aufgelöste_rollen` | Liste der Rollen nach Resolution |
| `aufgelöste_empfänger` | Liste der konkreten Devices/Kanäle |
| `ausliefer_status` | pro Empfänger: `ok` / `fehler:<grund>` / `skipped:<grund>` |
| `actions` | ggf. mitgesendete Action-Buttons |
| `payload` | Passthrough-Daten |

### Speicherung

- **Primär:** eigene HA-Storage-Datei `.storage/herold_history` (rolling, JSON-Lines oder strukturiert).
- **Sekundär:** jede Meldung auch als `logbook.log`-Eintrag (damit im HA-Logbook mit Filter auf "herold" sichtbar).
- **Event-Bus:** zusätzlich `herold_sent` firen — externe Consumer (z.B. InfluxDB, Node-RED, eigene Dashboards) können abonnieren.

### Retention

Konfigurierbar im Config Flow (Einstellungen-Tab) oder via `herold.einstellungen_setzen`, **Defaults:**
- Max. Einträge: **2000**
- Max. Alter: **30 Tage**
- Es greift, was zuerst zutrifft (FIFO bei Einträgen, Zeit-Cleanup).
- Auto-Cleanup einmal täglich um **03:00** via `async_track_time_change`.
- Manueller Trigger: `herold.history_aufraeumen` (optional mit Override).
- Feuert `herold_history_cleaned`-Event mit Zähler-Details.

### Zugriff

- **Service** `herold.history_abfragen` → Liste (siehe Services-Abschnitt oben).
- **Entities** für Dashboard-Ansicht (letzte, heute, 7d).
- **Custom Cards:** `herold-log-card` (Filter/Suche) und `herold-admin-card` (Verwaltung).
- **Logbook:** alle Herold-Events sind über `logbook.py` sauber formatiert.
- **Developer Tools → Events:** live mitlesen.

### Privacy / Datensparsamkeit

- `payload` und `message` können sensible Infos enthalten → Storage ist lokal (kein Cloud).
- **v2:** Config-Option, `message`-Inhalt im Log nach N Tagen redigieren, nur Metadaten behalten. Im MVP nicht implementiert.

## Konfiguration

**Zwei parallele Wege — beide voll funktional:**

### Config-Flow / Options-Flow (Settings → Geräte & Dienste → Herold → Konfigurieren)

5-Punkt-Menu:
1. **Topics** — Liste mit `log_only`-Flag, Anlegen/Bearbeiten/Löschen
2. **Rollen** — Liste mit Fallback-Badge, Mitglieder-Multi-Select
3. **Empfänger** — Typ/Ziel/Name
4. **Topic-Rollen-Zuordnung** (Admin-Override) — pro Topic die wirksamen Rollen überschreiben
5. **Einstellungen** — Fallback-Rolle, Retention

### Admin-Custom-Card (`herold-admin-card`, Lovelace)

Tab-basiertes Panel mit denselben 5 Bereichen in einer Übersicht:
- Tabellen-Ansicht aller Entitäten mit Quick-Actions
- Inline-Edit-Dialog (bleibt offen während State-Updates)
- Warn-Banner oben (Topics ohne Rollen, Rollen ohne Mitglieder, Empfänger ohne Rolle)
- Live-Refresh via `herold_config_updated`-Event
- Ruft direkt die herold.*-Services per WebSocket — keine Options-Flow-Dialoge

**v2:** zusätzlicher Bereich **Regeln** (Severity/Zeit/Presence-Overrides).

**Scripting-Parität:** Alle UI-Aktionen sind auch als Service verfügbar (`topic_registrieren`, `topic_entfernen`, `rolle_setzen`, `rolle_entfernen`, `empfaenger_setzen`, `empfaenger_entfernen`, `topic_rolle_mapping`, `einstellungen_setzen`).

## Getroffene Design-Entscheidungen

Siehe [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) — alle 10 MVP-Fragen sind entschieden.

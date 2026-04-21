# Architektur

**Status:** Design fixiert (2026-04-16). Alle MVP-Entscheidungen siehe [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md).

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
   → Unbekannt: Topic wird automatisch angelegt (implizit, siehe Q1), zur
     "unzugeordnet"-Liste hinzugefügt, fallback_verwendet=true gesetzt.
   → Bekannt ohne Rollen-Zuordnung: ebenfalls fallback_verwendet=true.

4. Rollen-Menge bestimmen:
   - MVP: topic.default_rollen + senden(..., extra_rollen=[...])
     + (falls fallback_verwendet) Fallback-Rolle aus Config.
   - v2: zusätzlich passende Regeln auswerten (severity/zeit/presence).

5. Rollen auflösen: Jede Rolle → ihre Mitglieder (Empfänger).
   → Empfänger-Union bilden und deduplizieren.
   → Leere Menge (Fallback-Rolle ist leer)? Last-Resort
     persistent_notification.create.

6. Pro Empfänger: severity_payload-Override des Empfängers mergen,
   dann Ausspiel-Mechanismus aufrufen (MVP: notify.<ziel>).

7. Nebenwirkungen (synchron im selben senden()-Call):
   - Event herold_sent auf EventBus firen
     (inkl. fallback_verwendet, aufgelöste_rollen, aufgelöste_empfänger,
      pro-Empfänger ausliefer_status).
   - Logbook-Eintrag.
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

### `herold.quittieren` — **v3, nicht im MVP**
Wenn Lifecycle später dazukommt oder via Alert2-Bridge.

## Persistenz

- **Config** (Topics, Rollen, Empfänger, Einstellungen): `.storage/herold` via `homeassistant.helpers.storage.Store`.
- **History**: `.storage/herold_history` — getrennte Datei, eigene Store-Instanz, damit Config klein und Backup-freundlich bleibt.
- Backup/Restore kompatibel mit HA-Bordmitteln.

## Entities

- `sensor.herold_aktive_topics` — count registrierter Topics
- `sensor.herold_letzte_meldung` — state: topic, attribute: vollständiger letzter Eintrag
- `sensor.herold_unzugeordnete_topics` — count Topics ohne Rollen-Mapping, attribute: Liste der Topic-IDs
- `sensor.herold_meldungen_heute` — Zähler (Mitternacht bis jetzt)
- `sensor.herold_meldungen_7_tage` — Zähler (rollierende 7 Tage)

Keine Attribut-Listen der "letzten N Einträge" auf einem Sensor — HA-Attribute-Limit (~16 kB) kollidiert mit langen Messages. Für Listen → `herold.history_abfragen`.

## Events (auf HA Event Bus)

- `herold_topic_registered` (topic, neu|update)
- `herold_sent` (topic, severity, aufgelöste_rollen, aufgelöste_empfänger, ausliefer_status, fallback_verwendet, eintrag_id, zeitstempel)
- `herold_delivery_failed` (topic, empfänger, fehler) — zusätzlich zum `herold_sent`, für einfacheres Filtern im Event-Trigger

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

Konfigurierbar im Config Flow, **Defaults:**
- Max. Einträge: **2000**
- Max. Alter: **30 Tage**
- Es greift, was zuerst zutrifft (FIFO bei Einträgen, Zeit-Cleanup täglich).
- Auto-Cleanup einmal täglich um 03:00 via `async_track_time_change`.

### Zugriff

- **Service** `herold.history_abfragen` → Liste (siehe Services-Abschnitt oben).
- **Entities** für Dashboard-Ansicht (letzte, heute, 7d).
- **Developer Tools**: Events können live beobachtet werden.
- **v2+:** eigene Lovelace-Card mit Timeline-Ansicht.

### Privacy / Datensparsamkeit

- `payload` und `message` können sensible Infos enthalten → Storage ist lokal (kein Cloud).
- **v2:** Config-Option, `message`-Inhalt im Log nach N Tagen redigieren, nur Metadaten behalten. Im MVP nicht implementiert.

## Konfiguration

**Primär:** Config Flow (UI). Tabs im MVP:
1. **Empfänger** — Auflistung, neu anlegen, `severity_payload` pflegen
2. **Rollen** — anlegen, Mitglieder (Empfänger) verwalten
3. **Topics** — alle registrierten Topics (explizit + implizit), Default-Rollen zuweisen, Baum-Darstellung nach Slash-Hierarchie
4. **Einstellungen** — Fallback-Rolle, Retention (max. Einträge, max. Alter)

**v2:** zusätzlicher Tab **Regeln** (Severity/Zeit/Presence-Overrides).

**Optional:** YAML-Import, für Power-User / Versionskontrolle.

## Getroffene Design-Entscheidungen

Siehe [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) — alle 10 MVP-Fragen sind entschieden.

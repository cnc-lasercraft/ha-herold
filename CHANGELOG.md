# Changelog

Alle nennenswerten Änderungen an diesem Projekt.
Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung nach [Semantic Versioning](https://semver.org/lang/de/).

## [1.1.0] — 2026-08-31

Lesende REST-API und eine einzige Quelle für Effektivwerte.

### Neu

- **REST-API unter `/api/herold/…`** (`config`, `topics`, `topics/<id>`, `rollen`,
  `empfaenger`, `einstellungen`, `history`) für Oberflächen ausserhalb von Home
  Assistant. Lesend, token-authentisiert; geschrieben wird weiterhin nur über die
  `herold.*`-Services. Sensor-Attribute sind als Transportmittel ungeeignet — sie
  werden bei jeder Änderung an alle Clients gepusht und zwangen bisher jeden
  Konsumenten, Producer-Default und User-Override selbst zusammenzuführen.
  `history` liefert einen `cursor` für pollende Clients.
- **`sensor.herold_aktive_topics`** trägt zusätzlich `wirksam_severity`,
  `wirksam_log_only`, `wirksam_interruption_level` und `hat_override`. Die
  bisherigen Felder bleiben unverändert (Producer-Defaults).

### Geändert

- **Producer-Default und Override werden nur noch an einer Stelle zusammengeführt**
  (`HeroldConfigStore.topic_ansicht()`). Mapping-Sensor, Unzugeordnet-Sensor und
  REST-API speisen daraus. Vorher lag dieselbe Logik im Sensor und noch einmal im
  Card-JavaScript — die Ursache des Anzeigefehlers von v1.0.1.

### Behoben

- **Admin-Card zeigte in „Severity" und „Flags" Producer-Defaults** neben wirksamen
  Rollen in derselben Zeile: ein per Override stillgelegtes Topic erschien ohne
  `log`-Flag, ein übersteuertes `interruption_level` gar nicht. Die Karte liest
  diese Spalten jetzt aus den `wirksam_*`-Feldern.
- **`sensor.herold_aktive_topics` abonniert `EVENT_CONFIG_UPDATED`** — ohne das
  wären die neuen Effektivwerte bei Override-Edits eingefroren, bis zufällig eine
  Meldung durchläuft (derselbe Fehler wie 2026-05-31 beim Unzugeordnet-Sensor).

## [1.0.2] — 2026-08-31

Behebt den sporadischen „Konfigurationsfehler" der Custom Cards.

### Behoben

- **Karten meldeten sporadisch „Konfigurationsfehler".** Home Assistant
  installiert mit `app.js` den scoped-custom-element-registry-Polyfill, der
  `customElements` durch eine eigene Registry-Map ersetzt. Die von der
  Integration per `add_extra_js_url` ausgelieferten Karten wurden je nach
  Netzwerk-Timing schon *vor* `app.js` ausgeführt und definierten ihr Element
  damit nur in der nativen Registry — für das `customElements.get()`, mit dem
  Lovelace eine Karte auflöst, blieb es unsichtbar. Belegt im Produktivsystem:
  `customElements.get("herold-log-card")` lieferte `undefined`, während
  `document.createElement("herold-log-card")` sauber zu `HeroldLogCard`
  upgradete. Beide Karten registrieren sich jetzt erst nach dem `load`-Event,
  wenn der Polyfill steht. Der bisherige Guard `if (!customElements.get(...))`
  konnte das nicht abfangen, weil er dieselbe unzuverlässige Funktion befragte;
  er ist durch ein `try`/`catch` um `define()` ersetzt.

## [1.0.1] — 2026-08-30

Fehlerbehebungen an der Admin-Card und an der Auslieferung der Custom Cards.

### Behoben

- **Admin-Card zeigte keine wirksamen Rollen.** Die Topics-Tabelle las das
  Rollen-Mapping noch im flachen Format aus der Zeit vor dem Override-Layer.
  Der Mapping-Sensor liefert pro Feld ein Tripel
  (`producer_default` / `override` / `wirksam`), weshalb jedes Topic
  „— keine —" anzeigte, die Override-Einfärbung der Chips nie griff und der
  Zähler am Mapping-Tab alle Topics statt nur der übersteuerten zählte.
- **Karten-Updates erreichten den Browser nicht.** Die von der Integration
  ausgelieferten Custom Cards wurden trotz `cache_headers=False` heuristisch
  gecacht — nach einem Update lief weiter die alte Karte, ohne Fehlermeldung.
  `add_extra_js_url` hängt die Manifest-Version nun als Query an
  (`/herold/<card>.js?v=<version>`), sodass jeder Release den Cache selbst
  bricht.

### Hinweise zum Update

- Der Cache-Bust greift ab dieser Version. Wer noch die Karte aus 1.0.0 im
  Browser hat, braucht einmalig einen harten Reload (bzw. geleerten App-Cache
  auf Wall-Displays und Kiosk-Browsern); danach genügt ein normaler Reload.

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

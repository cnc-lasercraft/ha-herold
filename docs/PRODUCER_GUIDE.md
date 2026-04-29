# Producer-Guide: Herold aus einer Custom Component nutzen

Anleitung für Custom Components, die Meldungen über Herold versenden wollen.

## Prinzip

Herold ist **optional** — deine CC funktioniert auch ohne. Wenn Herold installiert ist, nutzt du seine Services statt direkt `notify.*` aufzurufen. Damit profitierst du von Rollen-Routing, zentralem Log und Severity-Handling, ohne dich um Geräte-IDs zu kümmern.

## Schritt 1: Herold erkennen (optional dependency)

**Nicht** in `manifest.json` als Dependency eintragen — das würde deine CC von Herold abhängig machen. Stattdessen: zur Laufzeit prüfen, ob Herold verfügbar ist.

```python
# In deiner CC, z.B. const.py
HEROLD_DOMAIN = "herold"

# Helper-Funktion
def herold_verfuegbar(hass) -> bool:
    """Prüft ob Herold geladen ist."""
    return HEROLD_DOMAIN in hass.data
```

## Schritt 2: Topics beim Startup registrieren

In `async_setup_entry` (oder `async_setup`) deiner CC: registriere alle Topics, die deine CC verwenden wird. Das ist **optional** aber empfohlen — Herold akzeptiert auch unbekannte Topics beim `senden`, aber registrierte Topics haben Metadaten (Name, Beschreibung, Default-Severity, Default-Rollen).

```python
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

HEROLD_DOMAIN = "herold"

# Definiere deine Topics zentral
TOPICS = {
    "pool/ph/niedrig": {
        "name": "Pool PH zu niedrig",
        "beschreibung": "PH-Wert liegt unter dem eingestellten Schwellwert",
        "default_severity": "warnung",
        "default_rollen": ["techn_support"],
    },
    "pool/ph/kritisch": {
        "name": "Pool PH kritisch",
        "beschreibung": "PH-Wert liegt weit ausserhalb des Sollbereichs",
        "default_severity": "kritisch",
        "default_rollen": ["techn_support", "erwachsener"],
    },
    "pool/pumpe/fehler": {
        "name": "Pool Pumpe Fehler",
        "beschreibung": "Filterpumpe meldet Störung oder läuft nicht wie erwartet",
        "default_severity": "warnung",
        "default_rollen": ["techn_support"],
    },
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # ... dein normales Setup ...

    # Herold-Topics registrieren (wenn Herold geladen)
    if HEROLD_DOMAIN in hass.data:
        for topic_id, meta in TOPICS.items():
            await hass.services.async_call(
                HEROLD_DOMAIN,
                "topic_registrieren",
                {"topic": topic_id, "quelle": "custom_components.pool", **meta},
                blocking=False,  # nicht warten, Startup nicht blockieren
            )

    return True
```

**Hinweis:** `topic_registrieren` ist idempotent mit Update — bei jedem HA-Restart werden die Topics neu registriert und die Metadaten aufgefrischt. Das ist gewollt.

### `log_only`-Topics (gesprächige Producer ohne Spam-Risiko)

Für Topics, die **nur protokolliert** werden sollen (Debug-Output, Regelungs-Schritte, Status-Tracking), ohne dass Push-Nachrichten rausgehen:

```python
TOPICS = {
    "pool/regelung/schritt": {
        "name": "Pool-Regelung Schritt",
        "beschreibung": "Einzelner Regelungs-Schritt (nur Log)",
        "default_severity": "info",
        "log_only": True,   # ← keine Zustellung, nur History + Event
    },
}
```

**Effekt bei `herold.senden`:** Rollen-Auflösung und Empfänger-Zustellung werden übersprungen, auch der Last-Resort `persistent_notification` greift nicht. Der Eintrag landet aber normal in der History, im Logbook und feuert das `herold_sent`-Event mit `ausliefer_status: {"log_only": "skipped"}`. Du kannst `log_only` auch später via UI (Admin-Card → Topic editieren) oder Service (`topic_registrieren` mit `log_only: true`) umschalten.

## Schritt 3: Meldungen senden

Wenn ein Ereignis eintritt, das eine Benachrichtigung auslösen soll:

```python
async def _check_ph_value(self) -> None:
    """Wird z.B. von einem Coordinator-Update aufgerufen."""
    ph = self._get_current_ph()

    if ph < 6.5:
        await self._herold_senden(
            topic="pool/ph/kritisch",
            titel="Pool PH kritisch!",
            message=f"PH-Wert bei {ph:.1f} (Soll: 7.0–7.4). Sofort prüfen.",
            severity="kritisch",
        )
    elif ph < 6.8:
        await self._herold_senden(
            topic="pool/ph/niedrig",
            titel="Pool PH niedrig",
            message=f"PH-Wert bei {ph:.1f} (Soll: 7.0–7.4).",
            severity="warnung",
        )


async def _herold_senden(self, topic: str, titel: str, message: str, severity: str) -> None:
    """Sendet via Herold wenn verfügbar, sonst Fallback auf direktes Notify."""
    if HEROLD_DOMAIN in self.hass.data:
        await self.hass.services.async_call(
            HEROLD_DOMAIN,
            "senden",
            {
                "topic": topic,
                "titel": titel,
                "message": message,
                "severity": severity,
            },
            blocking=True,
        )
    else:
        # Fallback: direktes Notify (Legacy, ohne Herold)
        # Hier könnte ein konfigurierbarer notify-Service stehen
        pass
```

## Schritt 4: Actions (Actionable Notifications)

Herold reicht HA-Actionable-Notification-Buttons 1:1 an die Empfänger durch:

```python
await self.hass.services.async_call(
    HEROLD_DOMAIN,
    "senden",
    {
        "topic": "pool/pumpe/fehler",
        "titel": "Filterpumpe gestört",
        "message": "Pumpe läuft seit 5 Min nicht. Manuell prüfen?",
        "severity": "warnung",
        "actions": [
            {"action": "POOL_PUMPE_RESET", "title": "Pumpe neu starten"},
            {"action": "POOL_PUMPE_IGNORIEREN", "title": "Ignorieren"},
        ],
    },
    blocking=True,
)
```

Die Action-Antwort kommt weiterhin als normales HA-Event `mobile_app_notification_action` — das verarbeitet deine CC wie gehabt.

## Schritt 5: Payload durchreichen (Bilder, Sounds, etc.)

Für Kamera-Snapshots, Custom-Sounds oder andere device-spezifische Daten gibt
es das Feld `payload`. Es wird 1:1 ans Notify-Backend (z.B. `notify.mobile_app_*`)
durchgereicht.

### ⚠ Payload-Struktur — die häufigste Falle

`payload.data.<feld>` wird zu `data.<feld>` im Notify-Service-Call. Die HA
Companion App-Doku zeigt Beispiele in Form `data: { push: {...} }` — bei Herold
heißt das **`payload: { data: { push: {...} } }`**, NICHT `payload: { data: { data: { push: {...} } } }`.

**Eine `data:`-Ebene zu viel** → Cloud Push Gateway lehnt ab mit der irreführenden
Meldung *"data must only contain string values"* → Push verschwindet stillschweigend.

```yaml
# ❌ FALSCH — eine data:-Ebene zu viel, Push wird vom Gateway gefressen
payload:
  data:
    data:                       # ← diese Ebene gehört NICHT hin
      push:
        sound: { name: default, critical: 1, volume: 1 }
      tag: wasserleck

# ✓ RICHTIG — payload.data wird direkt zu service-call data
payload:
  data:
    push:
      sound: { name: default, critical: 1, volume: 1 }
    tag: wasserleck
    persistent: true
```

**Schutzmechanismus:** Herold erkennt das doppelte `data.data`-Pattern beim
`senden`-Aufruf und entschachtelt automatisch — mit einer `WARNING`-Logzeile
("payload.data.data erkannt — entschachtelt zu payload.data"). Die Meldung
kommt also durch, aber der Producer-Bug muss trotzdem gefixt werden.

### Critical Notification (iOS) — Beispiel

```python
await self.hass.services.async_call(
    HEROLD_DOMAIN,
    "senden",
    {
        "topic": "wasser/leck/waschkueche",
        "titel": "💧 WASSERLECK!",
        "message": "Sensor Waschküche meldet Wasser",
        "severity": "kritisch",
        "interruption_level": "critical",   # ← als eigener Parameter, NICHT in payload
        "payload": {
            "data": {
                "push": {
                    "sound": {
                        "name": "default",
                        "critical": 1,
                        "volume": 1,
                    },
                },
                "tag": "wasserleck_waschkueche",
                "persistent": True,
            }
        },
    },
    blocking=True,
)
```

### Bild / Kamera-Snapshot

```python
"payload": {
    "data": {
        "image": "/api/camera_proxy/camera.pool_kamera",
    }
}
```

### Was wenn der Producer-Payload trotzdem fehlerhaft ist

Bei `severity` ∈ `{warnung, kritisch}` versucht Herold automatisch einen
**Retry ohne `payload`**, wenn das Notify-Backend silent ablehnt. Damit kommt
zumindest die nackte Textmeldung an — Custom-Sound oder Critical-Alert geht
in dem Fall verloren, aber die Information selbst nicht. Der Status der
Zustellung lautet dann `ok_payload_verworfen` und im Log steht die Diagnose.

Wenn auch der Retry scheitert UND es eine `kritisch`-Meldung war, schaltet
Herold die Notbremse: ein **`persistent_notification` im HA-Frontend**, das
solange sichtbar bleibt bis du es wegklickst.

### Hinweise

- `interruption_level` ist ein **eigener `senden`-Parameter**, NICHT in der
  Payload. Wenn du beides setzt, gewinnt der Parameter (höchste Priorität).
- Werte unter `payload.data.push.sound.{critical, volume}` müssen numerisch
  bleiben (das ist Apple-APNS-Spec — die Cloud akzeptiert diese int-Werte
  für bekannte Felder).
- `payload` wird **deep-merged** mit den Herold-Defaults (Topic-`interruption_level`,
  `actions`). Felder im `payload` haben Vorrang, außer der `senden`-Parameter
  `interruption_level` ist explizit gesetzt.

## Schritt 6: Sprachausgabe (TTS) als zusätzlicher Empfänger

Herold kennt zwei Empfänger-Typen: `notify_service` (Push) und `tts`
(Sprachausgabe). Beide werden über das gleiche Routing (Topic → Rolle →
Empfänger) angesprochen — du als Producer schickst genau eine `herold.senden`-
Meldung, Herold verteilt sie an alle relevanten Empfänger in ihrer jeweiligen
Form.

### TTS-Empfänger anlegen

**Einzelner Lautsprecher:**

```yaml
service: herold.empfaenger_setzen
data:
  empfaenger: voice_kueche
  typ: tts
  ziel: tts.home_assistant_cloud           # TTS-Engine
  name: Voice OG Küche
  media_player: media_player.home_assistant_voice_og_kueche_media_player
```

**Mehrere Lautsprecher gleichzeitig** (Komma-Liste — HA `tts.speak` ruft alle
parallel an, gleicher Cache):

```yaml
service: herold.empfaenger_setzen
data:
  empfaenger: voice_haus
  typ: tts
  ziel: tts.home_assistant_cloud
  name: Voice Haus (alle)
  media_player: >-
    media_player.voice_kueche,
    media_player.voice_wohnen,
    media_player.voice_buero
```

### Was sich für TTS unterscheidet

- **`titel` wird ignoriert** — TTS-Engines kennen keinen Titel-Begriff. `message`
  ist der gesprochene Text. Ist `message` leer, wird `titel` gesprochen.
- **`actions`, `interruption_level`, `payload.data.*` werden ignoriert** — das
  sind mobile_app-Spezifika, für TTS irrelevant.
- **`severity` beeinflusst die Sprachausgabe nicht** — der Producer baut den
  Sprechtext wie er will (z.B. selbst „Achtung!" davor schreiben bei kritisch).
- **TTS-spezifische Optionen** (Stimme, Sprache, Geschwindigkeit) gehen über
  `payload.tts_options` und werden als `options:` an `tts.speak` durchgereicht.

### Routing-Beispiel: Push UND Sprachausgabe für ein Topic

Eine Rolle wie `voice_alle` enthält den TTS-Empfänger `voice_haus`, eine Rolle
`erwachsener` enthält den Push-Empfänger `iphone_17_ul`. Ein Wasserleck-Topic
mit beiden Rollen löst beim Aufruf gleichzeitig Push am iPhone UND Ansage auf
allen Lautsprechern aus:

```yaml
service: herold.senden
data:
  topic: wasser/leck/waschkueche
  titel: 💧 WASSERLECK!
  message: Sensor Waschküche meldet Wasser. Sofort prüfen!
  severity: kritisch
  extra_rollen:
    - voice_alle                # zusätzlich zu Topic-Default-Rollen
```

Der `iphone_17_ul`-Empfänger bekommt eine Critical-Push, der `voice_haus`-
Empfänger spricht den `message`-Text auf allen 6 Lautsprechern.

### Hinweise

- **TTS-Engine** ist die Entity (z.B. `tts.home_assistant_cloud`,
  `tts.openai_tts`, `tts.google_en_com`). Service-Pattern intern ist immer
  `tts.speak` mit `target.entity_id = <engine>` — Herold setzt das richtig.
- **Cache** ist hartkodiert auf `false` (TTS-Outputs sind selten identisch).
  Falls du Caching willst, ist das ein eigener Feature-Request.
- **Fail-safe-Schichten** (Sanity-Check, Retry-ohne-Payload, Notbremse) gelten
  nur für `notify_service`-Empfänger. TTS-Fehler (z.B. Lautsprecher offline)
  laufen normal über den Service-Call-Exception-Pfad und landen als
  `fehler:<msg>` im `ausliefer_status`.

## Topic-Namenskonvention

- Format: `<bereich>/<was>[/<detail>]`
- Regex: `^[a-z0-9_/]+$` (Kleinbuchstaben, Ziffern, Unterstrich, Slash)
- Umlaute transkribieren: `waschkueche` statt `waschküche`
- Sprache: frei, empfohlen konsistent mit dem restlichen HA-Setup

**Beispiele:**
```
pool/ph/niedrig
pool/ph/kritisch
pool/pumpe/fehler
pool/temperatur/niedrig
wasser/leck/waschkueche
garage/tor/offen_nachts
backup/fehler
pv/ueberschuss
```

## iOS Interruption-Level (Urgent / Critical / …)

Unabhängig von Severity kannst du das iOS-Interruption-Level steuern — pro Topic (Default) oder pro Meldung (Override).

**Merge-Reihenfolge** (spätere gewinnen):
1. `Topic.interruption_level` — Topic-Default (gesetzt via `topic_registrieren` oder Admin-Card)
2. `senden(..., payload=...)` — allgemeiner Passthrough
3. `senden(..., interruption_level=...)` — höchste Priorität

**Topic-Default setzen:**

```yaml
# In Topic-Registrierung oder über die Admin-Card (Topic-Edit → Dropdown)
service: herold.topic_registrieren
data:
  topic: "wasser/leck/waschkueche"
  interruption_level: "time-sensitive"   # passive / active / time-sensitive / critical
```

**Pro Meldung überschreiben:**

```yaml
service: herold.senden
data:
  topic: "garage/tor/offen_nachts"
  titel: "Garagentor nachts offen!"
  message: "..."
  interruption_level: "critical"   # durchbricht Silent/DND, braucht Critical-Permission
```

**iOS-Bedeutung:**
| Level | Effekt |
|---|---|
| `passive` | Nur Lock-Screen, kein Ton/Vibrieren |
| `active` (iOS-Default) | Standard-Push |
| `time-sensitive` | Durchbricht Focus-Modes, bleibt 1h prominent |
| `critical` | Durchbricht Silent/DND, spielt auch bei Stumm einen Ton — **Critical-Alerts-Permission** in HA Companion App erforderlich |

## Severity-Semantik

| Severity | Bedeutung | Typischer Empfänger-Effekt |
|---|---|---|
| `info` | Zur Kenntnis, kein Handlungsbedarf | Normale Push, leiser Ton |
| `warnung` | Aufmerksamkeit nötig, nicht dringend | Time-sensitive Push |
| `kritisch` | Sofortiges Handeln erforderlich | Critical-Alert, lauter Ton |

Die Severity beeinflusst im MVP **nicht** das Routing (wer bekommt's), sondern nur die Darstellung am Empfänger und das Fail-safe-Verhalten von Herold: bei `warnung`/`kritisch` versucht Herold bei silent-rejects einen Retry ohne `payload`, bei `kritisch` zusätzlich eine `persistent_notification`-Notbremse, falls keine Zustellung gelingt. Bei `info` wird ein einzelner fehlgeschlagener Push nicht heroisch gerettet.

## Zusammenfassung: Minimale Integration

Die kürzeste Integration sind **5 Zeilen** in deiner CC:

```python
# Topic registrieren (einmal beim Setup)
if "herold" in hass.data:
    await hass.services.async_call("herold", "topic_registrieren", {
        "topic": "pool/ph/niedrig", "name": "Pool PH niedrig",
        "default_severity": "warnung", "default_rollen": ["techn_support"],
        "quelle": "custom_components.pool",
    }, blocking=False)

# Meldung senden (wenn Ereignis eintritt)
if "herold" in hass.data:
    await hass.services.async_call("herold", "senden", {
        "topic": "pool/ph/niedrig", "titel": "PH niedrig",
        "message": f"PH bei {ph:.1f}", "severity": "warnung",
    }, blocking=True)
```

## Events abonnieren (optional)

Falls deine CC auf Zustellungs-Ergebnisse oder Config-Änderungen reagieren soll — Herold feuert vier Events auf dem HA-Event-Bus:

| Event | Payload (Auszug) | Wann |
|---|---|---|
| `herold_sent` | `topic`, `severity`, `aufgeloste_rollen`, `aufgeloste_empfaenger`, `ausliefer_status`, `fallback_verwendet`, `eintrag_id`, `zeitstempel` | Nach jedem `senden()` |
| `herold_delivery_failed` | `topic`, `empfaenger`, `fehler` | Einzelner Empfänger-Fehler (zusätzlich zu `herold_sent`) |
| `herold_topic_registered` | `topic`, `status` (`neu` / `update` / `implizit` / `entfernt`) | Topic angelegt/aktualisiert/entfernt |
| `herold_history_cleaned` | `ausloeser` (`scheduler` / `service`), `entfernt`, `restliche`, `max_eintraege`, `max_tage` | Täglicher Retention-Cleanup |
| `herold_config_updated` | `typ` | Rollen/Empfänger/Mapping/Einstellungen geändert |

**Beispiel:** Wenn deine CC auf fehlgeschlagene Zustellungen reagieren will (z.B. alternativen Kanal versuchen):

```python
from homeassistant.core import Event, callback

@callback
def _on_delivery_failed(event: Event) -> None:
    if event.data["topic"].startswith("pool/"):
        _LOGGER.warning(
            "Pool-Zustellung fehlgeschlagen: %s → %s: %s",
            event.data["empfaenger"],
            event.data["topic"],
            event.data["fehler"],
        )

entry.async_on_unload(
    hass.bus.async_listen("herold_delivery_failed", _on_delivery_failed)
)
```

## Retention & History-Abfrage

Herold räumt die History täglich um 03:00 automatisch auf (Default: 2000 Einträge / 30 Tage, beides konfigurierbar). Deine CC kann History jederzeit abfragen:

```python
response = await hass.services.async_call(
    "herold", "history_abfragen",
    {"topic": "pool/*", "severity": "kritisch", "limit": 50},
    blocking=True, return_response=True,
)
for eintrag in response["eintraege"]:
    ...
```

Für sehr gesprächige Producer mit `log_only: true`: bedenke, dass jeder Eintrag Platz in der History belegt. Bei hohem Durchsatz (mehrere pro Minute) empfiehlt sich, die Retention-Grenzen zu reduzieren oder die Producer-Frequenz zu drosseln.

## Eigene Herold-View in deiner CC (Konvention)

**Konvention:** Jeder Producer stellt seine eigenen Herold-Meldungen in einer eigenen Lovelace-View *innerhalb* seines Bereichs dar — gefiltert auf das eigene Topic-Prefix. So sieht der Pool-Bereich nur Pool-Logs, der Wallbox-Bereich nur Wallbox-Logs etc. Zentrale Sicht über alles bleibt die Admin-Card im Herold-Dashboard.

**Warum:** Der Producer kennt seine Topics am besten und ist der natürliche Ort, um sie zu betrachten. Wer am Pool arbeitet, soll Pool-Logs nicht erst aus 1000 fremden Einträgen filtern müssen.

### Card mit fixem Filter

Die `herold-log-card` unterstützt dafür drei Config-Optionen:

| Option | Typ | Wirkung |
|---|---|---|
| `topic` | string | Topic-Filter vorbelegen — exakt (`pool/ph/niedrig`) oder mit Wildcard (`pool/*`) |
| `severity` | `info` / `warnung` / `kritisch` | Severity-Filter vorbelegen |
| `lock_filters` | bool | Filter-Bar ausblenden — die Card zeigt dann **nur** den per Config festgelegten Ausschnitt |
| `title` | string | Header-Text (Default: "Herold Log") |
| `limit` | int | Max. Einträge (Default: 200) |

**Empfohlenes Muster für eine Producer-View** — feste Filter, kein UI-Filter, eigener Titel:

```yaml
title: Log
path: log
icon: mdi:text-box-outline
type: panel
cards:
  - type: custom:herold-log-card
    title: Pool-Log
    topic: pool/*
    lock_filters: true
    limit: 100
```

Wenn `lock_filters` weggelassen wird (oder `false`), wird `topic`/`severity` als **weicher Default** vorbelegt — der User kann den Filter im UI weiter einschränken oder ändern.

### Topic-Prefix als Konvention

Damit das Filtern via `pool/*` sauber funktioniert, muss jeder Producer ein **eindeutiges, konsistentes Topic-Prefix** verwenden. Das Prefix ist gleichzeitig die "Identität" des Producers im Herold-Log — es taucht in der Admin-Card, der Producer-View und dem `quelle`-Feld der Topic-Registrierung auf.

### Aktueller Stand der Producer-Views

| Producer | Topic-Prefix | Dashboard | View-Pfad |
|---|---|---|---|
| Pool-Steuerung | `pool/*` | `pool-steuerung` | `/pool-steuerung/log` |
| Zeekr | `zeekr/*` | `ev-fahrzeuge` | `/ev-fahrzeuge/zeekr-log` |
| Wallbox/Ladeplanung | `wallbox/*` | `ev-fahrzeuge` | `/ev-fahrzeuge/wallbox-log` |
| EKZ Tariff | `ekz_tariff/*` | `ekz-tariff` | `/ekz-tariff/log` |
| Tariff Saver | `tariff_saver/*` | `tariff-saver-price-curve-15-min` | `/tariff-saver-price-curve-15-min/log` |

**Kandidaten für später:** `uniali/*` (Dashboard `uniali-audit` — Herold-Anbindung steht noch aus), `backup/*`, `miele/*`, `garage/*`, `licht/*` etc.

### Rezept: Neue Producer-Log-View nachbauen

Wenn ein Producer Herold neu nutzt oder ein bestehender Producer eine eigene View bekommen soll:

1. **Topic-Prefix festlegen** und konsistent in allen Topics des Producers verwenden (siehe Tabelle oben).
2. **Topics registrieren** beim CC-Setup (Schritt 2 oben), `quelle: "custom_components.<producer>"` setzen.
3. **Log-View ans Producer-Dashboard hängen.** Empfohlene Card-Config:
   ```yaml
   title: Log
   path: log
   icon: mdi:text-box-outline
   type: panel
   cards:
     - type: custom:herold-log-card
       title: <Producer>-Log
       topic: <prefix>/*
       lock_filters: true
       limit: 100
   ```
   Hinzufügen entweder in der Lovelace-UI (Dashboard öffnen → ⋮ → Dashboard bearbeiten → +Ansicht hinzufügen) oder via MCP:
   ```
   ha_config_set_dashboard(url_path="<dashboard>", config_hash=<hash>,
     python_transform='config["views"].append({...wie oben als dict...})')
   ```

Mehr braucht's nicht — die Konvention ist **Topic-Prefix + eine Log-View pro Dashboard**.

### Card-Features (Nutzer-Ebene)

In der gerenderten Card hat der User folgende Interaktion:
- **Sortieren**: Klick auf Spaltenkopf (Zeit/Topic/Titel) toggelt asc/desc, Pfeil zeigt Richtung
- **Severity-Cycle**: Klick auf "Sev." cycelt Filter alle → warnung → info → kritisch → alle
- **Detail**: Klick auf Zeile öffnet/schließt Detail-Box mit Nachricht, Rollen, Empfängern, Zustellstatus
- **Live-Updates**: Card abonniert `herold_sent` und lädt bei jeder neuen Meldung neu

### Card-Code aktualisieren (Deploy)

Wenn `herold-log-card.js` im Repo geändert wurde:

1. **Datei deployen** nach `/homeassistant/www/`:
   ```bash
   cat custom_components/herold/www/herold-log-card.js | \
     ssh has "cat > /homeassistant/www/herold-log-card.js"
   ```
2. **Cache-Bust** der Lovelace-Resource (Browser cached fix, ohne Bump zieht der neue Code nicht):
   ```
   ha_config_set_dashboard_resource(
     resource_id=<id>, url="/local/herold-log-card.js?v=<N+1>",
     resource_type="module")
   ```
3. **Hard-Refresh** im Browser (Cmd+Shift+R) auf einer Producer-View.



- **Routing:** Topic → Rollen → Empfänger. Du sagst *was* passiert ist, Herold weiss *wer* es erfahren muss.
- **Device-Abstraktion:** Kein `notify.mobile_app_iphone_17_ul` mehr im Code. Bei Gerätewechsel: eine Stelle im Herold-Config ändern.
- **Severity-Payload:** Empfänger entscheidet selbst (Critical-Alert, Lautstärke, etc.).
- **Zentrales Log:** Jede Meldung wird protokolliert — wann, was, an wen, ob zugestellt.
- **Audit-Trail:** HA-Context wird mitgespeichert — nachvollziehbar, welche Automation/welcher User ausgelöst hat.

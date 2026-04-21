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

Für Kamera-Snapshots, Custom-Sounds oder andere device-spezifische Daten:

```python
await self.hass.services.async_call(
    HEROLD_DOMAIN,
    "senden",
    {
        "topic": "pool/truebung",
        "titel": "Pool trüb",
        "message": "Trübungswert über Schwellwert, siehe Kamera",
        "severity": "info",
        "payload": {
            "data": {
                "image": "/api/camera_proxy/camera.pool_kamera",
            }
        },
    },
    blocking=True,
)
```

`payload` wird **deep-merged** mit dem `severity_payload` des jeweiligen Empfängers. Die Empfänger-Config hat Vorrang (z.B. Critical-Alert-Sound bei `kritisch`), dein Payload ergänzt (z.B. Bild).

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

## Severity-Semantik

| Severity | Bedeutung | Typischer Empfänger-Effekt |
|---|---|---|
| `info` | Zur Kenntnis, kein Handlungsbedarf | Normale Push, leiser Ton |
| `warnung` | Aufmerksamkeit nötig, nicht dringend | Time-sensitive Push |
| `kritisch` | Sofortiges Handeln erforderlich | Critical-Alert, lauter Ton |

Die Severity beeinflusst im MVP **nicht** das Routing (wer bekommt's), sondern nur **wie** es zugestellt wird (via `severity_payload` am Empfänger). Der Producer entscheidet die Severity, der Empfänger entscheidet die Darstellung.

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

## Was Herold für dich übernimmt

- **Routing:** Topic → Rollen → Empfänger. Du sagst *was* passiert ist, Herold weiss *wer* es erfahren muss.
- **Device-Abstraktion:** Kein `notify.mobile_app_iphone_17_ul` mehr im Code. Bei Gerätewechsel: eine Stelle im Herold-Config ändern.
- **Severity-Payload:** Empfänger entscheidet selbst (Critical-Alert, Lautstärke, etc.).
- **Zentrales Log:** Jede Meldung wird protokolliert — wann, was, an wen, ob zugestellt.
- **Audit-Trail:** HA-Context wird mitgespeichert — nachvollziehbar, welche Automation/welcher User ausgelöst hat.

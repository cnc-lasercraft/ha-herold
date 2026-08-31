"""REST-API von Herold — Lesezugriff auf Konfiguration und History.

Warum eine eigene API, wo doch neun Sensoren dieselben Daten tragen?
Sensor-Attribute sind für eine Oberfläche das falsche Transportmittel: sie
werden bei jeder Änderung an *alle* HA-Clients gepusht, sie landen im Recorder
(`topic_mapping` sprengte mit 73 Topics die 16-KB-Grenze und musste per
`recorder: exclude` ruhiggestellt werden), und sie zwingen jeden Konsumenten,
Producer-Default und User-Override selbst zusammenzuführen. Genau das ist
2026-08-30 schiefgegangen.

Diese Views liefern beide Konfigurationsebenen *und* den Effektivwert in einem
Objekt, gebaut von `HeroldConfigStore.topic_ansicht()` — derselben Funktion,
aus der auch die Sensoren speisen. Damit gibt es die Zusammenführung nur noch
an einer Stelle.

Alle Endpunkte sind lesend und verlangen ein HA-Token (`requires_auth`, der
Standard von `HomeAssistantView`). Geschrieben wird weiterhin ausschliesslich
über die `herold.*`-Services — ein externer Client bleibt damit Fernbedienung
und wird nie zweite Wahrheit.

    GET /api/herold/config          Alles auf einmal (ein Roundtrip)
    GET /api/herold/topics          Topics mit Producer/Override/Effektiv
    GET /api/herold/topics/<id>     Ein Topic (id darf Slashes enthalten)
    GET /api/herold/rollen          Rollen inkl. Mitglieder
    GET /api/herold/empfaenger      Empfänger inkl. Typ und Ziel
    GET /api/herold/einstellungen   Fallback-Rolle, Retention, Kennzahlen
    GET /api/herold/history         Log, gefiltert (siehe HeroldHistoryView)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .store import HeroldConfigStore, HeroldHistoryStore

_LOGGER = logging.getLogger(__name__)

API_BASIS = f"/api/{DOMAIN}"

# Obergrenze für history?limit= — schützt davor, dass ein Client sich das
# komplette Archiv (Retention-Default 2000 Einträge) in einem Zug zieht.
HISTORY_LIMIT_MAX = 2000
HISTORY_LIMIT_DEFAULT = 100


def _stores(request: web.Request) -> tuple[HeroldConfigStore, HeroldHistoryStore]:
    """Stores aus hass.data holen."""
    hass: HomeAssistant = request.app["hass"]
    daten = hass.data[DOMAIN]
    return daten["config_store"], daten["history_store"]


def _rollen_nutzung(config: HeroldConfigStore) -> dict[str, int]:
    """Zählt je Rolle, wie viele Topics sie wirksam adressieren.

    Beantwortet die Frage „darf ich diese Rolle löschen?" ohne dass der Client
    alle Topics durchgehen muss.
    """
    zaehler = {rid: 0 for rid in config.rollen}
    for tid in config.topics:
        for rid in config.effective_default_rollen(tid)[0]:
            if rid in zaehler:
                zaehler[rid] += 1
    return zaehler


def _empfaenger_ansicht(config: HeroldConfigStore) -> list[dict[str, Any]]:
    """Empfänger inkl. der Rollen, über die sie erreicht werden."""
    return [
        {
            **empf.to_dict(),
            "rollen": sorted(
                rid for rid, rolle in config.rollen.items() if eid in rolle.mitglieder
            ),
        }
        for eid, empf in sorted(config.empfaenger.items())
    ]


class HeroldConfigView(HomeAssistantView):
    """Gesamte Konfiguration in einem Roundtrip."""

    url = f"{API_BASIS}/config"
    name = f"api:{DOMAIN}:config"

    async def get(self, request: web.Request) -> web.Response:
        config, history = _stores(request)
        nutzung = _rollen_nutzung(config)
        topics = config.topic_ansichten()
        return self.json(
            {
                "topics": topics,
                "rollen": [
                    {**rolle.to_dict(), "topic_anzahl": nutzung.get(rid, 0)}
                    for rid, rolle in sorted(config.rollen.items())
                ],
                "empfaenger": _empfaenger_ansicht(config),
                "einstellungen": _einstellungen(config, history, topics),
            }
        )


class HeroldTopicsView(HomeAssistantView):
    """Alle Topics mit beiden Konfigurationsebenen."""

    url = f"{API_BASIS}/topics"
    name = f"api:{DOMAIN}:topics"

    async def get(self, request: web.Request) -> web.Response:
        config, _ = _stores(request)
        topics = config.topic_ansichten()

        # Filter: ?unzugeordnet=1 und ?override=1 sind die beiden Arbeitslisten,
        # mit denen Topic-Triage tatsächlich gemacht wird.
        if request.query.get("unzugeordnet") in ("1", "true"):
            topics = [t for t in topics if t["unzugeordnet"]]
        if request.query.get("override") in ("1", "true"):
            topics = [t for t in topics if t["hat_override"]]
        if praefix := request.query.get("praefix"):
            topics = [t for t in topics if t["id"].startswith(praefix)]

        return self.json({"topics": topics, "anzahl": len(topics)})


class HeroldTopicView(HomeAssistantView):
    """Ein einzelnes Topic. Die ID darf Slashes enthalten (`pool/tank_leer`)."""

    url = API_BASIS + "/topics/{topic_id:.*}"
    name = f"api:{DOMAIN}:topic"

    async def get(self, request: web.Request, topic_id: str) -> web.Response:
        config, _ = _stores(request)
        ansicht = config.topic_ansicht(topic_id)
        if not ansicht:
            return self.json({"error": f"Topic '{topic_id}' unbekannt"}, status_code=404)
        return self.json(ansicht)


class HeroldRollenView(HomeAssistantView):
    """Rollen inkl. Mitglieder und Anzahl adressierter Topics."""

    url = f"{API_BASIS}/rollen"
    name = f"api:{DOMAIN}:rollen"

    async def get(self, request: web.Request) -> web.Response:
        config, _ = _stores(request)
        nutzung = _rollen_nutzung(config)
        return self.json(
            {
                "rollen": [
                    {
                        **rolle.to_dict(),
                        "topic_anzahl": nutzung.get(rid, 0),
                        "ist_fallback": rid == config.fallback_rolle,
                    }
                    for rid, rolle in sorted(config.rollen.items())
                ]
            }
        )


class HeroldEmpfaengerView(HomeAssistantView):
    """Empfänger inkl. der Rollen, über die sie erreicht werden."""

    url = f"{API_BASIS}/empfaenger"
    name = f"api:{DOMAIN}:empfaenger"

    async def get(self, request: web.Request) -> web.Response:
        config, _ = _stores(request)
        return self.json({"empfaenger": _empfaenger_ansicht(config)})


def _einstellungen(
    config: HeroldConfigStore,
    history: HeroldHistoryStore,
    topics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Globale Einstellungen plus die Kennzahlen, die eine Übersicht braucht."""
    if topics is None:
        topics = config.topic_ansichten()
    return {
        "fallback_rolle": config.fallback_rolle,
        "retention_eintraege": config.retention_eintraege,
        "retention_tage": config.retention_tage,
        "anzahl": {
            "topics": len(config.topics),
            "rollen": len(config.rollen),
            "empfaenger": len(config.empfaenger),
            "overrides": sum(1 for t in topics if t["hat_override"]),
            "unzugeordnet": sum(1 for t in topics if t["unzugeordnet"]),
            "history_eintraege": len(history.eintraege),
        },
    }


class HeroldEinstellungenView(HomeAssistantView):
    """Fallback-Rolle, Retention und Kennzahlen."""

    url = f"{API_BASIS}/einstellungen"
    name = f"api:{DOMAIN}:einstellungen"

    async def get(self, request: web.Request) -> web.Response:
        config, history = _stores(request)
        return self.json(_einstellungen(config, history))


class HeroldHistoryView(HomeAssistantView):
    """Log-Einträge, gefiltert.

    Query-Parameter (alle optional):
      topic      exakter Match, oder Prefix mit `/*` (`pool/*`)
      severity   info | warnung | kritisch
      rolle      nur Einträge, die diese Rolle aufgelöst haben
      von, bis   ISO-8601-Zeitstempel
      seit       Alias für `von` — als Cursor für pollende Clients gedacht
      zugestellt 1 = nur Einträge, die tatsächlich jemanden erreicht haben
      limit      Standard 100, Maximum 2000

    Die Antwort trägt `cursor`: den Zeitstempel des jüngsten Eintrags. Wer ihn
    beim nächsten Aufruf als `seit` zurückgibt, bekommt nur Neues — genau das
    Muster, das die Kommandozentrale heute mit einem eigenen Cursor nachbaut.
    """

    url = f"{API_BASIS}/history"
    name = f"api:{DOMAIN}:history"

    async def get(self, request: web.Request) -> web.Response:
        _, history = _stores(request)
        q = request.query

        try:
            limit = min(int(q.get("limit", HISTORY_LIMIT_DEFAULT)), HISTORY_LIMIT_MAX)
        except ValueError:
            return self.json({"error": "limit muss eine Zahl sein"}, status_code=400)

        ergebnis = list(history.eintraege)

        if topic := q.get("topic"):
            if topic.endswith("/*"):
                praefix = topic[:-1]  # "pool/*" → "pool/"
                ergebnis = [
                    e
                    for e in ergebnis
                    if e.topic.startswith(praefix) or e.topic == praefix.rstrip("/")
                ]
            else:
                ergebnis = [e for e in ergebnis if e.topic == topic]

        if severity := q.get("severity"):
            ergebnis = [e for e in ergebnis if e.severity == severity]

        if rolle := q.get("rolle"):
            ergebnis = [e for e in ergebnis if rolle in e.aufgeloste_rollen]

        if q.get("zugestellt") in ("1", "true"):
            ergebnis = [e for e in ergebnis if e.aufgeloste_empfaenger]

        try:
            if von := (q.get("seit") or q.get("von")):
                grenze = datetime.fromisoformat(von)
                ergebnis = [
                    e
                    for e in ergebnis
                    if datetime.fromisoformat(e.zeitstempel) > grenze
                ]
            if bis := q.get("bis"):
                grenze = datetime.fromisoformat(bis)
                ergebnis = [
                    e
                    for e in ergebnis
                    if datetime.fromisoformat(e.zeitstempel) <= grenze
                ]
        except ValueError as err:
            return self.json({"error": f"Ungültiger Zeitstempel: {err}"}, status_code=400)

        gesamt = len(ergebnis)
        ergebnis.sort(key=lambda e: e.zeitstempel, reverse=True)
        ergebnis = ergebnis[:limit]

        return self.json(
            {
                "eintraege": [e.to_dict() for e in ergebnis],
                "anzahl": len(ergebnis),
                "gesamt": gesamt,
                "cursor": ergebnis[0].zeitstempel if ergebnis else q.get("seit"),
            }
        )


def register_views(hass: HomeAssistant) -> None:
    """Alle Views bei HA registrieren (einmalig aus `async_setup`)."""
    for view in (
        HeroldConfigView(),
        HeroldTopicsView(),
        HeroldRollenView(),
        HeroldEmpfaengerView(),
        HeroldEinstellungenView(),
        HeroldHistoryView(),
        # Zuletzt: die Catch-all-Route `/topics/{id:.*}` würde sonst
        # `/topics` selbst mitschlucken.
        HeroldTopicView(),
    ):
        hass.http.register_view(view)
    _LOGGER.debug("REST-API registriert unter %s", API_BASIS)

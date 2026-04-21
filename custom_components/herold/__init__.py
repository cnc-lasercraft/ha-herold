"""Herold — zentrale Meldungs-Vermittlung mit Rollen-Routing."""
from __future__ import annotations

import logging
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.helpers import config_validation as cv, discovery
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType

from .const import (
    CLEANUP_HOUR,
    CLEANUP_MINUTE,
    DOMAIN,
    EMPF_TYP_NOTIFY,
    EMPF_TYPEN,
    EVENT_CONFIG_UPDATED,
    EVENT_DELIVERY_FAILED,
    EVENT_HISTORY_CLEANED,
    EVENT_SENT,
    EVENT_TOPIC_REGISTERED,
    SERVICE_EINSTELLUNGEN_SETZEN,
    SERVICE_EMPFAENGER_ENTFERNEN,
    SERVICE_EMPFAENGER_SETZEN,
    SERVICE_HISTORY_ABFRAGEN,
    SERVICE_HISTORY_AUFRAEUMEN,
    SERVICE_ROLLE_ENTFERNEN,
    SERVICE_ROLLE_SETZEN,
    SERVICE_SENDEN,
    SERVICE_TOPIC_ENTFERNEN,
    SERVICE_TOPIC_REGISTRIEREN,
    SERVICE_TOPIC_ROLLE_MAPPING,
    SEVERITIES,
    SEVERITY_DEFAULT,
    TOPIC_REGEX,
)
from .models import Empfaenger, HistoryEintrag, Rolle, Topic
from .store import HeroldConfigStore, HeroldHistoryStore

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _topic_id(value: object) -> str:
    if not isinstance(value, str) or not TOPIC_REGEX.match(value):
        raise vol.Invalid(
            f"Topic-ID '{value}' ist ungültig — erlaubt: Kleinbuchstaben, "
            f"Ziffern, Unterstrich, Slash ({TOPIC_REGEX.pattern})."
        )
    return value


def _deep_merge(base: dict, override: dict) -> dict:
    """Rekursiver Dict-Merge — override-Werte gewinnen."""
    result = deepcopy(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = deepcopy(val)
    return result


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

SENDEN_SCHEMA = vol.Schema(
    {
        vol.Required("topic"): _topic_id,
        vol.Required("titel"): cv.string,
        vol.Optional("message", default=""): cv.string,
        vol.Optional("severity"): vol.In(SEVERITIES),
        vol.Optional("actions"): vol.All(cv.ensure_list, [dict]),
        vol.Optional("extra_rollen"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("payload"): dict,
    }
)

TOPIC_REGISTRIEREN_SCHEMA = vol.Schema(
    {
        vol.Required("topic"): _topic_id,
        vol.Optional("name"): cv.string,
        vol.Optional("beschreibung"): cv.string,
        vol.Optional("quelle"): cv.string,
        vol.Optional("default_severity"): vol.In(SEVERITIES),
        vol.Optional("default_rollen"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("log_only"): cv.boolean,
    }
)

TOPIC_ENTFERNEN_SCHEMA = vol.Schema(
    {
        vol.Required("topic"): _topic_id,
    }
)

ROLLE_SETZEN_SCHEMA = vol.Schema(
    {
        vol.Required("rolle"): cv.string,
        vol.Optional("name"): cv.string,
        vol.Required("mitglieder"): vol.All(cv.ensure_list, [cv.string]),
    }
)

EMPFAENGER_SETZEN_SCHEMA = vol.Schema(
    {
        vol.Required("empfaenger"): cv.string,
        vol.Optional("typ", default=EMPF_TYP_NOTIFY): vol.In(EMPF_TYPEN),
        vol.Required("ziel"): cv.string,
        vol.Optional("name"): cv.string,
        vol.Optional("severity_payload"): dict,
    }
)

ROLLE_ENTFERNEN_SCHEMA = vol.Schema(
    {
        vol.Required("rolle"): cv.string,
    }
)

EMPFAENGER_ENTFERNEN_SCHEMA = vol.Schema(
    {
        vol.Required("empfaenger"): cv.string,
    }
)

TOPIC_ROLLE_MAPPING_SCHEMA = vol.Schema(
    {
        vol.Required("topic"): _topic_id,
        vol.Optional("rollen"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("zuruecksetzen", default=False): cv.boolean,
    }
)

EINSTELLUNGEN_SETZEN_SCHEMA = vol.Schema(
    {
        vol.Optional("fallback_rolle"): vol.Any(cv.string, None),
        vol.Optional("retention_eintraege"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional("retention_tage"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)

HISTORY_AUFRAEUMEN_SCHEMA = vol.Schema(
    {
        vol.Optional("max_eintraege"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional("max_tage"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)

HISTORY_ABFRAGEN_SCHEMA = vol.Schema(
    {
        vol.Optional("topic"): cv.string,
        vol.Optional("severity"): vol.In(SEVERITIES),
        vol.Optional("rolle"): cv.string,
        vol.Optional("zeitraum_von"): cv.string,
        vol.Optional("zeitraum_bis"): cv.string,
        vol.Optional("limit", default=100): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=10000)
        ),
    }
)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Setup via YAML-Eintrag ``herold:`` in configuration.yaml."""
    config_store = HeroldConfigStore(hass)
    history_store = HeroldHistoryStore(hass)
    await config_store.async_load()
    await history_store.async_load()

    async def _save_and_notify(typ: str = "config") -> None:
        """Config persistieren + EVENT_CONFIG_UPDATED feuern (für Admin-UI)."""
        await config_store.async_save()
        hass.bus.async_fire(EVENT_CONFIG_UPDATED, {"typ": typ})

    hass.data[DOMAIN] = {
        "config_store": config_store,
        "history_store": history_store,
        "save_and_notify": _save_and_notify,
    }

    # Sensor-Plattform laden
    hass.async_create_task(
        discovery.async_load_platform(hass, "sensor", DOMAIN, {}, config)
    )

    # -----------------------------------------------------------------------
    # Service: topic_registrieren
    # -----------------------------------------------------------------------

    async def _handle_topic_registrieren(call: ServiceCall) -> None:
        topic_id = call.data["topic"]
        existing = config_store.topics.get(topic_id)

        if existing:
            for feld in ("name", "beschreibung", "quelle", "default_severity"):
                if feld in call.data:
                    setattr(existing, feld, call.data[feld])
            if "default_rollen" in call.data:
                existing.default_rollen = list(call.data["default_rollen"])
            if "log_only" in call.data:
                existing.log_only = bool(call.data["log_only"])
            existing.explizit_registriert = True
            status = "update"
            _LOGGER.info("Topic '%s' aktualisiert", topic_id)
        else:
            config_store.topics[topic_id] = Topic(
                id=topic_id,
                name=call.data.get("name", topic_id),
                beschreibung=call.data.get("beschreibung", ""),
                quelle=call.data.get("quelle", ""),
                default_severity=call.data.get("default_severity", SEVERITY_DEFAULT),
                default_rollen=list(call.data.get("default_rollen", [])),
                explizit_registriert=True,
                log_only=bool(call.data.get("log_only", False)),
            )
            status = "neu"
            _LOGGER.info(
                "Topic '%s' registriert%s",
                topic_id,
                " (log_only)" if call.data.get("log_only") else "",
            )

        await _save_and_notify()
        hass.bus.async_fire(
            EVENT_TOPIC_REGISTERED, {"topic": topic_id, "status": status}
        )

    # -----------------------------------------------------------------------
    # Service: topic_entfernen
    # -----------------------------------------------------------------------

    async def _handle_topic_entfernen(call: ServiceCall) -> None:
        topic_id = call.data["topic"]
        if topic_id not in config_store.topics:
            _LOGGER.warning("Topic '%s' existiert nicht — nichts zu entfernen", topic_id)
            return
        config_store.topics.pop(topic_id, None)
        config_store.topic_rolle_mapping.pop(topic_id, None)
        await _save_and_notify()
        _LOGGER.info("Topic '%s' entfernt (inkl. Rollen-Mapping)", topic_id)
        hass.bus.async_fire(
            EVENT_TOPIC_REGISTERED, {"topic": topic_id, "status": "entfernt"}
        )

    # -----------------------------------------------------------------------
    # Service: rolle_setzen
    # -----------------------------------------------------------------------

    async def _handle_rolle_setzen(call: ServiceCall) -> None:
        rolle_id = call.data["rolle"]
        mitglieder = list(call.data["mitglieder"])
        existing = config_store.rollen.get(rolle_id)

        if existing:
            existing.mitglieder = mitglieder
            if "name" in call.data:
                existing.name = call.data["name"]
            _LOGGER.info("Rolle '%s' aktualisiert (%d Mitglieder)", rolle_id, len(mitglieder))
        else:
            config_store.rollen[rolle_id] = Rolle(
                id=rolle_id,
                name=call.data.get("name", rolle_id),
                mitglieder=mitglieder,
            )
            if config_store.fallback_rolle is None:
                config_store.fallback_rolle = rolle_id
                _LOGGER.info("Rolle '%s' als Fallback-Rolle gesetzt (erste Rolle)", rolle_id)
            _LOGGER.info("Rolle '%s' erstellt (%d Mitglieder)", rolle_id, len(mitglieder))

        await _save_and_notify()

    # -----------------------------------------------------------------------
    # Service: empfaenger_setzen
    # -----------------------------------------------------------------------

    async def _handle_empfaenger_setzen(call: ServiceCall) -> None:
        empf_id = call.data["empfaenger"]
        existing = config_store.empfaenger.get(empf_id)

        if existing:
            existing.typ = call.data["typ"]
            existing.ziel = call.data["ziel"]
            if "name" in call.data:
                existing.name = call.data["name"]
            if "severity_payload" in call.data:
                existing.severity_payload = call.data["severity_payload"]
            _LOGGER.info("Empfänger '%s' aktualisiert", empf_id)
        else:
            config_store.empfaenger[empf_id] = Empfaenger(
                id=empf_id,
                typ=call.data["typ"],
                ziel=call.data["ziel"],
                name=call.data.get("name", empf_id),
                severity_payload=call.data.get("severity_payload", {}),
            )
            _LOGGER.info(
                "Empfänger '%s' erstellt: %s → %s", empf_id, call.data["typ"], call.data["ziel"]
            )

        await _save_and_notify()

    # -----------------------------------------------------------------------
    # Services: rolle_entfernen / empfaenger_entfernen
    # -----------------------------------------------------------------------

    async def _handle_rolle_entfernen(call: ServiceCall) -> None:
        rolle_id = call.data["rolle"]
        if rolle_id not in config_store.rollen:
            _LOGGER.warning("Rolle '%s' existiert nicht — nichts zu entfernen", rolle_id)
            return
        config_store.rollen.pop(rolle_id, None)
        # Rolle aus Producer-Defaults und Admin-Mapping entfernen
        for t in config_store.topics.values():
            if rolle_id in t.default_rollen:
                t.default_rollen = [r for r in t.default_rollen if r != rolle_id]
        for tid, rollen in list(config_store.topic_rolle_mapping.items()):
            neue = [r for r in rollen if r != rolle_id]
            if neue:
                config_store.topic_rolle_mapping[tid] = neue
            else:
                config_store.topic_rolle_mapping.pop(tid, None)
        if config_store.fallback_rolle == rolle_id:
            config_store.fallback_rolle = None
            _LOGGER.warning("Fallback-Rolle '%s' wurde gelöscht — keine Fallback-Rolle mehr gesetzt", rolle_id)
        await _save_and_notify()
        _LOGGER.info("Rolle '%s' entfernt (aus allen Topics/Mappings bereinigt)", rolle_id)

    async def _handle_empfaenger_entfernen(call: ServiceCall) -> None:
        empf_id = call.data["empfaenger"]
        if empf_id not in config_store.empfaenger:
            _LOGGER.warning(
                "Empfänger '%s' existiert nicht — nichts zu entfernen", empf_id
            )
            return
        config_store.empfaenger.pop(empf_id, None)
        # Empfänger aus allen Rollen-Mitgliedern entfernen
        for r in config_store.rollen.values():
            if empf_id in r.mitglieder:
                r.mitglieder = [m for m in r.mitglieder if m != empf_id]
        await _save_and_notify()
        _LOGGER.info("Empfänger '%s' entfernt (aus allen Rollen bereinigt)", empf_id)

    # -----------------------------------------------------------------------
    # Service: topic_rolle_mapping  (Admin-Override für Topic → Rollen)
    # -----------------------------------------------------------------------

    async def _handle_topic_rolle_mapping(call: ServiceCall) -> None:
        topic_id = call.data["topic"]
        if call.data.get("zuruecksetzen"):
            config_store.topic_rolle_mapping.pop(topic_id, None)
            await _save_and_notify()
            _LOGGER.info(
                "Admin-Mapping für Topic '%s' zurückgesetzt — Producer-Defaults greifen wieder",
                topic_id,
            )
            return
        rollen = list(call.data.get("rollen", []))
        if rollen:
            config_store.topic_rolle_mapping[topic_id] = rollen
            _LOGGER.info("Topic '%s' → Rollen-Override: %s", topic_id, rollen)
        else:
            config_store.topic_rolle_mapping.pop(topic_id, None)
            _LOGGER.info("Topic '%s' → leere Rollen-Liste = Mapping entfernt", topic_id)
        await _save_and_notify()

    # -----------------------------------------------------------------------
    # Service: einstellungen_setzen  (Fallback-Rolle, Retention-Grenzen)
    # -----------------------------------------------------------------------

    async def _handle_einstellungen_setzen(call: ServiceCall) -> None:
        geaendert = []
        if "fallback_rolle" in call.data:
            wert = call.data["fallback_rolle"] or None
            if wert and wert not in config_store.rollen:
                _LOGGER.error(
                    "fallback_rolle='%s' existiert nicht — ignoriert", wert
                )
            else:
                config_store.fallback_rolle = wert
                geaendert.append(f"fallback_rolle={wert}")
        if "retention_eintraege" in call.data:
            config_store.retention_eintraege = int(call.data["retention_eintraege"])
            geaendert.append(f"retention_eintraege={config_store.retention_eintraege}")
        if "retention_tage" in call.data:
            config_store.retention_tage = int(call.data["retention_tage"])
            geaendert.append(f"retention_tage={config_store.retention_tage}")
        if geaendert:
            await _save_and_notify()
            _LOGGER.info("Einstellungen geändert: %s", ", ".join(geaendert))

    # -----------------------------------------------------------------------
    # Service: senden  (Resolution-Engine)
    # -----------------------------------------------------------------------

    async def _handle_senden(call: ServiceCall) -> None:
        topic_id: str = call.data["topic"]
        titel: str = call.data["titel"]
        message: str = call.data.get("message", "")
        actions: list[dict] = call.data.get("actions", [])
        extra_rollen: list[str] = call.data.get("extra_rollen", [])
        payload: dict[str, Any] = call.data.get("payload", {})
        fallback_verwendet = False

        # -- 1. Topic nachschlagen / implizit anlegen --
        topic = config_store.topics.get(topic_id)
        if not topic:
            topic = Topic(id=topic_id, name=topic_id, explizit_registriert=False)
            config_store.topics[topic_id] = topic
            await _save_and_notify()
            _LOGGER.info("Topic '%s' implizit angelegt (erster senden-Call)", topic_id)
            hass.bus.async_fire(
                EVENT_TOPIC_REGISTERED, {"topic": topic_id, "status": "implizit"}
            )

        # -- 2. Severity: Call-Override > Topic-Default > Global-Default --
        severity = call.data.get("severity") or topic.default_severity or SEVERITY_DEFAULT

        # -- log_only Short-Circuit: nur History + Event, keine Zustellung --
        aufgeloste_rollen: list[str] = []
        empfaenger_ids: list[str] = []
        ausliefer_status: dict[str, str] = {}

        if topic.log_only:
            ausliefer_status["log_only"] = "skipped"
            _LOGGER.debug(
                "Topic '%s' ist log_only — keine Zustellung, nur History/Event",
                topic_id,
            )
        else:
            # -- 3. Rollen bestimmen --
            # Admin-Mapping hat Vorrang vor Producer-Defaults
            if topic_id in config_store.topic_rolle_mapping:
                rollen_ids = list(config_store.topic_rolle_mapping[topic_id])
            else:
                rollen_ids = list(topic.default_rollen)

            for r in extra_rollen:
                if r not in rollen_ids:
                    rollen_ids.append(r)

            if not rollen_ids and config_store.fallback_rolle:
                rollen_ids = [config_store.fallback_rolle]
                fallback_verwendet = True
                _LOGGER.warning(
                    "Topic '%s' hat keine Rollen-Zuordnung — Fallback '%s'",
                    topic_id,
                    config_store.fallback_rolle,
                )

            # -- 4. Rollen → Empfänger auflösen + deduplizieren --
            for rolle_id in rollen_ids:
                rolle = config_store.rollen.get(rolle_id)
                if not rolle:
                    _LOGGER.warning("Rolle '%s' nicht gefunden — übersprungen", rolle_id)
                    continue
                aufgeloste_rollen.append(rolle_id)
                for mid in rolle.mitglieder:
                    if mid not in empfaenger_ids:
                        empfaenger_ids.append(mid)

            # -- 5. Zustellung --
            if not empfaenger_ids:
                # Last-Resort: persistent_notification
                fallback_verwendet = True
                _LOGGER.warning(
                    "Keine Empfänger für Topic '%s' — Last-Resort persistent_notification",
                    topic_id,
                )
                try:
                    await hass.services.async_call(
                        "persistent_notification",
                        "create",
                        {
                            "title": f"[Herold] {titel}",
                            "message": (
                                f"**Topic:** {topic_id}\n"
                                f"**Severity:** {severity}\n\n"
                                f"{message}\n\n---\n"
                                f"_Herold konnte keine Empfänger auflösen. "
                                f"Bitte Rollen-Zuordnung prüfen._"
                            ),
                            "notification_id": f"herold_{uuid.uuid4().hex[:8]}",
                        },
                        blocking=True,
                    )
                    ausliefer_status["persistent_notification"] = "ok"
                except Exception as err:  # noqa: BLE001
                    ausliefer_status["persistent_notification"] = f"fehler:{err}"
                    _LOGGER.error("Last-Resort persistent_notification fehlgeschlagen: %s", err)
            else:
                for empf_id in empfaenger_ids:
                    empf = config_store.empfaenger.get(empf_id)
                    if not empf:
                        _LOGGER.warning("Empfänger '%s' nicht im Registry — übersprungen", empf_id)
                        ausliefer_status[empf_id] = "skipped:nicht_registriert"
                        continue

                    if empf.typ != EMPF_TYP_NOTIFY:
                        ausliefer_status[empf_id] = f"skipped:typ_{empf.typ}_nicht_unterstuetzt"
                        continue

                    # Basis-Payload für notify.*
                    notify_data: dict[str, Any] = {
                        "title": titel,
                        "message": message or titel,
                    }

                    if actions:
                        notify_data.setdefault("data", {})["actions"] = actions

                    if payload:
                        notify_data = _deep_merge(notify_data, payload)

                    sev_override = empf.severity_payload.get(severity)
                    if sev_override:
                        notify_data = _deep_merge(notify_data, sev_override)

                    # notify.mobile_app_xxx → domain="notify", service="mobile_app_xxx"
                    parts = empf.ziel.split(".", 1)
                    if len(parts) != 2:
                        ausliefer_status[empf_id] = f"fehler:ungültiges_ziel:{empf.ziel}"
                        _LOGGER.error("Empfänger '%s': ungültiges Ziel '%s'", empf_id, empf.ziel)
                        continue

                    try:
                        await hass.services.async_call(
                            parts[0], parts[1], notify_data, blocking=True
                        )
                        ausliefer_status[empf_id] = "ok"
                        _LOGGER.debug("Zustellung an '%s' (%s) OK", empf_id, empf.ziel)
                    except Exception as err:  # noqa: BLE001
                        ausliefer_status[empf_id] = f"fehler:{err}"
                        _LOGGER.error("Zustellung an '%s' fehlgeschlagen: %s", empf_id, err)
                        hass.bus.async_fire(
                            EVENT_DELIVERY_FAILED,
                            {"topic": topic_id, "empfaenger": empf_id, "fehler": str(err)},
                        )

        # -- 6. History-Eintrag --
        eintrag_id = uuid.uuid4().hex
        zeitstempel = datetime.now(tz=timezone.utc).isoformat()

        eintrag = HistoryEintrag(
            id=eintrag_id,
            zeitstempel=zeitstempel,
            topic=topic_id,
            severity=severity,
            titel=titel,
            message=message,
            aufgeloste_rollen=aufgeloste_rollen,
            aufgeloste_empfaenger=empfaenger_ids,
            ausliefer_status=ausliefer_status,
            actions=actions,
            payload=payload,
            fallback_verwendet=fallback_verwendet,
            quelle_context={
                "user_id": call.context.user_id,
                "parent_id": call.context.parent_id,
                "id": call.context.id,
            },
        )
        await history_store.async_add(eintrag)

        # -- 7. Event --
        hass.bus.async_fire(
            EVENT_SENT,
            {
                "eintrag_id": eintrag_id,
                "topic": topic_id,
                "severity": severity,
                "aufgeloste_rollen": aufgeloste_rollen,
                "aufgeloste_empfaenger": empfaenger_ids,
                "ausliefer_status": ausliefer_status,
                "fallback_verwendet": fallback_verwendet,
                "zeitstempel": zeitstempel,
            },
        )

        ok = sum(1 for s in ausliefer_status.values() if s == "ok")
        fehler = sum(1 for s in ausliefer_status.values() if s.startswith("fehler:"))
        skip = sum(1 for s in ausliefer_status.values() if s.startswith("skipped:"))
        _LOGGER.info(
            "senden: topic=%s severity=%s → %d ok / %d fehler / %d skipped%s",
            topic_id,
            severity,
            ok,
            fehler,
            skip,
            " [FALLBACK]" if fallback_verwendet else "",
        )

    # -----------------------------------------------------------------------
    # Service: history_abfragen
    # -----------------------------------------------------------------------

    async def _handle_history_abfragen(call: ServiceCall) -> ServiceResponse:
        topic_filter = call.data.get("topic")
        severity_filter = call.data.get("severity")
        rolle_filter = call.data.get("rolle")
        zeitraum_von = call.data.get("zeitraum_von")
        zeitraum_bis = call.data.get("zeitraum_bis")
        limit = call.data.get("limit", 100)

        ergebnis = list(history_store.eintraege)

        if topic_filter:
            if topic_filter.endswith("/*"):
                prefix = topic_filter[:-1]  # "pool/*" → "pool/"
                ergebnis = [
                    e
                    for e in ergebnis
                    if e.topic.startswith(prefix) or e.topic == prefix.rstrip("/")
                ]
            else:
                ergebnis = [e for e in ergebnis if e.topic == topic_filter]

        if severity_filter:
            ergebnis = [e for e in ergebnis if e.severity == severity_filter]

        if rolle_filter:
            ergebnis = [e for e in ergebnis if rolle_filter in e.aufgeloste_rollen]

        if zeitraum_von:
            von = datetime.fromisoformat(zeitraum_von)
            ergebnis = [
                e for e in ergebnis if datetime.fromisoformat(e.zeitstempel) >= von
            ]

        if zeitraum_bis:
            bis = datetime.fromisoformat(zeitraum_bis)
            ergebnis = [
                e for e in ergebnis if datetime.fromisoformat(e.zeitstempel) <= bis
            ]

        ergebnis.sort(key=lambda e: e.zeitstempel, reverse=True)
        ergebnis = ergebnis[:limit]

        return {"eintraege": [e.to_dict() for e in ergebnis]}

    # -----------------------------------------------------------------------
    # Service: history_aufraeumen + täglicher Scheduler
    # -----------------------------------------------------------------------

    async def _cleanup(max_eintraege: int, max_tage: int, ausloeser: str) -> int:
        entfernt = await history_store.async_cleanup(max_eintraege, max_tage)
        hass.bus.async_fire(
            EVENT_HISTORY_CLEANED,
            {
                "ausloeser": ausloeser,
                "entfernt": entfernt,
                "restliche": len(history_store.eintraege),
                "max_eintraege": max_eintraege,
                "max_tage": max_tage,
            },
        )
        return entfernt

    async def _handle_history_aufraeumen(call: ServiceCall) -> None:
        max_eintraege = call.data.get("max_eintraege", config_store.retention_eintraege)
        max_tage = call.data.get("max_tage", config_store.retention_tage)
        await _cleanup(max_eintraege, max_tage, ausloeser="service")

    async def _scheduled_cleanup(_now) -> None:
        await _cleanup(
            config_store.retention_eintraege,
            config_store.retention_tage,
            ausloeser="scheduler",
        )

    async_track_time_change(
        hass,
        _scheduled_cleanup,
        hour=CLEANUP_HOUR,
        minute=CLEANUP_MINUTE,
        second=0,
    )

    # -----------------------------------------------------------------------
    # Registrierung
    # -----------------------------------------------------------------------

    hass.services.async_register(
        DOMAIN, SERVICE_SENDEN, _handle_senden, schema=SENDEN_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TOPIC_REGISTRIEREN,
        _handle_topic_registrieren,
        schema=TOPIC_REGISTRIEREN_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TOPIC_ENTFERNEN,
        _handle_topic_entfernen,
        schema=TOPIC_ENTFERNEN_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ROLLE_SETZEN, _handle_rolle_setzen, schema=ROLLE_SETZEN_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_EMPFAENGER_SETZEN,
        _handle_empfaenger_setzen,
        schema=EMPFAENGER_SETZEN_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ROLLE_ENTFERNEN,
        _handle_rolle_entfernen,
        schema=ROLLE_ENTFERNEN_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_EMPFAENGER_ENTFERNEN,
        _handle_empfaenger_entfernen,
        schema=EMPFAENGER_ENTFERNEN_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TOPIC_ROLLE_MAPPING,
        _handle_topic_rolle_mapping,
        schema=TOPIC_ROLLE_MAPPING_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_EINSTELLUNGEN_SETZEN,
        _handle_einstellungen_setzen,
        schema=EINSTELLUNGEN_SETZEN_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_HISTORY_ABFRAGEN,
        _handle_history_abfragen,
        schema=HISTORY_ABFRAGEN_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_HISTORY_AUFRAEUMEN,
        _handle_history_aufraeumen,
        schema=HISTORY_AUFRAEUMEN_SCHEMA,
    )

    _LOGGER.info(
        "Herold eingerichtet: %d Topics, %d Rollen, %d Empfänger, %d History",
        len(config_store.topics),
        len(config_store.rollen),
        len(config_store.empfaenger),
        len(history_store.eintraege),
    )

    # Config Flow Entry einmalig anlegen, damit Verwaltung in Settings auftaucht.
    # Der Entry hält keine eigenen Daten — alles bleibt im Config-Store.
    if not hass.config_entries.async_entries(DOMAIN):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data={}
            )
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Config-Flow-Entry aktiv — die eigentliche Integration läuft bereits.

    `async_setup` hat Services, Stores, Sensoren und Scheduler bereits
    initialisiert (idempotent über `hass.data[DOMAIN]`). Dieser Entry dient
    nur als Anker für den Options-Flow in Settings → Devices & Services.
    """
    if DOMAIN not in hass.data:
        # Integration wurde direkt via UI installiert, ohne `herold:` in YAML.
        # Wir triggern `async_setup` mit leerer Config einmalig nach.
        await async_setup(hass, {DOMAIN: {}})
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Entry-Entfernen erlaubt — laufende Services/Stores bleiben bestehen."""
    return True

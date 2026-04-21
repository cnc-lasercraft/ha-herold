"""Sensor-Plattform für Herold — Dashboard-Entities für Meldungsübersicht."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import (
    DOMAIN,
    EVENT_CONFIG_UPDATED,
    EVENT_SENT,
    EVENT_TOPIC_REGISTERED,
)
from .store import HeroldConfigStore, HeroldHistoryStore

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Sensor-Plattform einrichten."""
    config_store: HeroldConfigStore = hass.data[DOMAIN]["config_store"]
    history_store: HeroldHistoryStore = hass.data[DOMAIN]["history_store"]

    async_add_entities(
        [
            HeroldLetzteMeldungSensor(history_store),
            HeroldMeldungenHeuteSensor(history_store),
            HeroldMeldungen7TageSensor(history_store),
            HeroldAktiveTopicsSensor(config_store),
            HeroldUnzugeordneteTopicsSensor(config_store),
            HeroldRollenSensor(config_store),
            HeroldEmpfaengerSensor(config_store),
            HeroldMappingSensor(config_store),
            HeroldEinstellungenSensor(config_store),
        ]
    )


# ---------------------------------------------------------------------------
# Basis
# ---------------------------------------------------------------------------


class HeroldBaseSensor(SensorEntity):
    """Basis-Sensor: kein Polling, aktualisiert sich via Bus-Events."""

    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(self, listen_events: list[str]) -> None:
        self._listen_events = listen_events
        self._unsub: list[callback] = []

    async def async_added_to_hass(self) -> None:
        for ev in self._listen_events:
            self._unsub.append(
                self.hass.bus.async_listen(ev, self._on_event)
            )

    async def async_will_remove_from_hass(self) -> None:
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()

    @callback
    def _on_event(self, _event: Event) -> None:
        self.async_write_ha_state()


# ---------------------------------------------------------------------------
# Sensoren
# ---------------------------------------------------------------------------


class HeroldLetzteMeldungSensor(HeroldBaseSensor):
    """State = Topic der letzten Meldung, Attribute = voller Eintrag."""

    _attr_unique_id = f"{DOMAIN}_letzte_meldung"
    _attr_name = "Herold Letzte Meldung"
    _attr_icon = "mdi:message-text-clock"

    def __init__(self, history_store: HeroldHistoryStore) -> None:
        super().__init__([EVENT_SENT])
        self._store = history_store

    @property
    def native_value(self) -> str | None:
        if not self._store.eintraege:
            return None
        return self._store.eintraege[-1].topic

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self._store.eintraege:
            return None
        e = self._store.eintraege[-1]
        return {
            "eintrag_id": e.id,
            "zeitstempel": e.zeitstempel,
            "topic": e.topic,
            "severity": e.severity,
            "titel": e.titel,
            "message": e.message,
            "aufgeloste_rollen": e.aufgeloste_rollen,
            "aufgeloste_empfaenger": e.aufgeloste_empfaenger,
            "ausliefer_status": e.ausliefer_status,
            "fallback_verwendet": e.fallback_verwendet,
        }


class HeroldMeldungenHeuteSensor(HeroldBaseSensor):
    """Anzahl Meldungen seit Mitternacht (UTC)."""

    _attr_unique_id = f"{DOMAIN}_meldungen_heute"
    _attr_name = "Herold Meldungen Heute"
    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "Meldungen"

    def __init__(self, history_store: HeroldHistoryStore) -> None:
        super().__init__([EVENT_SENT])
        self._store = history_store

    @property
    def native_value(self) -> int:
        midnight = datetime.now(tz=timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return sum(
            1
            for e in self._store.eintraege
            if datetime.fromisoformat(e.zeitstempel) >= midnight
        )


class HeroldMeldungen7TageSensor(HeroldBaseSensor):
    """Anzahl Meldungen der letzten 7 Tage (rollierend)."""

    _attr_unique_id = f"{DOMAIN}_meldungen_7_tage"
    _attr_name = "Herold Meldungen 7 Tage"
    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "Meldungen"

    def __init__(self, history_store: HeroldHistoryStore) -> None:
        super().__init__([EVENT_SENT])
        self._store = history_store

    @property
    def native_value(self) -> int:
        grenze = datetime.now(tz=timezone.utc) - timedelta(days=7)
        return sum(
            1
            for e in self._store.eintraege
            if datetime.fromisoformat(e.zeitstempel) >= grenze
        )


class HeroldAktiveTopicsSensor(HeroldBaseSensor):
    """Anzahl registrierter Topics. Attribute: Liste mit ID/Name/explizit."""

    _attr_unique_id = f"{DOMAIN}_aktive_topics"
    _attr_name = "Herold Aktive Topics"
    _attr_icon = "mdi:tag-multiple"
    _attr_native_unit_of_measurement = "Topics"

    def __init__(self, config_store: HeroldConfigStore) -> None:
        super().__init__([EVENT_TOPIC_REGISTERED, EVENT_SENT])
        self._store = config_store

    @property
    def native_value(self) -> int:
        return len(self._store.topics)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "topics": [
                {
                    "id": t.id,
                    "name": t.name,
                    "severity": t.default_severity,
                    "explizit": t.explizit_registriert,
                    "log_only": t.log_only,
                    "interruption_level": t.interruption_level,
                }
                for t in self._store.topics.values()
            ]
        }


class HeroldUnzugeordneteTopicsSensor(HeroldBaseSensor):
    """Topics ohne Rollen-Zuordnung — Admin-Aufmerksamkeit nötig."""

    _attr_unique_id = f"{DOMAIN}_unzugeordnete_topics"
    _attr_name = "Herold Unzugeordnete Topics"
    _attr_icon = "mdi:tag-off"
    _attr_native_unit_of_measurement = "Topics"

    def __init__(self, config_store: HeroldConfigStore) -> None:
        super().__init__([EVENT_TOPIC_REGISTERED, EVENT_SENT])
        self._store = config_store

    @property
    def native_value(self) -> int:
        return len(self._unzugeordnete())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"topics": self._unzugeordnete()}

    def _unzugeordnete(self) -> list[str]:
        return [
            tid
            for tid, topic in self._store.topics.items()
            if not topic.log_only
            and not topic.default_rollen
            and tid not in self._store.topic_rolle_mapping
        ]


# ---------------------------------------------------------------------------
# Admin-Card-Sensoren (Rollen, Empfänger, Mapping, Einstellungen)
# ---------------------------------------------------------------------------


class HeroldRollenSensor(HeroldBaseSensor):
    """Rollen-Liste als Attribute für die Admin-Card."""

    _attr_unique_id = f"{DOMAIN}_rollen"
    _attr_name = "Herold Rollen"
    _attr_icon = "mdi:account-group"
    _attr_native_unit_of_measurement = "Rollen"

    def __init__(self, config_store: HeroldConfigStore) -> None:
        super().__init__([EVENT_CONFIG_UPDATED])
        self._store = config_store

    @property
    def native_value(self) -> int:
        return len(self._store.rollen)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "rollen": [
                {
                    "id": r.id,
                    "name": r.name,
                    "mitglieder": list(r.mitglieder),
                    "ist_fallback": r.id == self._store.fallback_rolle,
                }
                for r in sorted(self._store.rollen.values(), key=lambda x: x.id)
            ]
        }


class HeroldEmpfaengerSensor(HeroldBaseSensor):
    """Empfänger-Liste als Attribute für die Admin-Card."""

    _attr_unique_id = f"{DOMAIN}_empfaenger"
    _attr_name = "Herold Empfänger"
    _attr_icon = "mdi:cellphone-message"
    _attr_native_unit_of_measurement = "Empfänger"

    def __init__(self, config_store: HeroldConfigStore) -> None:
        super().__init__([EVENT_CONFIG_UPDATED])
        self._store = config_store

    @property
    def native_value(self) -> int:
        return len(self._store.empfaenger)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        rollen_je_empf: dict[str, list[str]] = {}
        for r in self._store.rollen.values():
            for m in r.mitglieder:
                rollen_je_empf.setdefault(m, []).append(r.id)
        return {
            "empfaenger": [
                {
                    "id": e.id,
                    "typ": e.typ,
                    "ziel": e.ziel,
                    "name": e.name,
                    "rollen": sorted(rollen_je_empf.get(e.id, [])),
                }
                for e in sorted(
                    self._store.empfaenger.values(), key=lambda x: x.id
                )
            ]
        }


class HeroldMappingSensor(HeroldBaseSensor):
    """Topic → Rollen-Mapping (Admin-Overrides) als Attribute."""

    _attr_unique_id = f"{DOMAIN}_mapping"
    _attr_name = "Herold Topic-Mapping"
    _attr_icon = "mdi:swap-horizontal"
    _attr_native_unit_of_measurement = "Overrides"

    def __init__(self, config_store: HeroldConfigStore) -> None:
        super().__init__([EVENT_CONFIG_UPDATED, EVENT_TOPIC_REGISTERED])
        self._store = config_store

    @property
    def native_value(self) -> int:
        return len(self._store.topic_rolle_mapping)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        eintraege = []
        for tid, topic in sorted(self._store.topics.items()):
            override = self._store.topic_rolle_mapping.get(tid)
            eintraege.append(
                {
                    "topic": tid,
                    "producer_default": list(topic.default_rollen),
                    "override": list(override) if override is not None else None,
                    "wirksam": list(override)
                    if override is not None
                    else list(topic.default_rollen),
                    "log_only": topic.log_only,
                }
            )
        return {"mapping": eintraege}


class HeroldEinstellungenSensor(HeroldBaseSensor):
    """Globale Einstellungen (Fallback-Rolle + Retention) als Attribute."""

    _attr_unique_id = f"{DOMAIN}_einstellungen"
    _attr_name = "Herold Einstellungen"
    _attr_icon = "mdi:cog"

    def __init__(self, config_store: HeroldConfigStore) -> None:
        super().__init__([EVENT_CONFIG_UPDATED])
        self._store = config_store

    @property
    def native_value(self) -> str:
        return self._store.fallback_rolle or "—"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "fallback_rolle": self._store.fallback_rolle,
            "retention_eintraege": self._store.retention_eintraege,
            "retention_tage": self._store.retention_tage,
        }

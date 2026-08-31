"""Persistenz-Layer für Herold — Config-Store und History-Store."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    RETENTION_EINTRAEGE_DEFAULT,
    RETENTION_TAGE_DEFAULT,
    STORAGE_KEY_CONFIG,
    STORAGE_KEY_HISTORY,
    STORAGE_VERSION,
)
from .models import Empfaenger, HistoryEintrag, Rolle, Topic

_LOGGER = logging.getLogger(__name__)


class HeroldConfigStore:
    """Verwaltet .storage/herold — Topics, Rollen, Empfänger, Einstellungen."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY_CONFIG
        )
        self.topics: dict[str, Topic] = {}
        self.rollen: dict[str, Rolle] = {}
        self.empfaenger: dict[str, Empfaenger] = {}
        self.topic_rolle_mapping: dict[str, list[str]] = {}
        # Per-Topic User-Overrides für Felder, die sonst Producer-Defaults sind.
        # Erlaubte Schlüssel pro Topic: "log_only", "interruption_level",
        # "default_severity". (Rollen-Override liegt in topic_rolle_mapping.)
        # Schlüssel im Inner-Dict bedeutet "User hat überschrieben" — Wert wird
        # benutzt; fehlt der Schlüssel, gilt der Producer-Default aus Topic.
        self.topic_overrides: dict[str, dict[str, Any]] = {}
        self.fallback_rolle: str | None = None
        self.retention_eintraege: int = RETENTION_EINTRAEGE_DEFAULT
        self.retention_tage: int = RETENTION_TAGE_DEFAULT

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.topics = {
            tid: Topic.from_dict(t) for tid, t in data.get("topics", {}).items()
        }
        self.rollen = {
            rid: Rolle.from_dict(r) for rid, r in data.get("rollen", {}).items()
        }
        self.empfaenger = {
            eid: Empfaenger.from_dict(e)
            for eid, e in data.get("empfaenger", {}).items()
        }
        self.topic_rolle_mapping = {
            tid: list(rollen)
            for tid, rollen in data.get("topic_rolle_mapping", {}).items()
        }
        self.topic_overrides = {
            tid: dict(o) for tid, o in data.get("topic_overrides", {}).items()
        }
        einst = data.get("einstellungen", {})
        self.fallback_rolle = einst.get("fallback_rolle")
        self.retention_eintraege = einst.get(
            "retention_eintraege", RETENTION_EINTRAEGE_DEFAULT
        )
        self.retention_tage = einst.get("retention_tage", RETENTION_TAGE_DEFAULT)
        _LOGGER.debug(
            "Config geladen: %d Topics, %d Rollen, %d Empfänger",
            len(self.topics),
            len(self.rollen),
            len(self.empfaenger),
        )

    # ---- Effective-Werte (Override > Producer-Default) ----

    def effective_log_only(self, topic_id: str) -> bool:
        o = self.topic_overrides.get(topic_id, {})
        if "log_only" in o:
            return bool(o["log_only"])
        topic = self.topics.get(topic_id)
        return bool(topic.log_only) if topic else False

    def effective_interruption_level(self, topic_id: str) -> str | None:
        o = self.topic_overrides.get(topic_id, {})
        if "interruption_level" in o:
            return o["interruption_level"] or None
        topic = self.topics.get(topic_id)
        return topic.interruption_level if topic else None

    def effective_default_severity(self, topic_id: str) -> str | None:
        o = self.topic_overrides.get(topic_id, {})
        if "default_severity" in o and o["default_severity"]:
            return o["default_severity"]
        topic = self.topics.get(topic_id)
        return topic.default_severity if topic else None

    def effective_default_rollen(self, topic_id: str) -> tuple[list[str], bool]:
        """Gibt (rollen, override_aktiv) zurück.
        override_aktiv=True → User-Override greift (auch bei leerer Liste).
        """
        if topic_id in self.topic_rolle_mapping:
            return list(self.topic_rolle_mapping[topic_id]), True
        topic = self.topics.get(topic_id)
        return (list(topic.default_rollen) if topic else []), False

    # ---- Kombinierte Topic-Ansicht (Producer-Default + Override + Effektiv) ----
    #
    # EINE Quelle für die Zusammenführung der beiden Konfigurationsebenen.
    # Sensoren, REST-API und Karten lesen alle hierher — vorher lag dieselbe
    # Logik im Mapping-Sensor UND im Card-JavaScript, was zwangsläufig
    # auseinanderlief (Admin-Card zeigte 2026-08-30 bei jedem Topic
    # „— keine —", weil das JS die flache Vor-Override-Struktur erwartete).

    def _tripel(self, topic_id: str, feld: str, producer_value: Any) -> dict[str, Any]:
        """{producer_default, override, wirksam} für ein überschreibbares Feld."""
        overrides = self.topic_overrides.get(topic_id, {})
        if feld in overrides:
            return {
                "producer_default": producer_value,
                "override": overrides[feld],
                "wirksam": overrides[feld],
            }
        return {
            "producer_default": producer_value,
            "override": None,
            "wirksam": producer_value,
        }

    def hat_override(self, topic_id: str) -> bool:
        """True, wenn der User an diesem Topic irgendetwas übersteuert hat."""
        return bool(
            topic_id in self.topic_rolle_mapping
            or self.topic_overrides.get(topic_id)
        )

    def ist_unzugeordnet(self, topic_id: str) -> bool:
        """Topic ohne wirksame Rolle, das trotzdem zugestellt werden will.

        `log_only`-Topics zählen nicht — die sollen bewusst niemanden erreichen.
        """
        return not self.effective_log_only(topic_id) and not (
            self.effective_default_rollen(topic_id)[0]
        )

    def topic_ansicht(self, topic_id: str) -> dict[str, Any]:
        """Vollbild eines Topics: Stammdaten, beide Ebenen, Effektivwerte."""
        topic = self.topics.get(topic_id)
        if topic is None:
            return {}

        rollen_override = self.topic_rolle_mapping.get(topic_id)
        rollen = (
            {
                "producer_default": list(topic.default_rollen),
                "override": list(rollen_override),
                "wirksam": list(rollen_override),
            }
            if rollen_override is not None
            else {
                "producer_default": list(topic.default_rollen),
                "override": None,
                "wirksam": list(topic.default_rollen),
            }
        )
        log_only = self._tripel(topic_id, "log_only", bool(topic.log_only))
        interruption = self._tripel(
            topic_id, "interruption_level", topic.interruption_level
        )
        severity = self._tripel(topic_id, "default_severity", topic.default_severity)

        return {
            "id": topic.id,
            "name": topic.name,
            "beschreibung": topic.beschreibung,
            "quelle": topic.quelle,
            "explizit_registriert": topic.explizit_registriert,
            "rollen": rollen,
            "log_only": log_only,
            "interruption_level": interruption,
            "default_severity": severity,
            "hat_override": self.hat_override(topic_id),
            "unzugeordnet": self.ist_unzugeordnet(topic_id),
            # Kurzform für Konsumenten, die nur den Effektivwert brauchen.
            "wirksam": {
                "rollen": rollen["wirksam"],
                "log_only": log_only["wirksam"],
                "interruption_level": interruption["wirksam"],
                "default_severity": severity["wirksam"],
            },
        }

    def topic_ansichten(self) -> list[dict[str, Any]]:
        """Alle Topics als kombinierte Ansicht, nach ID sortiert."""
        return [self.topic_ansicht(tid) for tid in sorted(self.topics)]

    async def async_save(self) -> None:
        data = {
            "topics": {tid: t.to_dict() for tid, t in self.topics.items()},
            "rollen": {rid: r.to_dict() for rid, r in self.rollen.items()},
            "empfaenger": {eid: e.to_dict() for eid, e in self.empfaenger.items()},
            "topic_rolle_mapping": {
                tid: list(rollen) for tid, rollen in self.topic_rolle_mapping.items()
            },
            "topic_overrides": {
                tid: dict(o) for tid, o in self.topic_overrides.items()
            },
            "einstellungen": {
                "fallback_rolle": self.fallback_rolle,
                "retention_eintraege": self.retention_eintraege,
                "retention_tage": self.retention_tage,
            },
        }
        await self._store.async_save(data)


class HeroldHistoryStore:
    """Verwaltet .storage/herold_history — rollierendes Log aller Meldungen."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY_HISTORY
        )
        self.eintraege: list[HistoryEintrag] = []

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.eintraege = [
            HistoryEintrag.from_dict(e) for e in data.get("eintraege", [])
        ]
        _LOGGER.debug("History geladen: %d Einträge", len(self.eintraege))

    async def async_save(self) -> None:
        data = {"eintraege": [e.to_dict() for e in self.eintraege]}
        await self._store.async_save(data)

    async def async_add(self, eintrag: HistoryEintrag) -> None:
        self.eintraege.append(eintrag)
        await self.async_save()

    def cleanup(self, max_eintraege: int, max_tage: int) -> int:
        """Entfernt abgelaufene/überzählige Einträge, gibt Anzahl entfernter zurück."""
        vorher = len(self.eintraege)
        grenze = datetime.now(tz=timezone.utc) - timedelta(days=max_tage)
        self.eintraege = [
            e
            for e in self.eintraege
            if datetime.fromisoformat(e.zeitstempel) >= grenze
        ]
        if len(self.eintraege) > max_eintraege:
            self.eintraege = self.eintraege[-max_eintraege:]
        return vorher - len(self.eintraege)

    async def async_cleanup(self, max_eintraege: int, max_tage: int) -> int:
        """Wie cleanup(), persistiert aber direkt und loggt das Ergebnis."""
        entfernt = self.cleanup(max_eintraege, max_tage)
        if entfernt:
            await self.async_save()
            _LOGGER.info(
                "History-Cleanup: %d Einträge entfernt (Grenze %d Einträge / %d Tage, noch %d)",
                entfernt,
                max_eintraege,
                max_tage,
                len(self.eintraege),
            )
        else:
            _LOGGER.debug(
                "History-Cleanup: nichts zu entfernen (%d Einträge innerhalb Grenzen)",
                len(self.eintraege),
            )
        return entfernt

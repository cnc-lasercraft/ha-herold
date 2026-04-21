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

    async def async_save(self) -> None:
        data = {
            "topics": {tid: t.to_dict() for tid, t in self.topics.items()},
            "rollen": {rid: r.to_dict() for rid, r in self.rollen.items()},
            "empfaenger": {eid: e.to_dict() for eid, e in self.empfaenger.items()},
            "topic_rolle_mapping": {
                tid: list(rollen) for tid, rollen in self.topic_rolle_mapping.items()
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

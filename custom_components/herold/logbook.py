"""Logbook-Integration für Herold — schöne Darstellung aller Herold-Events."""
from __future__ import annotations

from typing import Any, Callable

from homeassistant.components.logbook import (
    LOGBOOK_ENTRY_MESSAGE,
    LOGBOOK_ENTRY_NAME,
)
from homeassistant.core import Event, HomeAssistant, callback

from .const import (
    DOMAIN,
    EVENT_DELIVERY_FAILED,
    EVENT_HISTORY_CLEANED,
    EVENT_SENT,
    EVENT_TOPIC_REGISTERED,
)

_NAME = "Herold"


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, Any]]], None],
) -> None:
    """Registriert Logbook-Beschreibungen für alle Herold-Events."""

    @callback
    def _sent(event: Event) -> dict[str, Any]:
        d = event.data
        topic = d.get("topic", "?")
        severity = d.get("severity", "?")
        empf = d.get("aufgeloste_empfaenger") or []
        status = d.get("ausliefer_status") or {}
        fallback = d.get("fallback_verwendet", False)
        il = d.get("interruption_level")
        il_quelle = d.get("interruption_level_quelle")

        if status.get("log_only") == "skipped":
            msg = f"[{severity}] {topic} → nur Log (log_only)"
        elif fallback and "persistent_notification" in status:
            msg = f"[{severity}] {topic} → Last-Resort (keine Empfänger)"
        else:
            ok = sum(1 for v in status.values() if v == "ok")
            err = sum(1 for v in status.values() if isinstance(v, str) and v.startswith("fehler"))
            total = len(empf)
            msg = f"[{severity}] {topic} → {ok}/{total} zugestellt"
            if err:
                msg += f", {err} Fehler"
            if fallback:
                msg += " (Fallback-Rolle)"

        if il:
            msg += f" · 🔔 {il}" + (f" ({il_quelle})" if il_quelle else "")

        return {LOGBOOK_ENTRY_NAME: _NAME, LOGBOOK_ENTRY_MESSAGE: msg}

    @callback
    def _topic_registered(event: Event) -> dict[str, Any]:
        d = event.data
        status = d.get("status", "?")
        label = {"neu": "registriert", "update": "aktualisiert", "implizit": "implizit angelegt"}.get(
            status, status
        )
        return {
            LOGBOOK_ENTRY_NAME: _NAME,
            LOGBOOK_ENTRY_MESSAGE: f"Topic {d.get('topic')} {label}",
        }

    @callback
    def _delivery_failed(event: Event) -> dict[str, Any]:
        d = event.data
        return {
            LOGBOOK_ENTRY_NAME: _NAME,
            LOGBOOK_ENTRY_MESSAGE: (
                f"Zustellung fehlgeschlagen: {d.get('topic')} → "
                f"{d.get('empfaenger')}: {d.get('fehler')}"
            ),
        }

    @callback
    def _history_cleaned(event: Event) -> dict[str, Any]:
        d = event.data
        entfernt = d.get("entfernt", 0)
        restliche = d.get("restliche", 0)
        ausloeser = d.get("ausloeser", "?")
        if entfernt:
            msg = (
                f"History-Cleanup ({ausloeser}): {entfernt} Einträge entfernt, "
                f"{restliche} verbleiben"
            )
        else:
            msg = f"History-Cleanup ({ausloeser}): nichts zu tun ({restliche} Einträge)"
        return {LOGBOOK_ENTRY_NAME: _NAME, LOGBOOK_ENTRY_MESSAGE: msg}

    async_describe_event(DOMAIN, EVENT_SENT, _sent)
    async_describe_event(DOMAIN, EVENT_TOPIC_REGISTERED, _topic_registered)
    async_describe_event(DOMAIN, EVENT_DELIVERY_FAILED, _delivery_failed)
    async_describe_event(DOMAIN, EVENT_HISTORY_CLEANED, _history_cleaned)

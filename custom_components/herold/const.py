"""Konstanten für Herold."""
from __future__ import annotations

import re
from typing import Final

DOMAIN: Final = "herold"

STORAGE_VERSION: Final = 1
STORAGE_KEY_CONFIG: Final = DOMAIN
STORAGE_KEY_HISTORY: Final = f"{DOMAIN}_history"

TOPIC_REGEX: Final = re.compile(r"^[a-z0-9_/]+$")

SEVERITY_INFO: Final = "info"
SEVERITY_WARNUNG: Final = "warnung"
SEVERITY_KRITISCH: Final = "kritisch"
SEVERITIES: Final = (SEVERITY_INFO, SEVERITY_WARNUNG, SEVERITY_KRITISCH)
SEVERITY_DEFAULT: Final = SEVERITY_INFO

# iOS Interruption Levels (Apple Push). `active` ist der iOS-Default —
# wird wie "kein Override" behandelt. `critical` braucht die Critical-
# Alerts-Permission in der HA Companion App.
INTERRUPTION_LEVELS: Final = ("passive", "active", "time-sensitive", "critical")

EMPF_TYP_NOTIFY: Final = "notify_service"
EMPF_TYPEN: Final = (EMPF_TYP_NOTIFY,)

RETENTION_EINTRAEGE_DEFAULT: Final = 2000
RETENTION_TAGE_DEFAULT: Final = 30

SERVICE_SENDEN: Final = "senden"
SERVICE_TOPIC_REGISTRIEREN: Final = "topic_registrieren"
SERVICE_ROLLE_SETZEN: Final = "rolle_setzen"
SERVICE_EMPFAENGER_SETZEN: Final = "empfaenger_setzen"
SERVICE_HISTORY_ABFRAGEN: Final = "history_abfragen"
SERVICE_HISTORY_AUFRAEUMEN: Final = "history_aufraeumen"
SERVICE_TOPIC_ENTFERNEN: Final = "topic_entfernen"
SERVICE_ROLLE_ENTFERNEN: Final = "rolle_entfernen"
SERVICE_EMPFAENGER_ENTFERNEN: Final = "empfaenger_entfernen"
SERVICE_TOPIC_ROLLE_MAPPING: Final = "topic_rolle_mapping"
SERVICE_EINSTELLUNGEN_SETZEN: Final = "einstellungen_setzen"

EVENT_SENT: Final = f"{DOMAIN}_sent"
EVENT_TOPIC_REGISTERED: Final = f"{DOMAIN}_topic_registered"
EVENT_DELIVERY_FAILED: Final = f"{DOMAIN}_delivery_failed"
EVENT_HISTORY_CLEANED: Final = f"{DOMAIN}_history_cleaned"
EVENT_CONFIG_UPDATED: Final = f"{DOMAIN}_config_updated"

CLEANUP_HOUR: Final = 3
CLEANUP_MINUTE: Final = 0

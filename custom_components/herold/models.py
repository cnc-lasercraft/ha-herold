"""Domain-Modelle für Herold (Topic, Rolle, Empfänger, History-Eintrag)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .const import SEVERITY_DEFAULT


@dataclass(slots=True)
class Topic:
    id: str
    name: str = ""
    beschreibung: str = ""
    quelle: str = ""
    default_severity: str = SEVERITY_DEFAULT
    default_rollen: list[str] = field(default_factory=list)
    explizit_registriert: bool = False
    log_only: bool = False
    interruption_level: str | None = None  # None = kein Topic-Override

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "beschreibung": self.beschreibung,
            "quelle": self.quelle,
            "default_severity": self.default_severity,
            "default_rollen": list(self.default_rollen),
            "explizit_registriert": self.explizit_registriert,
            "log_only": self.log_only,
            "interruption_level": self.interruption_level,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Topic":
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            beschreibung=data.get("beschreibung", ""),
            quelle=data.get("quelle", ""),
            default_severity=data.get("default_severity", SEVERITY_DEFAULT),
            default_rollen=list(data.get("default_rollen", [])),
            explizit_registriert=data.get("explizit_registriert", False),
            log_only=data.get("log_only", False),
            interruption_level=data.get("interruption_level"),
        )


@dataclass(slots=True)
class Rolle:
    id: str
    name: str = ""
    mitglieder: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "mitglieder": list(self.mitglieder),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rolle":
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            mitglieder=list(data.get("mitglieder", [])),
        )


@dataclass(slots=True)
class Empfaenger:
    id: str
    typ: str
    ziel: str
    name: str = ""
    severity_payload: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "typ": self.typ,
            "ziel": self.ziel,
            "name": self.name,
            "severity_payload": dict(self.severity_payload),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Empfaenger":
        return cls(
            id=data["id"],
            typ=data["typ"],
            ziel=data["ziel"],
            name=data.get("name", ""),
            severity_payload=dict(data.get("severity_payload", {})),
        )


@dataclass(slots=True)
class HistoryEintrag:
    id: str
    zeitstempel: str
    topic: str
    severity: str
    titel: str
    message: str = ""
    aufgeloste_rollen: list[str] = field(default_factory=list)
    aufgeloste_empfaenger: list[str] = field(default_factory=list)
    ausliefer_status: dict[str, str] = field(default_factory=dict)
    actions: list[dict[str, Any]] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    fallback_verwendet: bool = False
    quelle_context: dict[str, Any] = field(default_factory=dict)
    interruption_level: str | None = None  # effektiv von Herold gesetzt (Topic/Call)
    interruption_level_quelle: str | None = None  # "call" | "topic" | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "zeitstempel": self.zeitstempel,
            "topic": self.topic,
            "severity": self.severity,
            "titel": self.titel,
            "message": self.message,
            "aufgeloste_rollen": list(self.aufgeloste_rollen),
            "aufgeloste_empfaenger": list(self.aufgeloste_empfaenger),
            "ausliefer_status": dict(self.ausliefer_status),
            "actions": list(self.actions),
            "payload": dict(self.payload),
            "fallback_verwendet": self.fallback_verwendet,
            "quelle_context": dict(self.quelle_context),
            "interruption_level": self.interruption_level,
            "interruption_level_quelle": self.interruption_level_quelle,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HistoryEintrag":
        return cls(
            id=data["id"],
            zeitstempel=data["zeitstempel"],
            topic=data["topic"],
            severity=data["severity"],
            titel=data["titel"],
            message=data.get("message", ""),
            aufgeloste_rollen=list(data.get("aufgeloste_rollen", [])),
            aufgeloste_empfaenger=list(data.get("aufgeloste_empfaenger", [])),
            ausliefer_status=dict(data.get("ausliefer_status", {})),
            actions=list(data.get("actions", [])),
            payload=dict(data.get("payload", {})),
            fallback_verwendet=data.get("fallback_verwendet", False),
            quelle_context=dict(data.get("quelle_context", {})),
            interruption_level=data.get("interruption_level"),
            interruption_level_quelle=data.get("interruption_level_quelle"),
        )

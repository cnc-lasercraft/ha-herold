"""Config- und Options-Flow für Herold.

Phase 1: Setup-Flow (single instance) + Options-Flow-Menu.
Phase 2a/b/c: Topics-CRUD.

Rollen/Empfänger/Mapping/Einstellungen folgen in weiteren Phasen.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    DOMAIN,
    EMPF_TYP_NOTIFY,
    EMPF_TYPEN,
    SEVERITIES,
    SEVERITY_DEFAULT,
    TOPIC_REGEX,
)
from .models import Empfaenger, Rolle, Topic
from .store import HeroldConfigStore

_NEU = "__neu__"
_ID_REGEX_HINT = "Kleinbuchstaben, Ziffern, Unterstrich"


class HeroldConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einfacher Setup-Flow — genau ein Entry pro HA-Instanz."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="Herold", data={})
        return self.async_show_form(step_id="user")

    async def async_step_import(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        return self.async_create_entry(title="Herold", data={})

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HeroldOptionsFlow()


class HeroldOptionsFlow(OptionsFlow):
    """Options-Flow für Verwaltung.

    Kein eigener __init__: `self.config_entry` wird ab HA 2024.11 automatisch
    vom Framework gesetzt (read-only Property in der Basisklasse).
    """

    _edit_topic_id: str | None = None  # None → "neues Topic"
    _edit_rolle_id: str | None = None
    _edit_empfaenger_id: str | None = None
    _edit_mapping_topic: str | None = None

    # ------------------------------------------------------------------
    # Hauptmenu
    # ------------------------------------------------------------------

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "topics",
                "rollen",
                "empfaenger",
                "mapping",
                "einstellungen",
            ],
        )

    # ------------------------------------------------------------------
    # Topics — Liste / Auswahl
    # ------------------------------------------------------------------

    async def async_step_topics(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        store = self._store()

        if user_input is not None:
            auswahl = user_input["topic"]
            self._edit_topic_id = None if auswahl == _NEU else auswahl
            return await self.async_step_topic_edit()

        optionen: list[SelectOptionDict] = [
            {"value": _NEU, "label": "➕ Neues Topic anlegen"}
        ]
        for tid, topic in sorted(store.topics.items()):
            flags = []
            if topic.log_only:
                flags.append("log_only")
            if not topic.explizit_registriert:
                flags.append("implizit")
            suffix = f" [{', '.join(flags)}]" if flags else ""
            label = f"{tid} — {topic.name or '—'}{suffix}"
            optionen.append({"value": tid, "label": label})

        return self.async_show_form(
            step_id="topics",
            data_schema=vol.Schema(
                {
                    vol.Required("topic"): SelectSelector(
                        SelectSelectorConfig(
                            options=optionen,
                            mode=SelectSelectorMode.DROPDOWN,
                            custom_value=False,
                        )
                    )
                }
            ),
            description_placeholders={"anzahl": str(len(store.topics))},
        )

    # ------------------------------------------------------------------
    # Topic — Edit/Create/Delete
    # ------------------------------------------------------------------

    async def async_step_topic_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        store = self._store()
        is_new = self._edit_topic_id is None
        topic = None if is_new else store.topics.get(self._edit_topic_id)

        if not is_new and topic is None:
            return self.async_abort(reason="topic_not_found")

        errors: dict[str, str] = {}

        if user_input is not None:
            # Löschen (nur Edit-Mode)
            if not is_new and user_input.get("_loeschen"):
                assert self._edit_topic_id is not None
                store.topics.pop(self._edit_topic_id, None)
                store.topic_rolle_mapping.pop(self._edit_topic_id, None)
                await self._save()
                return self.async_create_entry(title="", data={})

            # Topic-ID validieren (nur bei Neu)
            if is_new:
                tid = (user_input.get("id") or "").strip()
                if not tid:
                    errors["id"] = "required"
                elif not TOPIC_REGEX.match(tid):
                    errors["id"] = "invalid_topic_id"
                elif tid in store.topics:
                    errors["id"] = "topic_exists"
            else:
                assert self._edit_topic_id is not None
                tid = self._edit_topic_id

            if not errors:
                if is_new:
                    topic = Topic(id=tid, explizit_registriert=True)
                    store.topics[tid] = topic
                assert topic is not None
                topic.name = user_input.get("name", "") or tid
                topic.beschreibung = user_input.get("beschreibung", "")
                topic.quelle = user_input.get("quelle", "")
                topic.default_severity = user_input.get(
                    "default_severity", SEVERITY_DEFAULT
                )
                topic.default_rollen = list(user_input.get("default_rollen", []))
                topic.log_only = bool(user_input.get("log_only", False))
                topic.explizit_registriert = True
                await self._save()
                return self.async_create_entry(title="", data={})

        # Form anzeigen (initial oder nach Validierungsfehler)
        rollen_optionen = [
            {"value": rid, "label": f"{rid} — {r.name or '—'} ({len(r.mitglieder)} Mitgl.)"}
            for rid, r in sorted(store.rollen.items())
        ]

        def _last(key: str, default: Any) -> Any:
            if user_input is not None and key in user_input:
                return user_input[key]
            return getattr(topic, key) if topic else default

        schema_dict: dict[Any, Any] = {}
        if is_new:
            schema_dict[vol.Required("id", default=_last("id", ""))] = TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            )
        schema_dict[vol.Optional("name", default=_last("name", ""))] = TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        )
        schema_dict[
            vol.Optional("beschreibung", default=_last("beschreibung", ""))
        ] = TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT, multiline=True))
        schema_dict[vol.Optional("quelle", default=_last("quelle", ""))] = TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        )
        schema_dict[
            vol.Required(
                "default_severity", default=_last("default_severity", SEVERITY_DEFAULT)
            )
        ] = SelectSelector(
            SelectSelectorConfig(
                options=list(SEVERITIES),
                mode=SelectSelectorMode.DROPDOWN,
                translation_key="severity",
            )
        )
        schema_dict[
            vol.Optional("default_rollen", default=list(_last("default_rollen", [])))
        ] = SelectSelector(
            SelectSelectorConfig(
                options=rollen_optionen,
                mode=SelectSelectorMode.DROPDOWN,
                multiple=True,
            )
        )
        schema_dict[
            vol.Optional("log_only", default=bool(_last("log_only", False)))
        ] = BooleanSelector()
        if not is_new:
            schema_dict[vol.Optional("_loeschen", default=False)] = BooleanSelector()

        return self.async_show_form(
            step_id="topic_edit",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "topic_id": self._edit_topic_id or "(neu)",
                "modus": "Neu" if is_new else "Bearbeiten",
            },
        )

    # ------------------------------------------------------------------
    # Rollen — Liste / Edit / Delete
    # ------------------------------------------------------------------

    async def async_step_rollen(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        store = self._store()

        if user_input is not None:
            auswahl = user_input["rolle"]
            self._edit_rolle_id = None if auswahl == _NEU else auswahl
            return await self.async_step_rolle_edit()

        optionen: list[SelectOptionDict] = [
            {"value": _NEU, "label": "➕ Neue Rolle anlegen"}
        ]
        for rid, rolle in sorted(store.rollen.items()):
            fallback = " [Fallback]" if rid == store.fallback_rolle else ""
            label = f"{rid} — {rolle.name or '—'} ({len(rolle.mitglieder)} Mitgl.){fallback}"
            optionen.append({"value": rid, "label": label})

        return self.async_show_form(
            step_id="rollen",
            data_schema=vol.Schema(
                {
                    vol.Required("rolle"): SelectSelector(
                        SelectSelectorConfig(
                            options=optionen,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            description_placeholders={"anzahl": str(len(store.rollen))},
        )

    async def async_step_rolle_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        store = self._store()
        is_new = self._edit_rolle_id is None
        rolle = None if is_new else store.rollen.get(self._edit_rolle_id)

        if not is_new and rolle is None:
            return self.async_abort(reason="rolle_not_found")

        errors: dict[str, str] = {}

        if user_input is not None:
            if not is_new and user_input.get("_loeschen"):
                assert self._edit_rolle_id is not None
                # Gleiche Bereinigung wie Service
                rid = self._edit_rolle_id
                store.rollen.pop(rid, None)
                for t in store.topics.values():
                    if rid in t.default_rollen:
                        t.default_rollen = [r for r in t.default_rollen if r != rid]
                for tid, rollen in list(store.topic_rolle_mapping.items()):
                    neue = [r for r in rollen if r != rid]
                    if neue:
                        store.topic_rolle_mapping[tid] = neue
                    else:
                        store.topic_rolle_mapping.pop(tid, None)
                if store.fallback_rolle == rid:
                    store.fallback_rolle = None
                await self._save()
                return self.async_create_entry(title="", data={})

            if is_new:
                rid = (user_input.get("id") or "").strip()
                if not rid:
                    errors["id"] = "required"
                elif rid in store.rollen:
                    errors["id"] = "rolle_exists"
            else:
                assert self._edit_rolle_id is not None
                rid = self._edit_rolle_id

            if not errors:
                if is_new:
                    rolle = Rolle(id=rid)
                    store.rollen[rid] = rolle
                    if store.fallback_rolle is None:
                        store.fallback_rolle = rid
                assert rolle is not None
                rolle.name = user_input.get("name", "") or rid
                rolle.mitglieder = list(user_input.get("mitglieder", []))
                await self._save()
                return self.async_create_entry(title="", data={})

        empfaenger_optionen = [
            {"value": eid, "label": f"{eid} — {e.name or '—'} ({e.ziel})"}
            for eid, e in sorted(store.empfaenger.items())
        ]

        def _last(key: str, default: Any) -> Any:
            if user_input is not None and key in user_input:
                return user_input[key]
            return getattr(rolle, key) if rolle else default

        schema_dict: dict[Any, Any] = {}
        if is_new:
            schema_dict[vol.Required("id", default=_last("id", ""))] = TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            )
        schema_dict[vol.Optional("name", default=_last("name", ""))] = TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        )
        schema_dict[
            vol.Optional("mitglieder", default=list(_last("mitglieder", [])))
        ] = SelectSelector(
            SelectSelectorConfig(
                options=empfaenger_optionen,
                mode=SelectSelectorMode.DROPDOWN,
                multiple=True,
            )
        )
        if not is_new:
            schema_dict[vol.Optional("_loeschen", default=False)] = BooleanSelector()

        return self.async_show_form(
            step_id="rolle_edit",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "rolle_id": self._edit_rolle_id or "(neu)",
                "modus": "Neu" if is_new else "Bearbeiten",
            },
        )

    # ------------------------------------------------------------------
    # Empfänger — Liste / Edit / Delete
    # ------------------------------------------------------------------

    async def async_step_empfaenger(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        store = self._store()

        if user_input is not None:
            auswahl = user_input["empfaenger"]
            self._edit_empfaenger_id = None if auswahl == _NEU else auswahl
            return await self.async_step_empfaenger_edit()

        optionen: list[SelectOptionDict] = [
            {"value": _NEU, "label": "➕ Neuen Empfänger anlegen"}
        ]
        for eid, e in sorted(store.empfaenger.items()):
            label = f"{eid} — {e.name or '—'} ({e.typ}: {e.ziel})"
            optionen.append({"value": eid, "label": label})

        return self.async_show_form(
            step_id="empfaenger",
            data_schema=vol.Schema(
                {
                    vol.Required("empfaenger"): SelectSelector(
                        SelectSelectorConfig(
                            options=optionen,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            description_placeholders={"anzahl": str(len(store.empfaenger))},
        )

    async def async_step_empfaenger_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        store = self._store()
        is_new = self._edit_empfaenger_id is None
        empf = None if is_new else store.empfaenger.get(self._edit_empfaenger_id)

        if not is_new and empf is None:
            return self.async_abort(reason="empfaenger_not_found")

        errors: dict[str, str] = {}

        if user_input is not None:
            if not is_new and user_input.get("_loeschen"):
                assert self._edit_empfaenger_id is not None
                eid = self._edit_empfaenger_id
                store.empfaenger.pop(eid, None)
                for r in store.rollen.values():
                    if eid in r.mitglieder:
                        r.mitglieder = [m for m in r.mitglieder if m != eid]
                await self._save()
                return self.async_create_entry(title="", data={})

            if is_new:
                eid = (user_input.get("id") or "").strip()
                if not eid:
                    errors["id"] = "required"
                elif eid in store.empfaenger:
                    errors["id"] = "empfaenger_exists"
            else:
                assert self._edit_empfaenger_id is not None
                eid = self._edit_empfaenger_id

            ziel = (user_input.get("ziel") or "").strip()
            if not ziel or "." not in ziel:
                errors["ziel"] = "invalid_ziel"

            if not errors:
                if is_new:
                    empf = Empfaenger(
                        id=eid,
                        typ=user_input.get("typ", EMPF_TYP_NOTIFY),
                        ziel=ziel,
                    )
                    store.empfaenger[eid] = empf
                assert empf is not None
                empf.typ = user_input.get("typ", EMPF_TYP_NOTIFY)
                empf.ziel = ziel
                empf.name = user_input.get("name", "") or eid
                await self._save()
                return self.async_create_entry(title="", data={})

        def _last(key: str, default: Any) -> Any:
            if user_input is not None and key in user_input:
                return user_input[key]
            return getattr(empf, key) if empf else default

        schema_dict: dict[Any, Any] = {}
        if is_new:
            schema_dict[vol.Required("id", default=_last("id", ""))] = TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            )
        schema_dict[
            vol.Required("typ", default=_last("typ", EMPF_TYP_NOTIFY))
        ] = SelectSelector(
            SelectSelectorConfig(
                options=list(EMPF_TYPEN),
                mode=SelectSelectorMode.DROPDOWN,
            )
        )
        schema_dict[vol.Required("ziel", default=_last("ziel", ""))] = TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        )
        schema_dict[vol.Optional("name", default=_last("name", ""))] = TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        )
        if not is_new:
            schema_dict[vol.Optional("_loeschen", default=False)] = BooleanSelector()

        return self.async_show_form(
            step_id="empfaenger_edit",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={
                "empfaenger_id": self._edit_empfaenger_id or "(neu)",
                "modus": "Neu" if is_new else "Bearbeiten",
            },
        )

    # ------------------------------------------------------------------
    # Topic → Rollen-Mapping (Admin-Override)
    # ------------------------------------------------------------------

    async def async_step_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        store = self._store()

        if not store.topics:
            return self.async_abort(reason="keine_topics")

        if user_input is not None:
            self._edit_mapping_topic = user_input["topic"]
            return await self.async_step_mapping_edit()

        optionen: list[SelectOptionDict] = []
        for tid, topic in sorted(store.topics.items()):
            rollen = store.topic_rolle_mapping.get(tid)
            if rollen is not None:
                suffix = f" [Override: {', '.join(rollen) or 'keine'}]"
            elif topic.default_rollen:
                suffix = f" [Default: {', '.join(topic.default_rollen)}]"
            else:
                suffix = " [keine Rollen]"
            optionen.append({"value": tid, "label": f"{tid}{suffix}"})

        return self.async_show_form(
            step_id="mapping",
            data_schema=vol.Schema(
                {
                    vol.Required("topic"): SelectSelector(
                        SelectSelectorConfig(
                            options=optionen,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_mapping_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        store = self._store()
        tid = self._edit_mapping_topic
        if tid is None or tid not in store.topics:
            return self.async_abort(reason="topic_not_found")

        if user_input is not None:
            if user_input.get("_zuruecksetzen"):
                store.topic_rolle_mapping.pop(tid, None)
            else:
                rollen = list(user_input.get("rollen", []))
                if rollen:
                    store.topic_rolle_mapping[tid] = rollen
                else:
                    store.topic_rolle_mapping.pop(tid, None)
            await self._save()
            return self.async_create_entry(title="", data={})

        rollen_optionen = [
            {"value": rid, "label": f"{rid} — {r.name or '—'}"}
            for rid, r in sorted(store.rollen.items())
        ]
        aktuell = store.topic_rolle_mapping.get(tid, list(store.topics[tid].default_rollen))

        schema = vol.Schema(
            {
                vol.Optional("rollen", default=list(aktuell)): SelectSelector(
                    SelectSelectorConfig(
                        options=rollen_optionen,
                        mode=SelectSelectorMode.DROPDOWN,
                        multiple=True,
                    )
                ),
                vol.Optional("_zuruecksetzen", default=False): BooleanSelector(),
            }
        )

        producer_default = ", ".join(store.topics[tid].default_rollen) or "(keine)"
        return self.async_show_form(
            step_id="mapping_edit",
            data_schema=schema,
            description_placeholders={
                "topic_id": tid,
                "producer_default": producer_default,
            },
        )

    # ------------------------------------------------------------------
    # Einstellungen — Fallback-Rolle + Retention-Grenzen
    # ------------------------------------------------------------------

    async def async_step_einstellungen(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        store = self._store()

        if user_input is not None:
            fb = user_input.get("fallback_rolle") or None
            if fb == "__keine__":
                fb = None
            if fb and fb not in store.rollen:
                return self.async_show_form(
                    step_id="einstellungen",
                    data_schema=self._einstellungen_schema(store, user_input),
                    errors={"fallback_rolle": "rolle_unbekannt"},
                )
            store.fallback_rolle = fb
            store.retention_eintraege = int(user_input["retention_eintraege"])
            store.retention_tage = int(user_input["retention_tage"])
            await self._save()
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="einstellungen",
            data_schema=self._einstellungen_schema(store, None),
        )

    def _einstellungen_schema(
        self, store: HeroldConfigStore, user_input: dict[str, Any] | None
    ) -> vol.Schema:
        rollen_optionen: list[SelectOptionDict] = [
            {"value": "__keine__", "label": "— keine Fallback-Rolle —"}
        ]
        for rid, r in sorted(store.rollen.items()):
            rollen_optionen.append(
                {"value": rid, "label": f"{rid} — {r.name or '—'}"}
            )

        def _last(key: str, default: Any) -> Any:
            if user_input is not None and key in user_input:
                return user_input[key]
            return default

        aktueller_fb = _last("fallback_rolle", store.fallback_rolle or "__keine__")
        return vol.Schema(
            {
                vol.Required("fallback_rolle", default=aktueller_fb): SelectSelector(
                    SelectSelectorConfig(
                        options=rollen_optionen,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    "retention_eintraege",
                    default=int(_last("retention_eintraege", store.retention_eintraege)),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100000)),
                vol.Required(
                    "retention_tage",
                    default=int(_last("retention_tage", store.retention_tage)),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=3650)),
            }
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _store(self) -> HeroldConfigStore:
        return self.hass.data[DOMAIN]["config_store"]

    async def _save(self) -> None:
        """Save + EVENT_CONFIG_UPDATED (damit Admin-Card/Sensoren aktualisieren)."""
        await self.hass.data[DOMAIN]["save_and_notify"]("options_flow")

"""Config flow for Notifier integration."""
from __future__ import annotations

import logging
import uuid
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    ACTION_SEND_TO_ABSENT,
    ACTION_SEND_TO_ALL,
    ACTION_SEND_TO_NEAREST,
    ACTION_SEND_TO_PRESENT,
    CONF_ALWAYS_HOME_DEVICES,
    CONF_CONSUMPTION_MONITORS,
    MON_COOLDOWN,
    MON_DAYS,
    MON_ENERGY_SOURCE,
    MON_ENTITY,
    MON_FACTOR,
    MON_HOURS,
    MON_ID,
    MON_NAME,
    MON_RULE,
    MON_TARGET,
    MON_THRESHOLD,
    MON_TIME,
    MON_TYPE,
    MON_WINDOW,
    CONF_DEVICE_NAME,
    CONF_DISTANCE_SENSOR,
    CONF_NOTIFICATION_SERVICE,
    CONF_OCCUPANCY_PERSONS,
    CONF_OCCUPANCY_SENSOR_NAME,
    CONF_PERSON_ID,
    CONF_PERSON_NAME,
    CONF_PERSONS,
    CONF_PROXIMITY_THRESHOLD,
    DEFAULT_OCCUPANCY_SENSOR_NAME,
    DEFAULT_PROXIMITY_THRESHOLD,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

LABELS = {
    "fr": {
        "manage_action": {"edit": "Modifier", "delete": "Supprimer"},
        "energy_kind": {"grid": "Réseau", "gas": "Gaz", "water": "Eau", "device": "Appareil"},
        "consumption_type": {
            "cumulative": "Compteur cumulatif (kWh, m³, L)",
            "instant": "Valeur instantanée (W, L/min)",
        },
        "consumption_rule": {
            "threshold": "Seuil sur une fenêtre de temps",
            "continuous": "Débit continu (fuite possible)",
            "slow_leak": "Fuite lente (consommation à chaque heure)",
            "habit": "Inhabituel par rapport aux heures habituelles",
        },
        "target": {
            ACTION_SEND_TO_ALL: "Tout le monde (personnes et appareils)",
            ACTION_SEND_TO_PRESENT: "Personnes à la maison",
            ACTION_SEND_TO_ABSENT: "Personnes absentes",
            ACTION_SEND_TO_NEAREST: "Personne la plus proche",
        },
    },
    "en": {
        "manage_action": {"edit": "Edit", "delete": "Delete"},
        "energy_kind": {"grid": "Grid", "gas": "Gas", "water": "Water", "device": "Device"},
        "consumption_type": {
            "cumulative": "Cumulative meter (kWh, m³, L)",
            "instant": "Instant value (W, L/min)",
        },
        "consumption_rule": {
            "threshold": "Threshold over a time window",
            "continuous": "Continuous flow (possible leak)",
            "slow_leak": "Slow leak (consumption every hour)",
            "habit": "Unusual compared to usual hours",
        },
        "target": {
            ACTION_SEND_TO_ALL: "Everyone (persons and devices)",
            ACTION_SEND_TO_PRESENT: "Persons at home",
            ACTION_SEND_TO_ABSENT: "Persons away",
            ACTION_SEND_TO_NEAREST: "Nearest person",
        },
    },
}


def _options(hass: HomeAssistant, group: str, values: list[str]) -> list[selector.SelectOptionDict]:
    """Labelled options. Built here because the options-flow dialog does not load selector translations."""
    labels = LABELS["fr" if hass.config.language.startswith("fr") else "en"][group]
    return [selector.SelectOptionDict(value=v, label=labels[v]) for v in values]


async def _energy_sources(hass: HomeAssistant) -> list[selector.SelectOptionDict]:
    """Consumption sources of the Energy dashboard that are real entities (name picked from it)."""
    try:
        # Imported lazily: the energy integration is optional.
        from homeassistant.components.energy.data import async_get_manager

        prefs = (await async_get_manager(hass)).data or {}
    except Exception:  # noqa: BLE001 - no energy dashboard: only manual entry is offered
        return []

    found: list[tuple[str | None, str]] = []
    for src in prefs.get("energy_sources", []):
        kind = src.get("type")
        if kind == "grid":
            # Stored flat (stat_energy_from); older/newer layouts use a flow_from list.
            found.append((src.get("stat_energy_from"), "grid"))
            found += [(f.get("stat_energy_from"), "grid") for f in src.get("flow_from", [])]
        elif kind in ("gas", "water"):
            found.append((src.get("stat_energy_from"), kind))
    found += [(d.get("stat_consumption"), "device") for d in prefs.get("device_consumption", [])]

    kinds = LABELS["fr" if hass.config.language.startswith("fr") else "en"]["energy_kind"]
    options: list[selector.SelectOptionDict] = []
    seen: set[str] = set()
    for stat_id, kind in found:
        state = hass.states.get(stat_id) if stat_id else None
        if state is None or stat_id in seen:  # external statistics are not entities
            continue
        seen.add(stat_id)
        options.append(
            selector.SelectOptionDict(value=stat_id, label=f"{kinds[kind]} – {state.name}")
        )
    return options


def _notify_selector(hass: HomeAssistant) -> selector.SelectSelector:
    """Dropdown of existing notify services; custom value still allowed."""
    options = [
        f"notify.{name}"
        for name in sorted(hass.services.async_services().get("notify", {}))
        if name not in ("send_message", "persistent_notification")
    ]
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            custom_value=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


# Durations are entered as hours/minutes/seconds. Stored value = minutes / divisor
# (so existing numeric options keep working).
DURATION_KEYS = {MON_WINDOW: 1, MON_HOURS: 60, MON_COOLDOWN: 1}

# (key, default, spec): spec dict = number selector kwargs, None = duration (default in
# minutes), "time" = time of day.
RULE_FIELDS: dict[str, list[tuple[str, Any, dict[str, Any] | str | None]]] = {
    "threshold": [
        (MON_THRESHOLD, None, {"min": 0, "step": "any"}),
        (MON_WINDOW, 60, None),
        (MON_COOLDOWN, 60, None),
    ],
    "continuous": [
        (MON_HOURS, 360, None),
        (MON_COOLDOWN, 60, None),
    ],
    "slow_leak": [
        (MON_HOURS, 360, None),
        (MON_COOLDOWN, 360, None),
    ],
    # Checked once a day over 24 h: compared with the average of the previous days.
    "habit": [
        (MON_TIME, "08:00:00", "time"),
        (MON_DAYS, 7, {"min": 3, "max": 60, "step": 1}),
        (MON_FACTOR, 1.5, {"min": 1, "step": "any"}),
    ],
}


def _req(m: dict[str, Any], key: str, default: Any = None) -> vol.Required:
    """Required key prefilled from m, else from default (no default when both are None)."""
    value = m.get(key, default)
    return vol.Required(key, default=value) if value is not None else vol.Required(key)


def _duration_field(m: dict[str, Any], key: str, default_minutes: float) -> tuple[vol.Required, Any]:
    stored = m.get(key)
    minutes = stored * DURATION_KEYS[key] if stored is not None else default_minutes
    total = int(round(minutes * 60))
    default = {"hours": total // 3600, "minutes": total % 3600 // 60, "seconds": total % 60}
    return (
        vol.Required(key, default=default),
        selector.DurationSelector(selector.DurationSelectorConfig(enable_day=False)),
    )


def _store_durations(user_input: dict[str, Any]) -> dict[str, Any]:
    """Turn duration dicts from the form into the stored numbers."""
    out = dict(user_input)
    for key, divisor in DURATION_KEYS.items():
        d = out.get(key)
        if isinstance(d, dict):
            minutes = d.get("hours", 0) * 60 + d.get("minutes", 0) + d.get("seconds", 0) / 60
            out[key] = minutes / divisor
    return out


def _number(**kwargs: Any) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX, **kwargs)
    )


def _choice(
    hass: HomeAssistant, group: str, values: list[str], **kwargs: Any
) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=_options(hass, group, values),
            mode=selector.SelectSelectorMode.DROPDOWN,
            **kwargs,
        )
    )


class NotifierConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Notifier."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {
            CONF_PERSONS: [],
            CONF_ALWAYS_HOME_DEVICES: [],
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_menu()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_OCCUPANCY_SENSOR_NAME, default=DEFAULT_OCCUPANCY_SENSOR_NAME
                ): selector.TextSelector(),
                vol.Required(
                    CONF_PROXIMITY_THRESHOLD, default=DEFAULT_PROXIMITY_THRESHOLD
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=100000, step=50, unit_of_measurement="m"
                    )
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle configuration menu."""
        return self.async_show_menu(
            step_id="menu",
            menu_options=["add_person", "add_device", "finish"],
        )

    async def async_step_add_person(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a person to configuration."""
        if user_input is not None:
            self._data[CONF_PERSONS].append(user_input)
            return await self.async_step_menu()

        schema = vol.Schema(
            {
                vol.Required(CONF_PERSON_NAME): selector.TextSelector(),
                vol.Required(CONF_PERSON_ID): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["person", "device_tracker"])
                ),
                vol.Required(CONF_NOTIFICATION_SERVICE): _notify_selector(self.hass),
                vol.Optional(CONF_DISTANCE_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
            }
        )

        return self.async_show_form(step_id="add_person", data_schema=schema)

    async def async_step_add_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add an always home device to configuration."""
        if user_input is not None:
            self._data[CONF_ALWAYS_HOME_DEVICES].append(user_input)
            return await self.async_step_menu()

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_NAME): selector.TextSelector(),
                vol.Required(CONF_NOTIFICATION_SERVICE): _notify_selector(self.hass),
            }
        )

        return self.async_show_form(step_id="add_device", data_schema=schema)

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Finish setup and create entry."""
        return self.async_create_entry(
            title="Notifier",
            data=self._data,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return NotifierOptionsFlow(config_entry)


class NotifierOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Notifier."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow (config_entry is a read-only property on recent HA)."""
        self._options: dict[str, Any] = dict(config_entry.data)
        if config_entry.options:
            self._options.update(config_entry.options)
        # Copy lists so editing never mutates the stored entry in place.
        self._options[CONF_PERSONS] = list(self._options.get(CONF_PERSONS, []))
        self._options[CONF_ALWAYS_HOME_DEVICES] = list(
            self._options.get(CONF_ALWAYS_HOME_DEVICES, [])
        )
        self._selected_item_index: int | None = None
        self._draft: dict[str, Any] = {}  # monitor being added/edited (common part)
        self._source: dict[str, Any] = {}  # its stored values, used as form defaults

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "general_settings",
                "add_person",
                "manage_persons",
                "add_device",
                "manage_devices",
                "add_monitor",
                "manage_monitors",
                "finish",
            ],
        )

    async def async_step_general_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit general settings and which persons the occupancy sensor covers."""
        names = [
            p[CONF_PERSON_NAME]
            for p in self._options.get(CONF_PERSONS, [])
            if p.get(CONF_PERSON_NAME)
        ]
        if user_input is not None:
            self._options.update(user_input)
            # An emptied multi-select is absent from user_input: store the explicit list.
            self._options[CONF_OCCUPANCY_PERSONS] = [
                n for n in user_input.get(CONF_OCCUPANCY_PERSONS, []) if n in names
            ]
            return await self.async_step_init()

        # No stored list yet = every person counts, so show them all selected.
        stored = self._options.get(CONF_OCCUPANCY_PERSONS)
        selected = names if stored is None else [n for n in stored if n in names]

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_OCCUPANCY_SENSOR_NAME,
                    default=self._options.get(
                        CONF_OCCUPANCY_SENSOR_NAME, DEFAULT_OCCUPANCY_SENSOR_NAME
                    ),
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_OCCUPANCY_PERSONS, description={"suggested_value": selected}
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=names,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_PROXIMITY_THRESHOLD,
                    default=self._options.get(
                        CONF_PROXIMITY_THRESHOLD, DEFAULT_PROXIMITY_THRESHOLD
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=100000, step=50, unit_of_measurement="m"
                    )
                ),
            }
        )

        return self.async_show_form(step_id="general_settings", data_schema=schema)

    def _sync_occupancy_persons(self, old: str | None, new: str | None) -> None:
        """Keep the occupancy selection coherent when a person is added, renamed or removed."""
        stored = self._options.get(CONF_OCCUPANCY_PERSONS)
        if stored is None:
            return  # no explicit list: everyone counts, nothing to sync
        stored = [n for n in stored if n != old]
        if new:
            stored.append(new)
        self._options[CONF_OCCUPANCY_PERSONS] = stored

    async def async_step_add_person(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a person."""
        if user_input is not None:
            persons = list(self._options.get(CONF_PERSONS, []))
            persons.append(user_input)
            self._options[CONF_PERSONS] = persons
            self._sync_occupancy_persons(None, user_input.get(CONF_PERSON_NAME))
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(CONF_PERSON_NAME): selector.TextSelector(),
                vol.Required(CONF_PERSON_ID): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["person", "device_tracker"])
                ),
                vol.Required(CONF_NOTIFICATION_SERVICE): _notify_selector(self.hass),
                vol.Optional(CONF_DISTANCE_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
            }
        )

        return self.async_show_form(step_id="add_person", data_schema=schema)

    async def async_step_manage_persons(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select a person to edit or remove."""
        persons = self._options.get(CONF_PERSONS, [])
        if not persons:
            return self.async_show_menu(
                step_id="manage_persons",
                menu_options=["add_person", "init"],
            )

        if user_input is not None:
            idx = int(user_input["person_index"])
            if user_input.get("action") == "delete":
                removed = persons.pop(idx)
                self._options[CONF_PERSONS] = persons
                self._sync_occupancy_persons(removed.get(CONF_PERSON_NAME), None)
                return await self.async_step_init()
            # Edit
            self._selected_item_index = idx
            return await self.async_step_edit_person()

        person_options = [
            selector.SelectOptionDict(
                value=str(i),
                label=f"{p.get(CONF_PERSON_NAME)} ({p.get(CONF_PERSON_ID)})",
            )
            for i, p in enumerate(persons)
        ]

        schema = vol.Schema(
            {
                vol.Required("person_index"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=person_options)
                ),
                vol.Required("action", default="edit"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=_options(self.hass, "manage_action", ["edit", "delete"])
                    )
                ),
            }
        )

        return self.async_show_form(step_id="manage_persons", data_schema=schema)

    async def async_step_edit_person(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit an existing person."""
        idx = self._selected_item_index
        persons = self._options.get(CONF_PERSONS, [])
        if idx is None or idx >= len(persons):
            return await self.async_step_init()

        person = persons[idx]

        if user_input is not None:
            old_name = person.get(CONF_PERSON_NAME)
            persons[idx] = user_input
            self._options[CONF_PERSONS] = persons
            if old_name != user_input.get(CONF_PERSON_NAME):
                self._sync_occupancy_persons(old_name, user_input.get(CONF_PERSON_NAME))
            self._selected_item_index = None
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PERSON_NAME, default=person.get(CONF_PERSON_NAME, "")
                ): selector.TextSelector(),
                vol.Required(
                    CONF_PERSON_ID, default=person.get(CONF_PERSON_ID, "")
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["person", "device_tracker"])
                ),
                vol.Required(
                    CONF_NOTIFICATION_SERVICE,
                    default=person.get(CONF_NOTIFICATION_SERVICE, ""),
                ): _notify_selector(self.hass),
                vol.Optional(
                    CONF_DISTANCE_SENSOR,
                    description={
                        "suggested_value": person.get(CONF_DISTANCE_SENSOR)
                    },
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
            }
        )

        return self.async_show_form(step_id="edit_person", data_schema=schema)

    async def async_step_add_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add an always home device."""
        if user_input is not None:
            devices = list(self._options.get(CONF_ALWAYS_HOME_DEVICES, []))
            devices.append(user_input)
            self._options[CONF_ALWAYS_HOME_DEVICES] = devices
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_NAME): selector.TextSelector(),
                vol.Required(CONF_NOTIFICATION_SERVICE): _notify_selector(self.hass),
            }
        )

        return self.async_show_form(step_id="add_device", data_schema=schema)

    async def async_step_manage_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select a device to edit or remove."""
        devices = self._options.get(CONF_ALWAYS_HOME_DEVICES, [])
        if not devices:
            return self.async_show_menu(
                step_id="manage_devices",
                menu_options=["add_device", "init"],
            )

        if user_input is not None:
            idx = int(user_input["device_index"])
            if user_input.get("action") == "delete":
                devices.pop(idx)
                self._options[CONF_ALWAYS_HOME_DEVICES] = devices
                return await self.async_step_init()
            # Edit
            self._selected_item_index = idx
            return await self.async_step_edit_device()

        device_options = [
            selector.SelectOptionDict(
                value=str(i),
                label=f"{d.get(CONF_DEVICE_NAME)} ({d.get(CONF_NOTIFICATION_SERVICE)})",
            )
            for i, d in enumerate(devices)
        ]

        schema = vol.Schema(
            {
                vol.Required("device_index"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=device_options)
                ),
                vol.Required("action", default="edit"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=_options(self.hass, "manage_action", ["edit", "delete"])
                    )
                ),
            }
        )

        return self.async_show_form(step_id="manage_devices", data_schema=schema)

    async def async_step_edit_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit an existing device."""
        idx = self._selected_item_index
        devices = self._options.get(CONF_ALWAYS_HOME_DEVICES, [])
        if idx is None or idx >= len(devices):
            return await self.async_step_init()

        device = devices[idx]

        if user_input is not None:
            devices[idx] = user_input
            self._options[CONF_ALWAYS_HOME_DEVICES] = devices
            self._selected_item_index = None
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DEVICE_NAME, default=device.get(CONF_DEVICE_NAME, "")
                ): selector.TextSelector(),
                vol.Required(
                    CONF_NOTIFICATION_SERVICE,
                    default=device.get(CONF_NOTIFICATION_SERVICE, ""),
                ): _notify_selector(self.hass),
            }
        )

        return self.async_show_form(step_id="edit_device", data_schema=schema)

    def _common_schema(
        self, m: dict[str, Any], energy: list[selector.SelectOptionDict]
    ) -> vol.Schema:
        """Fields shared by every rule. Source: Energy dashboard list or any sensor."""
        source: dict[Any, Any] = {}
        if energy:
            source[vol.Optional(MON_ENERGY_SOURCE)] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=energy, mode=selector.SelectSelectorMode.DROPDOWN
                )
            )
        source[
            vol.Optional(MON_ENTITY, description={"suggested_value": m.get(MON_ENTITY)})
        ] = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
        return vol.Schema(
            {
                _req(m, MON_NAME): selector.TextSelector(),
                **source,
                _req(m, MON_TYPE, "cumulative"): _choice(
                    self.hass, "consumption_type", ["cumulative", "instant"]
                ),
                _req(m, MON_RULE, "threshold"): _choice(
                    self.hass, "consumption_rule", list(RULE_FIELDS)
                ),
                _req(m, MON_TARGET, ACTION_SEND_TO_ALL): _choice(
                    self.hass,
                    "target",
                    [
                        ACTION_SEND_TO_ALL,
                        ACTION_SEND_TO_PRESENT,
                        ACTION_SEND_TO_ABSENT,
                        ACTION_SEND_TO_NEAREST,
                    ],
                    custom_value=True,
                ),
            }
        )

    async def _common_step(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> FlowResult:
        energy = await _energy_sources(self.hass)
        errors: dict[str, str] = {}
        if user_input is not None:
            draft = _store_durations(user_input)
            if chosen := draft.pop(MON_ENERGY_SOURCE, None):
                # Energy dashboard counters are always cumulative.
                draft[MON_ENTITY], draft[MON_TYPE] = chosen, "cumulative"
            if draft.get(MON_ENTITY):
                self._draft = draft
                return await getattr(self, f"async_step_monitor_{draft[MON_RULE]}")()
            errors["base"] = "entity_required"
        return self.async_show_form(
            step_id=step_id,
            data_schema=self._common_schema({**self._source, **(user_input or {})}, energy),
            errors=errors,
        )

    async def _rule_step(
        self, rule: str, user_input: dict[str, Any] | None
    ) -> FlowResult:
        """Second screen: only the fields the chosen rule uses; then save."""
        if user_input is not None:
            monitor = {**self._draft, **_store_durations(user_input)}
            monitors = list(self._options.get(CONF_CONSUMPTION_MONITORS, []))
            idx = self._selected_item_index
            if idx is None:
                monitor[MON_ID] = uuid.uuid4().hex[:8]
                monitors.append(monitor)
            else:
                monitor[MON_ID] = monitors[idx][MON_ID]
                monitors[idx] = monitor
            self._options[CONF_CONSUMPTION_MONITORS] = monitors
            self._selected_item_index = None
            return await self.async_step_init()

        source = self._source if self._source.get(MON_RULE) == rule else {}
        fields: dict[Any, Any] = {}
        for key, default, kwargs in RULE_FIELDS[rule]:
            if kwargs is None:
                marker, sel = _duration_field(source, key, default)
            elif kwargs == "time":
                marker, sel = _req(source, key, default), selector.TimeSelector()
            else:
                marker, sel = _req(source, key, default), _number(**kwargs)
            fields[marker] = sel
        schema = vol.Schema(fields)
        return self.async_show_form(step_id=f"monitor_{rule}", data_schema=schema)

    async def async_step_monitor_threshold(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return await self._rule_step("threshold", user_input)

    async def async_step_monitor_continuous(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return await self._rule_step("continuous", user_input)

    async def async_step_monitor_slow_leak(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return await self._rule_step("slow_leak", user_input)

    async def async_step_monitor_habit(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return await self._rule_step("habit", user_input)

    async def async_step_add_monitor(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a consumption monitor."""
        if user_input is None:
            self._selected_item_index = None
            self._source = {}
        return await self._common_step("add_monitor", user_input)

    async def async_step_manage_monitors(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select a consumption monitor to edit or remove."""
        monitors = self._options.get(CONF_CONSUMPTION_MONITORS, [])
        if not monitors:
            return self.async_show_menu(
                step_id="manage_monitors",
                menu_options=["add_monitor", "init"],
            )

        if user_input is not None:
            idx = int(user_input["monitor_index"])
            if user_input.get("action") == "delete":
                monitors.pop(idx)
                self._options[CONF_CONSUMPTION_MONITORS] = monitors
                return await self.async_step_init()
            self._selected_item_index = idx
            return await self.async_step_edit_monitor()

        schema = vol.Schema(
            {
                vol.Required("monitor_index"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=str(i), label=f"{m.get(MON_NAME)} ({m.get(MON_ENTITY)})"
                            )
                            for i, m in enumerate(monitors)
                        ]
                    )
                ),
                vol.Required("action", default="edit"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=_options(self.hass, "manage_action", ["edit", "delete"])
                    )
                ),
            }
        )
        return self.async_show_form(step_id="manage_monitors", data_schema=schema)

    async def async_step_edit_monitor(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit a consumption monitor."""
        idx = self._selected_item_index
        monitors = self._options.get(CONF_CONSUMPTION_MONITORS, [])
        if idx is None or idx >= len(monitors):
            return await self.async_step_init()
        if user_input is None:
            self._source = monitors[idx]
        return await self._common_step("edit_monitor", user_input)

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Save options."""
        return self.async_create_entry(title="", data=self._options)

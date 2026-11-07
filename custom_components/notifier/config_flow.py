"""Config flow for Notifier integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_ALWAYS_HOME_DEVICES,
    CONF_CREATE_OCCUPANCY_SENSOR,
    CONF_DEVICE_NAME,
    CONF_DISTANCE_SENSOR,
    CONF_HOME_OCCUPANCY_SENSOR,
    CONF_NOTIFICATION_SERVICE,
    CONF_OCCUPANCY_PERSONS,
    CONF_OCCUPIED_STATE,
    CONF_PERSON_ID,
    CONF_PERSON_NAME,
    CONF_PERSONS,
    CONF_PROXIMITY_THRESHOLD,
    DEFAULT_OCCUPIED_STATE,
    DEFAULT_PROXIMITY_THRESHOLD,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


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

        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_CREATE_OCCUPANCY_SENSOR) and not user_input.get(
                CONF_HOME_OCCUPANCY_SENSOR
            ):
                errors["base"] = "occupancy_required"
            else:
                self._data.update(user_input)
                return await self.async_step_menu()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CREATE_OCCUPANCY_SENSOR, default=True
                ): selector.BooleanSelector(),
                vol.Optional(CONF_HOME_OCCUPANCY_SENSOR): selector.EntitySelector(),
                vol.Required(
                    CONF_OCCUPIED_STATE, default=DEFAULT_OCCUPIED_STATE
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

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

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
                "finish",
            ],
        )

    async def async_step_general_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit general settings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_CREATE_OCCUPANCY_SENSOR) and not user_input.get(
                CONF_HOME_OCCUPANCY_SENSOR
            ):
                errors["base"] = "occupancy_required"
            else:
                self._options.update(user_input)
                # A cleared optional field is absent from user_input: store it explicitly.
                self._options[CONF_HOME_OCCUPANCY_SENSOR] = user_input.get(
                    CONF_HOME_OCCUPANCY_SENSOR, ""
                )
                self._options[CONF_OCCUPANCY_PERSONS] = user_input.get(CONF_OCCUPANCY_PERSONS, [])
                return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CREATE_OCCUPANCY_SENSOR,
                    default=self._options.get(CONF_CREATE_OCCUPANCY_SENSOR, False),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_HOME_OCCUPANCY_SENSOR,
                    description={
                        "suggested_value": self._options.get(CONF_HOME_OCCUPANCY_SENSOR) or None
                    },
                ): selector.EntitySelector(),
                vol.Optional(
                    CONF_OCCUPANCY_PERSONS,
                    description={
                        "suggested_value": self._options.get(CONF_OCCUPANCY_PERSONS) or []
                    },
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            p[CONF_PERSON_NAME]
                            for p in self._options.get(CONF_PERSONS, [])
                            if p.get(CONF_PERSON_NAME)
                        ],
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_OCCUPIED_STATE,
                    default=self._options.get(CONF_OCCUPIED_STATE, DEFAULT_OCCUPIED_STATE),
                ): selector.TextSelector(),
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

        return self.async_show_form(
            step_id="general_settings", data_schema=schema, errors=errors
        )

    async def async_step_add_person(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a person."""
        if user_input is not None:
            persons = list(self._options.get(CONF_PERSONS, []))
            persons.append(user_input)
            self._options[CONF_PERSONS] = persons
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
                persons.pop(idx)
                self._options[CONF_PERSONS] = persons
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
                        options=[
                            selector.SelectOptionDict(value="edit", label="Edit"),
                            selector.SelectOptionDict(value="delete", label="Delete"),
                        ]
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
            persons[idx] = user_input
            self._options[CONF_PERSONS] = persons
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
                        options=[
                            selector.SelectOptionDict(value="edit", label="Edit"),
                            selector.SelectOptionDict(value="delete", label="Delete"),
                        ]
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

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Save options."""
        return self.async_create_entry(title="", data=self._options)

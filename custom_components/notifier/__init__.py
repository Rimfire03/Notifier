"""The Notifier integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import CONSUMPTION_DATA, DOMAIN
from .consumption import ConsumptionManager
from .notifier_manager import NotifierManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR]

SERVICE_NOTIFIER_SEND = "send"

NOTIFIER_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("action"): cv.string,
        vol.Optional("title"): cv.string,
        vol.Required("message"): cv.string,
        vol.Optional("callback"): vol.All(cv.ensure_list, [dict]),
        vol.Optional("timeout"): vol.Coerce(int),
        vol.Optional("image_url"): cv.string,
        vol.Optional("click_url"): cv.string,
        vol.Optional("icon"): cv.string,
        vol.Optional("color"): cv.string,
        vol.Optional("tag"): cv.string,
        vol.Optional("persistent"): cv.boolean,
        vol.Optional("interuption_level"): cv.string,
        vol.Optional("siri_shortcut_name"): cv.string,
        vol.Optional("until"): vol.All(cv.ensure_list, [dict]),
    },
    extra=vol.ALLOW_EXTRA,
)

SERVICE_NOTIFIER_DISCARD = "discard"
DISCARD_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("tag"): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Notifier component from configuration.yaml (not needed, but returns True)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Notifier from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    config_data = dict(entry.data)
    if entry.options:
        config_data.update(entry.options)

    config_data["entry_id"] = entry.entry_id

    async def async_send(data: dict[str, Any]) -> None:
        if (mgr := hass.data[DOMAIN].get(entry.entry_id)) is not None:
            await mgr.async_process_notification(data)

    # Created before the platforms: the alert sensors attach to its monitors.
    consumption = ConsumptionManager(hass, entry.entry_id, config_data, async_send)
    hass.data.setdefault(CONSUMPTION_DATA, {})[entry.entry_id] = consumption

    # Platforms first: the optional occupancy sensor must exist before the manager looks it up.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    manager = NotifierManager(hass, config_data)
    await manager.async_setup()

    hass.data[DOMAIN][entry.entry_id] = manager
    await consumption.async_start()

    async def async_handle_send_service(call: ServiceCall) -> None:
        """Handle notifier.send service call."""
        await manager.async_process_notification(dict(call.data))

    async def async_handle_discard_service(call: ServiceCall) -> None:
        """Handle notifier.discard service call."""
        tag = call.data.get("tag")
        if tag:
            await manager.async_clear_notifications(str(tag))

    hass.services.async_register(
        DOMAIN,
        SERVICE_NOTIFIER_SEND,
        async_handle_send_service,
        schema=NOTIFIER_SERVICE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_NOTIFIER_DISCARD,
        async_handle_discard_service,
        schema=DISCARD_SERVICE_SCHEMA,
    )

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options when changed."""
    # Reload so listeners (occupancy sensor) are rebuilt with the new config.
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    consumption: ConsumptionManager | None = hass.data.get(CONSUMPTION_DATA, {}).pop(
        entry.entry_id, None
    )
    if consumption:
        await consumption.async_stop()
    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    manager:NotifierManager | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if manager:
        await manager.async_unload()

    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_NOTIFIER_SEND)
        hass.services.async_remove(DOMAIN, SERVICE_NOTIFIER_DISCARD)

    return True

"""Binary sensor: home occupied (on when at least one configured person is home)."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_CREATE_OCCUPANCY_SENSOR,
    CONF_OCCUPANCY_PERSONS,
    CONF_OCCUPANCY_SENSOR_NAME,
    CONF_PERSON_ID,
    CONF_PERSON_NAME,
    CONF_PERSONS,
    DEFAULT_OCCUPANCY_SENSOR_NAME,
    DOMAIN,
    OCCUPANCY_SENSOR_UNIQUE_SUFFIX,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create the occupancy sensor, or remove it when the option is off."""
    config = {**entry.data, **entry.options}
    unique_id = f"{entry.entry_id}_{OCCUPANCY_SENSOR_UNIQUE_SUFFIX}"
    if not config.get(CONF_CREATE_OCCUPANCY_SENSOR):
        registry = er.async_get(hass)
        if entity_id := registry.async_get_entity_id("binary_sensor", DOMAIN, unique_id):
            registry.async_remove(entity_id)
        return
    # Empty selection = every configured person.
    wanted = config.get(CONF_OCCUPANCY_PERSONS) or []
    trackers = [
        p[CONF_PERSON_ID]
        for p in config.get(CONF_PERSONS, [])
        if p.get(CONF_PERSON_ID) and (not wanted or p.get(CONF_PERSON_NAME) in wanted)
    ]
    name = config.get(CONF_OCCUPANCY_SENSOR_NAME) or DEFAULT_OCCUPANCY_SENSOR_NAME
    async_add_entities([HomeOccupiedSensor(unique_id, name, trackers)])


class HomeOccupiedSensor(BinarySensorEntity):
    """On when any configured person is home."""

    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, unique_id: str, name: str, trackers: list[str]) -> None:
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._trackers = trackers
        self._attr_is_on = False

    def _compute(self) -> bool:
        return any(
            (s := self.hass.states.get(t)) is not None and s.state == "home"
            for t in self._trackers
        )

    async def async_added_to_hass(self) -> None:
        self._attr_is_on = self._compute()

        @callback
        def _changed(_event: Event) -> None:
            self._attr_is_on = self._compute()
            self.async_write_ha_state()

        if self._trackers:
            self.async_on_remove(
                async_track_state_change_event(self.hass, self._trackers, _changed)
            )

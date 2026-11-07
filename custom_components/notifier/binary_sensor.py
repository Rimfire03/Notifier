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

from .consumption import ConsumptionMonitor
from .const import (
    CONSUMPTION_DATA,
    CONSUMPTION_UNIQUE_INFIX,
    CONF_OCCUPANCY_PERSONS,
    CONF_OCCUPANCY_SENSOR_NAME,
    CONF_PERSON_ID,
    CONF_PERSON_NAME,
    CONF_PERSONS,
    DEFAULT_OCCUPANCY_SENSOR_NAME,
    OCCUPANCY_SENSOR_UNIQUE_SUFFIX,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create the occupancy sensor for the persons selected in the options."""
    config = {**entry.data, **entry.options}
    unique_id = f"{entry.entry_id}_{OCCUPANCY_SENSOR_UNIQUE_SUFFIX}"
    persons = [p for p in config.get(CONF_PERSONS, []) if p.get(CONF_PERSON_ID)]
    wanted = config.get(CONF_OCCUPANCY_PERSONS)  # None = everyone; a list (even empty) is exact
    if wanted is not None:
        persons = [p for p in persons if p.get(CONF_PERSON_NAME) in wanted]
    name = config.get(CONF_OCCUPANCY_SENSOR_NAME) or DEFAULT_OCCUPANCY_SENSOR_NAME
    entities: list[BinarySensorEntity] = [HomeOccupiedSensor(unique_id, name, persons)]

    consumption = hass.data.get(CONSUMPTION_DATA, {}).get(entry.entry_id)
    monitors = consumption.monitors if consumption else {}
    entities += [ConsumptionAlertSensor(entry.entry_id, m) for m in monitors.values()]

    # Drop the alert sensors of deleted monitors.
    prefix = f"{entry.entry_id}_{CONSUMPTION_UNIQUE_INFIX}_"
    registry = er.async_get(hass)
    for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg.unique_id.startswith(prefix) and reg.unique_id[len(prefix):] not in monitors:
            registry.async_remove(reg.entity_id)

    async_add_entities(entities)


class ConsumptionAlertSensor(BinarySensorEntity):
    """On while a consumption monitor reports abnormal consumption."""

    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, entry_id: str, monitor: ConsumptionMonitor) -> None:
        self._monitor = monitor
        self._attr_unique_id = f"{entry_id}_{CONSUMPTION_UNIQUE_INFIX}_{monitor.id}"
        self._attr_name = monitor.name
        self._attr_extra_state_attributes = {
            "entity": monitor.entity,
            "rule": monitor.rule,
        }

    @property
    def is_on(self) -> bool:
        return self._monitor.alert

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._monitor.add_listener(self.async_write_ha_state))


class HomeOccupiedSensor(BinarySensorEntity):
    """On when any selected person is home."""

    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, unique_id: str, name: str, persons: list[dict]) -> None:
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._persons = {
            p[CONF_PERSON_ID]: p.get(CONF_PERSON_NAME, p[CONF_PERSON_ID]) for p in persons
        }
        self._attr_is_on = False

    def _home(self) -> list[str]:
        return [
            label
            for tracker, label in self._persons.items()
            if (s := self.hass.states.get(tracker)) is not None and s.state == "home"
        ]

    def _refresh(self) -> None:
        home = self._home()
        self._attr_is_on = bool(home)
        self._attr_extra_state_attributes = {
            "persons": list(self._persons.values()),
            "persons_home": home,
        }

    async def async_added_to_hass(self) -> None:
        self._refresh()

        @callback
        def _changed(_event: Event) -> None:
            self._refresh()
            self.async_write_ha_state()

        if self._persons:
            self.async_on_remove(
                async_track_state_change_event(self.hass, list(self._persons), _changed)
            )

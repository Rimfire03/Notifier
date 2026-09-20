"""Core logic and event handling for Notifier."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    ACTION_SEND_TO_ABSENT,
    ACTION_SEND_TO_ALL,
    ACTION_SEND_TO_NEAREST,
    ACTION_SEND_TO_PRESENT,
    ACTION_SEND_WHEN_PRESENT,
    CONF_ALWAYS_HOME_DEVICES,
    CONF_DEVICE_NAME,
    CONF_DISTANCE_SENSOR,
    CONF_HOME_OCCUPANCY_SENSOR,
    CONF_NOTIFICATION_SERVICE,
    CONF_OCCUPIED_STATE,
    CONF_PERSON_ID,
    CONF_PERSON_NAME,
    CONF_PERSONS,
    CONF_PROXIMITY_THRESHOLD,
    DEFAULT_OCCUPIED_STATE,
    DEFAULT_PROXIMITY_THRESHOLD,
    EVENT_MOBILE_APP_ACTION,
    EVENT_NOTIFIER,
    EVENT_NOTIFIER_DISCARD,
)

_LOGGER = logging.getLogger(__name__)

COLOR_MAP = {
    "red": "#f44336",
    "pink": "#e91e63",
    "purple": "#9c27b0",
    "deep-purple": "#673ab7",
    "indigo": "#3f51b5",
    "blue": "#2196f3",
    "light-blue": "#03a9f4",
    "cyan": "#00bcd4",
    "teal": "#009688",
    "green": "#4caf50",
    "light-green": "#8bc34a",
    "lime": "#cddc39",
    "yellow": "#ffeb3b",
    "amber": "#ffc107",
    "orange": "#ff9800",
    "deep-orange": "#ff5722",
    "brown": "#795548",
    "grey": "#9e9e9e",
    "blue-grey": "#607d8b",
    "black": "#000000",
    "white": "#ffffff",
    "disabled": "#bdbdbd",
}


def compute_color(color_name: str) -> str:
    """Compute hex color from color name if known."""
    if not color_name:
        return ""
    return COLOR_MAP.get(color_name.lower(), color_name)


class NotifierManager:
    """Notifier Manager handling logic, state, and events."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        """Initialize the manager."""
        self.hass = hass
        self.config = config
        self.staged_notifications: list[dict[str, Any]] = []
        self.watchers: list[dict[str, Any]] = []
        self._listeners: list[CALLBACK_TYPE] = []

    def update_config(self, config: dict[str, Any]) -> None:
        """Update configuration."""
        self.config = config

    @property
    def home_occupancy_sensor(self) -> str:
        """Return the occupancy sensor entity id."""
        sensor = self.config.get(CONF_HOME_OCCUPANCY_SENSOR, "")
        if isinstance(sensor, dict):
            return sensor.get("id", "")
        return str(sensor)

    @property
    def occupied_state(self) -> str:
        """Return the occupied state value."""
        sensor = self.config.get(CONF_HOME_OCCUPANCY_SENSOR, {})
        if isinstance(sensor, dict) and "occupied_state" in sensor:
            return str(sensor.get("occupied_state"))
        return str(self.config.get(CONF_OCCUPIED_STATE, DEFAULT_OCCUPIED_STATE))

    @property
    def proximity_threshold(self) -> float:
        """Return proximity threshold in meters."""
        return float(
            self.config.get(CONF_PROXIMITY_THRESHOLD, DEFAULT_PROXIMITY_THRESHOLD)
        )

    @property
    def persons(self) -> list[dict[str, Any]]:
        """Return configured persons."""
        return self.config.get(CONF_PERSONS, [])

    @property
    def always_home_devices(self) -> list[dict[str, Any]]:
        """Return configured always home devices."""
        return self.config.get(CONF_ALWAYS_HOME_DEVICES, [])

    async def async_setup(self) -> None:
        """Set up event listeners."""
        self._listeners.append(
            self.hass.bus.async_listen(
                EVENT_NOTIFIER, self._handle_notifier_event
            )
        )
        self._listeners.append(
            self.hass.bus.async_listen(
                EVENT_NOTIFIER_DISCARD, self._handle_notifier_discard_event
            )
        )
        self._listeners.append(
            self.hass.bus.async_listen(
                EVENT_MOBILE_APP_ACTION, self._handle_mobile_app_action
            )
        )

        occupancy_sensor = self.home_occupancy_sensor
        if occupancy_sensor:
            self._listeners.append(
                async_track_state_change_event(
                    self.hass, [occupancy_sensor], self._handle_occupancy_change
                )
            )

        _LOGGER.info(
            "Notifier manager initialized with %d persons and %d devices",
            len(self.persons),
            len(self.always_home_devices),
        )

    async def async_unload(self) -> None:
        """Unload listeners and active watchers."""
        for unsub in self._listeners:
            unsub()
        self._listeners.clear()

        for watcher in list(self.watchers):
            unsub = watcher.get("unsub")
            if callable(unsub):
                unsub()
        self.watchers.clear()
        self.staged_notifications.clear()

    async def _handle_notifier_event(self, event: Event) -> None:
        """Handle NOTIFIER custom event."""
        _LOGGER.debug("NOTIFIER event received: %s", event.data)
        await self.async_process_notification(event.data)

    async def _handle_notifier_discard_event(self, event: Event) -> None:
        """Handle NOTIFIER_DISCARD event."""
        tag = event.data.get("tag")
        if tag:
            await self.async_clear_notifications(str(tag))

    async def _handle_mobile_app_action(self, event: Event) -> None:
        """Handle mobile app notification action clicks to auto-discard."""
        tag = event.data.get("tag")
        if tag:
            _LOGGER.debug("Mobile app notification action clicked with tag: %s", tag)
            await self.async_clear_notifications(str(tag))

    async def _handle_occupancy_change(self, event: Event) -> None:
        """Handle state change of occupancy sensor."""
        new_state: State | None = event.data.get("new_state")
        if new_state is None:
            return

        if str(new_state.state).lower() == self.occupied_state.lower():
            if self.staged_notifications:
                _LOGGER.info(
                    "Home is now occupied. Flushing %d staged notification(s)...",
                    len(self.staged_notifications),
                )
            while self.staged_notifications:
                data = self.staged_notifications.pop(0)
                await self.async_send_to_present(data)

    def is_home_occupied(self) -> bool:
        """Check whether the home is currently occupied."""
        sensor_id = self.home_occupancy_sensor
        if not sensor_id:
            return True
        state = self.hass.states.get(sensor_id)
        if state is None:
            return False
        return str(state.state).lower() == self.occupied_state.lower()

    def is_person_present(self, person: dict[str, Any]) -> bool:
        """Check if a person is present (home or within proximity threshold)."""
        person_id = person.get(CONF_PERSON_ID)
        if person_id:
            state = self.hass.states.get(person_id)
            if state and str(state.state).lower() == "home":
                return True

        distance_sensor = person.get(CONF_DISTANCE_SENSOR)
        if distance_sensor:
            dist_state = self.hass.states.get(distance_sensor)
            if dist_state:
                try:
                    distance = float(dist_state.state)
                    if distance <= self.proximity_threshold:
                        return True
                except (ValueError, TypeError):
                    pass

        return False

    def get_person_distance(self, person: dict[str, Any]) -> float:
        """Get distance of person in meters or inf if unknown."""
        distance_sensor = person.get(CONF_DISTANCE_SENSOR)
        if distance_sensor:
            dist_state = self.hass.states.get(distance_sensor)
            if dist_state:
                try:
                    return float(dist_state.state)
                except (ValueError, TypeError):
                    pass

        person_id = person.get(CONF_PERSON_ID)
        if person_id:
            state = self.hass.states.get(person_id)
            if state and str(state.state).lower() == "home":
                return 0.0

        return float("inf")

    def build_notification_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Build notification data dict for mobile_app service."""
        notification_data: dict[str, Any] = {}

        if "callback" in data and isinstance(data["callback"], list):
            actions = []
            for cb in data["callback"]:
                action = {
                    "action": cb.get("event", ""),
                    "title": cb.get("title", ""),
                }
                if "icon" in cb:
                    action["icon"] = f"sfsymbols:{cb['icon']}"
                if "destructive" in cb:
                    action["destructive"] = cb["destructive"]
                actions.append(action)
            notification_data["actions"] = actions

        if "timeout" in data:
            notification_data["timeout"] = data["timeout"]

        if "click_url" in data:
            notification_data["url"] = data["click_url"]

        if "image_url" in data:
            notification_data["image"] = data["image_url"]

        if "icon" in data:
            notification_data["notification_icon"] = data["icon"]

        if "color" in data:
            notification_data["color"] = compute_color(str(data["color"]))

        if "tag" in data:
            notification_data["tag"] = data["tag"]

        if "interuption_level" in data:
            notification_data["push"] = {
                "interruption-level": data["interuption_level"]
            }

        if "siri_shortcut_name" in data:
            notification_data["shortcut"] = {
                "name": data["siri_shortcut_name"]
            }

        return notification_data

    async def _call_notify_service(
        self,
        service_target: str,
        title: str | None,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Call a notification service safely supporting 'notify/xyz' or 'notify.xyz'."""
        if not service_target:
            return

        normalized = service_target.replace("/", ".")
        parts = normalized.split(".", 1)
        if len(parts) == 2:
            domain, service = parts[0], parts[1]
        else:
            domain, service = "notify", parts[0]

        service_data: dict[str, Any] = {"message": message}
        if title:
            service_data["title"] = title
        if data:
            service_data["data"] = data

        _LOGGER.debug(
            "Calling notification service %s.%s with %s",
            domain,
            service,
            service_data,
        )
        try:
            await self.hass.services.async_call(
                domain, service, service_data, blocking=False
            )
        except Exception as err:
            _LOGGER.error("Failed to call service %s.%s: %s", domain, service, err)

    async def async_send_to_person(
        self, data: dict[str, Any], person: dict[str, Any]
    ) -> None:
        """Send notification to a specific person."""
        service = person.get(CONF_NOTIFICATION_SERVICE)
        if not service:
            return
        notification_data = self.build_notification_data(data)
        title = data.get("title")
        message = data.get("message", "")
        await self._call_notify_service(service, title, message, notification_data)

    async def async_send_to_always_home_devices(
        self, data: dict[str, Any]
    ) -> None:
        """Send notification to all always home devices."""
        notification_data = self.build_notification_data(data)
        title = data.get("title")
        message = data.get("message", "")
        for device in self.always_home_devices:
            service = device.get(CONF_NOTIFICATION_SERVICE)
            if service:
                await self._call_notify_service(
                    service, title, message, notification_data
                )

    async def async_send_to_all(self, data: dict[str, Any]) -> None:
        """Send notification to all persons and always home devices."""
        for person in self.persons:
            await self.async_send_to_person(data, person)
        await self.async_send_to_always_home_devices(data)

    async def async_send_to_present(self, data: dict[str, Any]) -> None:
        """Send notification to present persons and always home devices."""
        for person in self.persons:
            if self.is_person_present(person):
                await self.async_send_to_person(data, person)
        await self.async_send_to_always_home_devices(data)

    async def async_send_to_absent(self, data: dict[str, Any]) -> None:
        """Send notification to absent persons."""
        for person in self.persons:
            if not self.is_person_present(person):
                await self.async_send_to_person(data, person)

    async def async_send_to_nearest(self, data: dict[str, Any]) -> None:
        """Send notification to nearest person(s)."""
        if not self.persons:
            return

        distances = [(person, self.get_person_distance(person)) for person in self.persons]
        min_distance = min(d[1] for d in distances)

        if min_distance == float("inf"):
            # If all distances are unknown, send to all
            await self.async_send_to_all(data)
            return

        threshold = self.proximity_threshold
        for person, dist in distances:
            if dist <= min_distance + threshold:
                await self.async_send_to_person(data, person)

    async def async_send_when_present(self, data: dict[str, Any]) -> None:
        """Send when home is occupied, or stage it until occupied."""
        if self.is_home_occupied():
            await self.async_send_to_present(data)
        else:
            _LOGGER.info(
                "Home is not occupied. Staging notification for when home becomes occupied."
            )
            self.staged_notifications.append(data)
            await self.async_send_to_always_home_devices(data)

    async def async_process_notification(self, data: dict[str, Any]) -> None:
        """Process an incoming notification payload."""
        action = data.get("action", "")

        # Target person direct check
        for person in self.persons:
            person_name = str(person.get(CONF_PERSON_NAME, "")).strip().lower()
            if action.lower() == f"send_to_{person_name}":
                await self.async_send_to_person(data, person)
                break
        else:
            if action == ACTION_SEND_TO_ALL:
                await self.async_send_to_all(data)
            elif action == ACTION_SEND_TO_PRESENT:
                await self.async_send_to_present(data)
            elif action == ACTION_SEND_TO_ABSENT:
                await self.async_send_to_absent(data)
            elif action == ACTION_SEND_TO_NEAREST:
                await self.async_send_to_nearest(data)
            elif action == ACTION_SEND_WHEN_PRESENT:
                await self.async_send_when_present(data)

        # Persistent notification
        if data.get("persistent"):
            tag = data.get("tag")
            notification_id = str(tag) if tag else str(int(time.time()))
            _LOGGER.debug(
                "Creating persistent notification on HA with id %s", notification_id
            )
            try:
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": data.get("title"),
                        "message": data.get("message", ""),
                        "notification_id": notification_id,
                    },
                    blocking=False,
                )
            except Exception as err:
                _LOGGER.error("Failed to create persistent notification: %s", err)

        # Until watchers
        if "until" in data and "tag" in data and isinstance(data["until"], list):
            tag = str(data["tag"])
            for watcher_def in data["until"]:
                entity_id = watcher_def.get("entity_id")
                target_state = str(watcher_def.get("new_state", ""))
                if not entity_id:
                    continue

                @callback
                def _until_state_changed(
                    event: Event,
                    w_tag: str = tag,
                    expected_state: str = target_state,
                ) -> None:
                    new_s: State | None = event.data.get("new_state")
                    if new_s and str(new_s.state).lower() == expected_state.lower():
                        _LOGGER.debug(
                            "Watcher triggered for tag %s (entity reached %s)",
                            w_tag,
                            expected_state,
                        )
                        asyncio.create_task(self.async_clear_notifications(w_tag))

                unsub = async_track_state_change_event(
                    self.hass, [entity_id], _until_state_changed
                )
                self.watchers.append({"tag": tag, "unsub": unsub})
                _LOGGER.debug(
                    "Registered until watcher on %s -> %s for tag %s",
                    entity_id,
                    target_state,
                    tag,
                )

    async def async_clear_notifications(self, tag: str) -> None:
        """Clear notifications for given tag across devices and HA persistent notifications."""
        _LOGGER.debug("Clearing notifications with tag: %s", tag)
        notification_data = {"tag": tag}

        # Clear on person devices
        for person in self.persons:
            service = person.get(CONF_NOTIFICATION_SERVICE)
            if service:
                await self._call_notify_service(
                    service,
                    None,
                    "clear_notification",
                    notification_data,
                )

        # Clear on always home devices
        for device in self.always_home_devices:
            service = device.get(CONF_NOTIFICATION_SERVICE)
            if service:
                await self._call_notify_service(
                    service,
                    None,
                    "clear_notification",
                    notification_data,
                )

        # Clear persistent notification
        try:
            await self.hass.services.async_call(
                "persistent_notification",
                "dismiss",
                {"notification_id": tag},
                blocking=False,
            )
        except Exception as err:
            _LOGGER.error("Failed to dismiss persistent notification %s: %s", tag, err)

        # Cancel active watchers for this tag
        self.cancel_watchers(tag)

    def cancel_watchers(self, tag: str) -> None:
        """Cancel watchers registered for tag."""
        remaining_watchers = []
        for watcher in self.watchers:
            if watcher.get("tag") == tag:
                unsub = watcher.get("unsub")
                if callable(unsub):
                    unsub()
            else:
                remaining_watchers.append(watcher)
        self.watchers = remaining_watchers

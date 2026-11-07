"""Constants for the Notifier integration."""
from __future__ import annotations

DOMAIN = "notifier"

# Configuration keys
CONF_HOME_OCCUPANCY_SENSOR = "home_occupancy_sensor"
CONF_OCCUPIED_STATE = "occupied_state"
CONF_PROXIMITY_THRESHOLD = "proximity_threshold"
CONF_CREATE_OCCUPANCY_SENSOR = "create_occupancy_sensor"
CONF_PERSONS = "persons"
CONF_ALWAYS_HOME_DEVICES = "always_home_devices"

# Person keys
CONF_PERSON_NAME = "name"
CONF_PERSON_ID = "id"
CONF_NOTIFICATION_SERVICE = "notification_service"
CONF_DISTANCE_SENSOR = "distance_sensor"

# Always home device keys
CONF_DEVICE_NAME = "name"

OCCUPANCY_SENSOR_UNIQUE_SUFFIX = "home_occupied"

# Defaults
DEFAULT_PROXIMITY_THRESHOLD = 1000
DEFAULT_OCCUPIED_STATE = "on"

# Events
EVENT_NOTIFIER = "NOTIFIER"
EVENT_NOTIFIER_DISCARD = "NOTIFIER_DISCARD"
EVENT_MOBILE_APP_ACTION = "mobile_app_notification_action"

# Actions
ACTION_SEND_TO_ALL = "send_to_all"
ACTION_SEND_TO_PRESENT = "send_to_present"
ACTION_SEND_TO_ABSENT = "send_to_absent"
ACTION_SEND_TO_NEAREST = "send_to_nearest"
ACTION_SEND_WHEN_PRESENT = "send_when_present"

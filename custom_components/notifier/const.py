"""Constants for the Notifier integration."""
from __future__ import annotations

DOMAIN = "notifier"

# Configuration keys
CONF_HOME_OCCUPANCY_SENSOR = "home_occupancy_sensor"
CONF_OCCUPIED_STATE = "occupied_state"
CONF_PROXIMITY_THRESHOLD = "proximity_threshold"
CONF_CREATE_OCCUPANCY_SENSOR = "create_occupancy_sensor"
CONF_OCCUPANCY_PERSONS = "occupancy_persons"
CONF_OCCUPANCY_SENSOR_NAME = "occupancy_sensor_name"
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

# Consumption monitoring (optional, independent of notifications)
CONF_CONSUMPTION_MONITORS = "consumption_monitors"
CONSUMPTION_DATA = f"{DOMAIN}_consumption"
CONSUMPTION_UNIQUE_INFIX = "consumption"
MON_ID = "id"
MON_NAME = "name"
MON_ENTITY = "entity"
MON_TYPE = "type"  # cumulative | instant
MON_RULE = "rule"  # threshold | continuous | habit
MON_THRESHOLD = "threshold"
MON_WINDOW = "window_minutes"
MON_HOURS = "continuous_hours"
MON_DAYS = "habit_days"
MON_FACTOR = "habit_factor"
MON_TIME = "alert_time"
MON_COOLDOWN = "cooldown_minutes"
MON_TARGET = "target"

# Defaults
DEFAULT_PROXIMITY_THRESHOLD = 1000
DEFAULT_OCCUPIED_STATE = "on"
DEFAULT_OCCUPANCY_SENSOR_NAME = "Maison occupée"

# Events
EVENT_NOTIFIER = "NOTIFIER"
EVENT_NOTIFIER_DISCARD = "NOTIFIER_DISCARD"
EVENT_MOBILE_APP_ACTION = "mobile_app_notification_action"
EVENT_CONSUMPTION_NORMAL = "notifier_consumption_normal"

# Actions
ACTION_SEND_TO_ALL = "send_to_all"
ACTION_SEND_TO_PRESENT = "send_to_present"
ACTION_SEND_TO_ABSENT = "send_to_absent"
ACTION_SEND_TO_NEAREST = "send_to_nearest"
ACTION_SEND_WHEN_PRESENT = "send_when_present"

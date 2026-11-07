"""Abnormal water / electricity consumption monitoring.

Fully independent of the notification pipeline: it only calls the existing
``async_process_notification`` to deliver alerts.
"""
from __future__ import annotations

import logging
import math
import time
from collections import deque
from datetime import timedelta
from typing import Any, Awaitable, Callable

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, State, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CONSUMPTION_MONITORS,
    DOMAIN,
    EVENT_CONSUMPTION_NORMAL,
    EVENT_MOBILE_APP_ACTION,
    MON_COOLDOWN,
    MON_DAYS,
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
)

_LOGGER = logging.getLogger(__name__)

# Flow is "continuous" while the meter keeps moving with gaps shorter than this.
CONTINUOUS_GAP = 3600
# Minimum distinct days of history before the habit rule may alert.
HABIT_MIN_DAYS = 3
HABIT_DAYS = 7
HABIT_FACTOR = 1.5
HABIT_DEFAULT_TIME = "08:00:00"
# The daily check runs on the minute tick: allow a few minutes of slack, not a late alert after a restart.
HABIT_GRACE_MINUTES = 10
HOUR_FORMAT = "%Y-%m-%dT%H"
SAVE_DELAY = 300

MESSAGES = {
    "fr": {
        "title": "Alerte consommation",
        "normal": "C'était normal",
        "close": "Fermer",
        "threshold": "Consommation anormale sur « {name} » : {value:.2f} {unit} en {window:g} min (seuil {limit:g} {unit}).",
        "continuous": "Consommation continue sur « {name} » depuis {value:.1f} h (limite {limit:g} h) : fuite possible.",
        "habit": "Consommation inhabituelle sur « {name} » : {value:.2f} {unit} sur les dernières 24 h (alerte au-delà de {limit:.2f} {unit}).",
    },
    "en": {
        "title": "Consumption alert",
        "normal": "It was normal",
        "close": "Close",
        "threshold": "Abnormal consumption on \"{name}\": {value:.2f} {unit} in {window:g} min (limit {limit:g} {unit}).",
        "continuous": "Continuous consumption on \"{name}\" for {value:.1f} h (limit {limit:g} h): possible leak.",
        "habit": "Unusual consumption on \"{name}\": {value:.2f} {unit} over the last 24 h (alert above {limit:.2f} {unit}).",
    },
}


def _number(state: State | None) -> float | None:
    """Numeric value of a state, None when unknown/unavailable/non-numeric."""
    if state is None:
        return None
    try:
        value = float(state.state)
    except (ValueError, TypeError):
        return None
    return value if math.isfinite(value) else None


class ConsumptionMonitor:
    """Tracks one sensor and evaluates one rule on it."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.id: str = cfg[MON_ID]
        self.name: str = cfg.get(MON_NAME) or cfg[MON_ENTITY]
        self.entity: str = cfg[MON_ENTITY]
        self.cumulative: bool = cfg.get(MON_TYPE, "cumulative") != "instant"
        self.rule: str = cfg.get(MON_RULE, "threshold")
        self.threshold = float(cfg.get(MON_THRESHOLD) or 0)
        self.window = float(cfg.get(MON_WINDOW) or 60)
        self.hours = float(cfg.get(MON_HOURS) or 6)
        # Habit rule: fixed history and sensitivity, the user only picks the alert time.
        self.days = int(cfg.get(MON_DAYS) or HABIT_DAYS)
        self.factor = float(cfg.get(MON_FACTOR) or HABIT_FACTOR)
        hour, minute, *_ = (cfg.get(MON_TIME) or HABIT_DEFAULT_TIME).split(":")
        self.alert_hm = (int(hour), int(minute))
        self._habit_day: str | None = None
        self._habit_verdict: tuple[bool, float, float] = (False, 0.0, 0.0)
        self._fire = False
        self.cooldown = float(cfg.get(MON_COOLDOWN) or 60)
        self.target: str = cfg.get(MON_TARGET) or "send_to_all"

        self.unit = ""
        self.alert = False
        self.last_notified = 0.0
        self.listeners: list[Callable[[], None]] = []
        # hour key -> [sum, count]; persisted
        self.buckets: dict[str, list[float]] = {}

        self._last_value: float | None = None
        self._samples: deque[tuple[float, float]] = deque()
        self._streak_start: float | None = None
        self._last_active: float | None = None

    def add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

    def _hour_key(self, now: float, days_back: int = 0, hours_back: int = 0) -> str:
        local = dt_util.as_local(dt_util.utc_from_timestamp(now))
        return (local - timedelta(days=days_back, hours=hours_back)).strftime(HOUR_FORMAT)

    @staticmethod
    def _bucket_value(bucket: list[float] | None, cumulative: bool) -> float:
        if not bucket or not bucket[1]:
            return 0.0
        return bucket[0] if cumulative else bucket[0] / bucket[1]

    def seed(self, value: float | None) -> None:
        """Remember the current meter value so the first event yields a real increment."""
        self._last_value = value

    def feed(self, value: float, now: float) -> None:
        """Record a new sensor value."""
        if self.cumulative:
            # A meter reset (value going down) counts as no consumption for that step.
            x = 0.0 if self._last_value is None else max(value - self._last_value, 0.0)
            self._last_value = value
            active = x > 0
        else:
            x = value
            active = value > 0

        if active:
            if self._last_active is None or now - self._last_active > CONTINUOUS_GAP:
                self._streak_start = now
            self._last_active = now
        else:
            self._streak_start = self._last_active = None

        if self.rule == "threshold":  # other rules never read the window: keep it bounded
            self._samples.append((now, x))

        key = self._hour_key(now)
        if key not in self.buckets:
            cutoff = self._hour_key(now, self.days + 2)  # +1 day for the 24 h window itself
            self.buckets = {k: b for k, b in self.buckets.items() if k >= cutoff}
            self.buckets[key] = [0.0, 0]
        self.buckets[key][0] += x
        self.buckets[key][1] += 1

    def evaluate(self, now: float) -> tuple[bool, float, float]:
        """Return (abnormal, measured value, limit)."""
        if self.rule == "continuous":
            streak = 0.0
            if (
                self._streak_start is not None
                and self._last_active is not None
                and now - self._last_active <= CONTINUOUS_GAP
            ):
                streak = (now - self._streak_start) / 3600
            return streak >= self.hours, streak, self.hours

        if self.rule == "habit":
            return self._evaluate_habit(now)

        horizon = now - self.window * 60
        while self._samples and self._samples[0][0] < horizon:
            self._samples.popleft()
        values = [x for _, x in self._samples]
        if not values:
            return False, 0.0, self.threshold
        total = sum(values) if self.cumulative else sum(values) / len(values)
        return total > self.threshold, total, self.threshold

    def _day_total(self, now: float, days_back: int) -> float:
        """Consumption over the 24 h ending at `now`, shifted back by days_back days.

        Cumulative: sum of the hours. Instant: average of the hours.
        Hours without events carry no bucket and count as zero.
        """
        total = sum(
            self._bucket_value(
                self.buckets.get(self._hour_key(now, days_back, h)), self.cumulative
            )
            for h in range(24)
        )
        return total if self.cumulative else total / 24

    def _evaluate_habit(self, now: float) -> tuple[bool, float, float]:
        """Daily check at the chosen time: last 24 h against the previous days' 24 h."""
        local = dt_util.as_local(dt_util.utc_from_timestamp(now))
        today = local.date().isoformat()
        hour, minute = self.alert_hm
        due = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if (
            self._habit_day != today
            and due <= local < due + timedelta(minutes=HABIT_GRACE_MINUTES)
        ):
            self._habit_day = today
            current = self._day_total(now, 0)
            # Only compare with days fully covered by recorded history.
            first = min(self.buckets, default=None)
            days = [
                d
                for d in range(1, self.days + 1)
                if first is not None and self._hour_key(now, d, 23) >= first
            ]
            if len(days) < HABIT_MIN_DAYS:
                self._habit_verdict = (False, current, 0.0)
            else:
                past = [self._day_total(now, d) for d in days]
                limit = sum(past) / len(past) * self.factor
                abnormal = limit > 0 and current > limit
                self._habit_verdict = (abnormal, current, limit)
                self._fire = abnormal
        return self._habit_verdict

    @property
    def normal_action(self) -> str:
        return f"CONSUMPTION_NORMAL_{self.id}"

    @property
    def close_action(self) -> str:
        return f"CONSUMPTION_CLOSE_{self.id}"

    def acknowledge(self) -> None:
        """User said the consumption was normal: turn the alert off until the next check."""
        self._habit_verdict = (False, *self._habit_verdict[1:])
        if self.alert:
            self.alert = False
            for listener in list(self.listeners):
                listener()

    def should_notify(self, now: float, changed: bool) -> bool:
        """Whether an alert message must be sent now (the sensor is already abnormal)."""
        if self.rule == "habit":
            fire, self._fire = self._fire, False  # once per daily check
            return fire
        return changed or now - self.last_notified >= self.cooldown * 60


class ConsumptionManager:
    """Owns the monitors of one config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        config: dict[str, Any],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self.hass = hass
        self._send = send
        self.monitors: dict[str, ConsumptionMonitor] = {
            m[MON_ID]: ConsumptionMonitor(m)
            for m in config.get(CONF_CONSUMPTION_MONITORS, [])
            if m.get(MON_ID) and m.get(MON_ENTITY)
        }
        self._store: Store = Store(hass, 1, f"{DOMAIN}_consumption_{entry_id}")
        self._unsubs: list[CALLBACK_TYPE] = []

    def _data(self) -> dict[str, Any]:
        return {m.id: m.buckets for m in self.monitors.values()}

    async def async_start(self) -> None:
        if not self.monitors:
            return
        saved = await self._store.async_load() or {}
        for m in self.monitors.values():
            m.buckets = saved.get(m.id, {})
            m.seed(_number(self.hass.states.get(m.entity)))
        entities = sorted({m.entity for m in self.monitors.values()})
        self._unsubs.append(
            async_track_state_change_event(self.hass, entities, self._on_state)
        )
        self._unsubs.append(
            async_track_time_interval(self.hass, self._tick, timedelta(minutes=1))
        )
        self._unsubs.append(
            self.hass.bus.async_listen(EVENT_MOBILE_APP_ACTION, self._on_action)
        )

    async def async_stop(self) -> None:
        while self._unsubs:
            self._unsubs.pop()()
        if self.monitors:
            await self._store.async_save(self._data())

    @callback
    def _on_action(self, event: Event) -> None:
        """'It was normal' button: clear the alert and tell automations."""
        action = event.data.get("action")
        for m in self.monitors.values():
            if action == m.normal_action:
                m.acknowledge()
                self.hass.bus.async_fire(
                    EVENT_CONSUMPTION_NORMAL, {"name": m.name, "entity_id": m.entity}
                )

    @callback
    def _on_state(self, event: Event) -> None:
        new_state: State | None = event.data.get("new_state")
        value = _number(new_state)
        if value is None:
            return
        now = time.time()
        for m in self.monitors.values():
            if m.entity == event.data["entity_id"]:
                m.unit = new_state.attributes.get("unit_of_measurement", "")
                m.feed(value, now)
                self._check(m, now)
        self._store.async_delay_save(self._data, SAVE_DELAY)

    @callback
    def _tick(self, _now: Any) -> None:
        now = time.time()
        for m in self.monitors.values():
            self._check(m, now)

    def _check(self, m: ConsumptionMonitor, now: float) -> None:
        abnormal, value, limit = m.evaluate(now)
        changed = abnormal != m.alert
        m.alert = abnormal
        if changed:
            for listener in list(m.listeners):
                listener()
        if abnormal and m.should_notify(now, changed):
            m.last_notified = now
            self.hass.async_create_task(self._notify(m, value, limit))

    async def _notify(self, m: ConsumptionMonitor, value: float, limit: float) -> None:
        texts = MESSAGES["fr" if self.hass.config.language.startswith("fr") else "en"]
        message = texts[m.rule].format(
            name=m.name, value=value, limit=limit, unit=m.unit, window=m.window
        )
        data: dict[str, Any] = {
            "action": m.target,
            "title": texts["title"],
            "message": message,
            "tag": f"consumption_{m.id}",
        }
        if m.rule == "habit":
            # Any button click also discards the notification (existing tag handling).
            data["callback"] = [
                {"title": texts["normal"], "event": m.normal_action},
                {"title": texts["close"], "event": m.close_action},
            ]
        try:
            await self._send(data)
        except Exception:  # noqa: BLE001 - an alert failure must not stop monitoring
            _LOGGER.exception("Consumption alert for %s could not be sent", m.name)

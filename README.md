# Notifier (Home Assistant Custom Integration - HACS)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

**Notifier** is an intelligent notification management integration for Home Assistant (100% UI configurable, no YAML required). It is designed to be fully backwards-compatible with the former AppDaemon `notifier.py` app: **no changes are needed in your existing automations or scripts!**

---

## ✨ Features

- ⚙️ **100% UI Configurable:** Set up and manage persons, presence sensors, threshold, and always-home devices directly in Home Assistant (UI Settings -> Integrations).
- 🔄 **100% Backwards-Compatible:** Listens directly to the `NOTIFIER` and `NOTIFIER_DISCARD` events and handles the `mobile_app_notification_action` clicks automatically.
- 🎯 **Smart Targeting (`action`):**
  - `send_to_<name>`: Send directly to `<name>`'s phone.
  - `send_to_all`: Send to all configured persons and always-home devices (tablets/iPads).
  - `send_to_present`: Send to persons currently home (or within distance threshold).
  - `send_to_absent`: Send to absent persons.
  - `send_to_nearest`: Send to person(s) closest to home.
  - `send_when_present`: Send immediately if occupied, or queue (stage) notification and deliver as soon as the home becomes occupied.
- 🏷️ **Tag & Action Discard:** Click an action button on any device to automatically dismiss the notification on all other devices.
- ⏱️ **Watchers (`until`):** Keep notifications only while relevant (e.g. automatically dismiss notifications once a light turns off or the home becomes occupied).
- 🔔 **HA Service:** Also includes the `notifier.send` and `notifier.discard` services in addition to event triggers.

---

## 📦 Installation via HACS

1. In Home Assistant, open **HACS** > **Integrations**.
2. Click the 3 dots in the top right corner and choose **Custom repositories**.
3. Add repository: `https://github.com/Rimfire03/Notifier` with category **Integration**.
4. Click **Download** on the Notifier integration.
5. Restart Home Assistant.
6. In **Settings** > **Devices & Services** > **Add Integration**, search for **Notifier** and follow the configuration wizard.

---

## 🚀 Usage

### 1. Existing Automations (Events) - 100% Compatible

You do not need to change anything in your automations! Triggering `NOTIFIER` events works as before:

```yaml
service: event.fire  # or event in automation
event: NOTIFIER
event_data:
  action: send_to_present
  title: "Alerte Sécurité"
  message: "La porte d'entrée est restée ouverte."
  tag: "front_door_open"
  color: "red"
  icon: "mdi:door-open"
  callback:
    - title: "Fermer"
      event: "close_door"
      destructive: false
  until:
    - entity_id: binary_sensor.front_door
      new_state: "off"
```

### 2. Direct Service Call (`notifier.send`)

You can also use the native service:

```yaml
service: notifier.send
data:
  action: send_when_present
  title: "Rappel Poubelles"
  message: "N'oublie pas de sortir le bac jaune ce soir !"
  tag: "trash_reminder"
```

---

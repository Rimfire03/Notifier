# 🔔 Notifier

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/v/release/Rimfire03/Notifier?include_prereleases)](https://github.com/Rimfire03/Notifier/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-Donate-orange.svg?logo=buy-me-a-coffee&logoColor=white)](https://buymeacoffee.com/slide598b)

> Smart notifications for **Home Assistant** (presence-aware targeting, staging, auto-discard), 100% configurable from the UI, ready for **HACS**.  
> *Des notifications intelligentes pour **Home Assistant** (ciblage selon la présence, mise en attente, suppression automatique), 100 % configurables depuis l'interface, prêtes pour **HACS**.*

> 💡 **Credits / Crédits:** inspired by the work of [jlpouffier](https://github.com/jlpouffier) on GitHub and his YouTube channel [@HorizonDomotique](https://www.youtube.com/@HorizonDomotique).

---

## ☕ Support / Soutenir le projet

If you find this integration helpful, consider buying me a coffee to support the development!  
*Si vous appréciez cette intégration, vous pouvez m'offrir un café pour soutenir le développement !*

<a href="https://buymeacoffee.com/slide598b" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 50px !important;width: 217px !important;" ></a>

---

## 🌐 Languages Supported / Langues Disponibles

- 🇬🇧 **English**
- 🇫🇷 **Français**

---

# 🇬🇧 English Documentation

Notifier is fully backwards-compatible with the former AppDaemon `notifier.py` app: **your existing automations and scripts keep working unchanged** (they fire the `NOTIFIER` event).

## ✨ Features

- ⚙️ **100% UI configurable, no YAML:** persons, presence sensor, proximity threshold and always-home devices are managed in **Settings → Devices & services**. Notification services are picked from a dropdown.
- 🔄 **Backwards-compatible:** listens to the `NOTIFIER` and `NOTIFIER_DISCARD` events and to `mobile_app_notification_action` clicks.
- 🎯 **Smart targeting (`action`):**
  - `send_to_<name>`: send directly to that person's phone.
  - `send_to_all`: all persons and always-home devices (tablets).
  - `send_to_present`: persons at home (or within the distance threshold).
  - `send_to_absent`: absent persons.
  - `send_to_nearest`: person(s) closest to home.
  - `send_when_present`: send now if home is occupied, otherwise stage it and deliver as soon as it becomes occupied.
- 🏷️ **Tag & discard:** clicking an action button dismisses the notification on every device.
- ⏱️ **Watchers (`until`):** automatically dismiss a notification once an entity reaches a state (light off, home occupied...).
- 🔔 **Services:** `notifier.send` and `notifier.discard`, in addition to the events.

## 📦 Installation

### Method 1: Via HACS (custom repository)

1. In Home Assistant, open **HACS** → menu (⋮) → **Custom repositories**.
2. Add `https://github.com/Rimfire03/Notifier`, category **Integration**.
3. Search for **Notifier** in HACS and click **Download**.
4. Restart Home Assistant.

### Method 2: Manual

Copy `custom_components/notifier` into your Home Assistant `custom_components` folder and restart.

## ⚙️ Setup

Entirely from the UI: **Settings → Devices & services → Add integration → Notifier**.

1. Name the **"Home occupied" sensor** (created automatically: on when at least one selected person is home) and set the proximity threshold. In **Configure → General settings** you choose which persons it counts; the sensor lists them in its `persons` and `persons_home` attributes.
2. Add each **person** (name, `person.*`/`device_tracker.*` entity, notification service, optional distance sensor). The name is used in `send_to_<name>`.
3. Add **always-home devices** (wall tablets...).
4. Change anything later via the integration's **Configure** button.

## 🚀 Usage

### Existing automations (event)

```yaml
event: NOTIFIER
event_data:
  action: send_to_present
  title: "Security alert"
  message: "The front door has been left open."
  tag: "front_door_open"
  color: "red"
  icon: "mdi:door-open"
  callback:
    - title: "Close"
      event: "close_door"
  until:
    - entity_id: binary_sensor.front_door
      new_state: "off"
```

### Service call

```yaml
service: notifier.send
data:
  action: send_when_present
  title: "Trash reminder"
  message: "Don't forget the yellow bin tonight!"
  tag: "trash_reminder"
```

Supported fields: `action`, `title`, `message`, `tag`, `timeout`, `image_url`, `click_url`, `icon`, `color`, `persistent`, `interuption_level`, `siri_shortcut_name`, `callback`, `until`.

### Consumption monitoring (optional)

In **Configure → Add a consumption monitor**, pick a water or electricity sensor (cumulative meter or instant value), a rule and who to notify. Nothing changes if you add none. Each monitor creates a problem `binary_sensor` and sends an alert through the usual targets (`send_to_all`, `send_to_present`...), then waits for its cooldown before repeating.

| Rule | Alert when |
|------|-----------|
| Threshold | consumption over the window exceeds the threshold (cumulative: increase; instant: average) |
| Continuous | the meter keeps moving for N hours without a pause of 1 h or more (possible leak) |
| Habit | once a day, at the time you choose, the last 24 h exceed 1.5 times the average of the same 24 h over the previous 7 days (needs 3 days of history) |

## 🏷️ Releases

Versions are automatic (`x.yy`, from the commit count): each push to `main` publishes a GitHub release and updates `manifest.json`. HACS offers it as an update.

---

# 🇫🇷 Documentation en Français

Notifier est entièrement rétrocompatible avec l'ancienne app AppDaemon `notifier.py` : **vos automatisations et scripts existants continuent de fonctionner sans changement** (ils déclenchent l'événement `NOTIFIER`).

## ✨ Fonctionnalités

- ⚙️ **100 % configurable depuis l'interface, sans YAML :** personnes, capteur de présence, seuil de proximité et appareils toujours présents se gèrent dans **Paramètres → Appareils et services**. Les services de notification se choisissent dans une liste déroulante.
- 🔄 **Rétrocompatible :** écoute les événements `NOTIFIER` et `NOTIFIER_DISCARD` ainsi que les clics `mobile_app_notification_action`.
- 🎯 **Ciblage intelligent (`action`) :**
  - `send_to_<nom>` : envoi direct au téléphone de cette personne.
  - `send_to_all` : toutes les personnes et les appareils toujours présents (tablettes).
  - `send_to_present` : personnes à la maison (ou sous le seuil de distance).
  - `send_to_absent` : personnes absentes.
  - `send_to_nearest` : personne(s) la/les plus proche(s) de la maison.
  - `send_when_present` : envoi immédiat si la maison est occupée, sinon mise en attente jusqu'à ce qu'elle le soit.
- 🏷️ **Tag & suppression :** cliquer sur un bouton d'action supprime la notification sur tous les appareils.
- ⏱️ **Surveillance (`until`) :** supprime automatiquement la notification quand une entité atteint un état (lumière éteinte, maison occupée...).
- 🔔 **Services :** `notifier.send` et `notifier.discard`, en plus des événements.

## 📦 Installation

### Méthode 1 : Via HACS (dépôt personnalisé)

1. Dans Home Assistant, ouvrez **HACS** → menu (⋮) → **Dépôts personnalisés**.
2. Ajoutez `https://github.com/Rimfire03/Notifier`, catégorie **Intégration**.
3. Recherchez **Notifier** dans HACS et cliquez sur **Télécharger**.
4. Redémarrez Home Assistant.

### Méthode 2 : Manuelle

Copiez `custom_components/notifier` dans le dossier `custom_components` de Home Assistant, puis redémarrez.

## ⚙️ Configuration

Entièrement via l'interface : **Paramètres → Appareils et services → Ajouter une intégration → Notifier**.

1. Nommez le **capteur « Maison occupée »** (créé automatiquement : actif dès qu'au moins une personne sélectionnée est à la maison) et réglez le seuil de proximité. Dans **Configurer → Paramètres généraux**, choisissez les personnes prises en compte ; le capteur les liste dans ses attributs `persons` et `persons_home`.
2. Ajoutez chaque **personne** (nom, entité `person.*`/`device_tracker.*`, service de notification, capteur de distance optionnel). Le nom sert dans `send_to_<nom>`.
3. Ajoutez les **appareils toujours présents** (tablettes murales...).
4. Modifiez tout plus tard avec le bouton **Configurer** de l'intégration.

## 🚀 Utilisation

Mêmes exemples que dans la section anglaise ci-dessus (événement `NOTIFIER` ou service `notifier.send`).

### Surveillance de la consommation (optionnelle)

Dans **Configurer → Ajouter une surveillance de consommation**, choisissez un capteur d'eau ou d'électricité (compteur cumulatif ou valeur instantanée), une règle et qui notifier. Rien ne change si vous n'en ajoutez aucune. Chaque surveillance crée un `binary_sensor` de type problème et envoie l'alerte par les cibles habituelles (`send_to_all`, `send_to_present`...), puis attend son délai avant de répéter.

| Règle | Alerte quand |
|-------|-------------|
| Seuil | la consommation sur la fenêtre dépasse le seuil (cumulatif : augmentation ; instantané : moyenne) |
| Continu | le compteur bouge sans pause d'au moins 1 h pendant N heures (fuite possible) |
| Habitude | une fois par jour, à l'heure choisie, les dernières 24 h dépassent 1,5 fois la moyenne des mêmes 24 h des 7 jours précédents (3 jours d'historique requis) |

## 🏷️ Versions

Les versions sont automatiques (`x.yy`, d'après le nombre de commits) : chaque push sur `main` publie une release GitHub et met à jour `manifest.json`. HACS la propose comme mise à jour.

---

## 📄 Licence

Projet open-source sous licence [MIT](LICENSE) - Développé pour la communauté Home Assistant par [Rimfire03](https://github.com/Rimfire03).

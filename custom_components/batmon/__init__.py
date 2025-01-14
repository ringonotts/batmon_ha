from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.discovery import async_discover
from .batmon import BatMonDataUpdateCoordinator
from .const import DOMAIN
import logging
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up BatMon integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up BatMon from a config entry."""
    coordinator = BatMonDataUpdateCoordinator(hass, config_entry=entry)

    # Perform an initial data refresh to populate the coordinator
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.error(f"Error refreshing coordinator: {err}")
        return False

    # Store the coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Forward platform setups
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "switch"])

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload BatMon integration."""
    coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
    if coordinator:
        coordinator.cancel_discovery_task()
    return await hass.config_entries.async_unload_platforms(entry, ["sensor", "switch"])


async def notify_new_devices(hass, coordinator):
    """Notify Home Assistant of new devices."""
    for device in coordinator.data.values():
        if device.get("status") == "new":
            # Notify Home Assistant of a new device
            await async_discover(
                hass,
                "batmon",
                {
                    "name": device["name"],
                    "address": device["address"],
                },
                "batmon",
            )
            device["status"] = "notified"  # Mark as notified

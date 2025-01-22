"""The Batmon BLE integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from bleak.backends.device import BLEDevice
from .batmon import BatMonBluetoothDeviceData, BatMonDevice
from bleak_retry_connector import close_stale_connections_by_address
from typing import TypeAlias

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.unit_system import METRIC_SYSTEM

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class BatMonBLEDataUpdateCoordinator(DataUpdateCoordinator[BatMonDevice]):
    """Class to manage fetching Batmon BLE data."""

    ble_device: BLEDevice
    config_entry: BatMonBLEConfigEntry

    def __init__(self, hass: HomeAssistant, entry: BatMonBLEConfigEntry) -> None:
        """Initialize the coordinator."""
        self.state_of_charge_required = entry.data.get(
            "state_of_charge_required", False)
        self.battery_capacity = entry.data.get("battery_capacity", None)

        _LOGGER.debug(
            "Setting up BatMon BLE: State of Charge Required = %s, Battery Capacity = %s",
            self.state_of_charge_required,
            self.battery_capacity,
        )

        self.batmon = BatMonBluetoothDeviceData(
            _LOGGER, hass.config.units is METRIC_SYSTEM
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_setup(self) -> None:
        """Set up the coordinator."""
        address = self.config_entry.unique_id

        assert address is not None

        await close_stale_connections_by_address(address)

        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, address)

        if not ble_device:
            raise ConfigEntryNotReady(
                f"Could not find Batmon device with address {address}"
            )
        self.ble_device = ble_device

    async def _async_update_data(self) -> BatMonDevice:
        """Get data from Batmon BLE."""
        try:
            data = await self.batmon.update_device(self.ble_device, self.state_of_charge_required, self.battery_capacity)
        except Exception as err:
            raise UpdateFailed(f"Unable to fetch data: {err}") from err

        return data


BatMonBLEConfigEntry: TypeAlias = ConfigEntry[BatMonBLEDataUpdateCoordinator]

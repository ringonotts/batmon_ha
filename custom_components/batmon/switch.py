"""Support for BatMon ble Switches."""

from __future__ import annotations

import logging

from .batmon import BatMonBluetoothDeviceData, BatMonDevice, BatmonSensorCommand, BmConst, CPPushByteArray

from .const import DOMAIN, UUID_SENSORS_COMMAND
from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.const import (
    Platform,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import (
    RegistryEntry,
    async_entries_for_device,
)
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.unit_system import METRIC_SYSTEM
from homeassistant.components import bluetooth
from bleak_retry_connector import close_stale_connections_by_address
from homeassistant.exceptions import ConfigEntryNotReady

from .coordinator import BatMonBLEDataUpdateCoordinator, BatMonBLEConfigEntry

_LOGGER = logging.getLogger(__name__)

SWITCH_MAPPING_TEMPLATE: dict[str, SwitchEntityDescription] = {
    "relay_state": SwitchEntityDescription(
        key="relay_state",
        name="Relay State",
    ),
    "switch_state": SwitchEntityDescription(
        key="switch_state",
        name="Switch State",
    ),
}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: BatMonBLEConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BatMon BLE sensors."""
    coordinator = entry.runtime_data
    
    entities = []
    switch_mapping = SWITCH_MAPPING_TEMPLATE.copy()
    _LOGGER.debug("got sensors: %s", coordinator.data.sensors)
    for switch_type, sensor_value in coordinator.data.sensors.items():
        if switch_type not in switch_mapping:
            _LOGGER.warning(f"SWITCH type {switch_type} not in sensors mapping")
            continue
        entities.append(
            BatMonSwitch(coordinator, coordinator.data, switch_mapping[switch_type])
        )

    async_add_entities(entities)


class BatMonSwitch(
    CoordinatorEntity[BatMonBLEDataUpdateCoordinator], SwitchEntity
):
    """BatMon BLE Switch for the device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BatMonBLEDataUpdateCoordinator,
        batmon_device: BatMonDevice,
        entity_description: SwitchEntityDescription,
    ) -> None:
        """Populate the BatMon entity with relevant data."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self.batmon_device = batmon_device

        name = batmon_device.name
        self._attr_unique_id = f"{batmon_device.address}_{entity_description.key}"
        self.attribute = entity_description.key
        _LOGGER.debug(f"SWITCH Coordinator BatMon Sensor name: {name}, unique_id: {self._attr_unique_id}, attribute: {self.attribute}")
        self._attr_device_info = DeviceInfo(
            connections={
                (
                    CONNECTION_BLUETOOTH,
                    batmon_device.address,
                )
            },
            name=name,
        )

    @property
    def is_on(self):
        """Return the state of the binary sensor."""
        return self.coordinator.data.sensors.get(self.attribute, False)

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        _LOGGER.debug(f"Turning ON switch {
                      self.name} ({self.attribute})")
        ret = await self._send_switch_command(self.attribute, True)
        # Update the coordinator's data to reflect the new state
        self.coordinator.data.sensors[self.attribute] = ret
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        _LOGGER.debug(f"Turning OFF switch {
                      self.name} ({self.attribute})")
        ret = await self._send_switch_command(self.attribute, False)
        # Update the coordinator's data to reflect the new state
        self.coordinator.data.sensors[self.attribute] = ret
        self.async_write_ha_state()


    async def _send_switch_command(self, attr, turn_on):
        address = self.batmon_device.address

        assert address is not None

        await close_stale_connections_by_address(address)

        ble_device = bluetooth.async_ble_device_from_address(self.hass, address)

        if not ble_device:
            raise ConfigEntryNotReady(
                f"Could not find Batmon device with address {address}"
            )
        batmon = BatMonBluetoothDeviceData( _LOGGER, self.hass.config.units is METRIC_SYSTEM)
        ret = await batmon.send_switch_command(ble_device, attr, turn_on)
        return ret
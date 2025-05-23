"""Config flow for BatMon BLE integration."""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from bleak import BleakError
import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfo,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN
from .batmon import BatMonBluetoothDeviceData, BatMonDevice

_LOGGER = logging.getLogger(__name__)

SERVICE_UUIDS = [
    "00000000-cc7a-482a-984a-7f2ed5b3e58f",
]


@dataclasses.dataclass
class Discovery:
    """A discovered bluetooth device."""
    name: str
    discovery_info: BluetoothServiceInfo
    device: BatMonDevice


def get_name(device: BatMonDevice) -> str:
    """Generate name with model and identifier for device."""
    return device.friendly_name()


class BatMonDeviceUpdateError(Exception):
    """Custom error class for device updates."""


class BatMonConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BatMon BLE."""
    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_device: Discovery | None = None
        self._discovered_devices: dict[str, Discovery] = {}

    async def _get_device_data(
        self, discovery_info: BluetoothServiceInfo
    ) -> BatMonDevice:
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, discovery_info.address
        )
        if ble_device is None:
            _LOGGER.debug("No BLE device in _get_device_data")
            raise BatMonDeviceUpdateError("No BLE device")

        BatMon = BatMonBluetoothDeviceData()
        try:
            data = await BatMon.update_device(ble_device, False, "0")
        except BleakError as err:
            _LOGGER.error(
                "Error connecting to and getting data from %s: %s", discovery_info.address, err)
            raise BatMonDeviceUpdateError(
                "Failed getting device data") from err
        except Exception as err:
            _LOGGER.error("Unknown error occurred from %s: %s",
                          discovery_info.address, err)
            raise
        return data

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfo
    ) -> ConfigFlowResult:
        """Handle the Bluetooth discovery step."""
        _LOGGER.debug("Discovered BT device: %s", discovery_info)
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        try:
            device = await self._get_device_data(discovery_info)
        except BatMonDeviceUpdateError:
            return self.async_abort(reason="cannot_connect")
        except Exception:
            return self.async_abort(reason="unknown")

        name = get_name(device)
        self.context["title_placeholders"] = {"name": name}
        self._discovered_device = Discovery(name, discovery_info, device)

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery and ask for additional settings."""
        if user_input is not None:
            user_input["address"] = self._discovered_device.discovery_info.address
            return self.async_create_entry(
                title=self.context["title_placeholders"]["name"],
                data=user_input,
            )

        # Create the form for user input
        data_schema = vol.Schema({
            vol.Required("state_of_charge_required", default=False): bool,
            vol.Optional("battery_capacity", default=""): str,
        })

        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=data_schema,
            description_placeholders=self.context["title_placeholders"],
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step to pick discovered device."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            discovery = self._discovered_devices[address]

            self.context["title_placeholders"] = {"name": discovery.name}
            self._discovered_device = discovery

            return await self.async_step_bluetooth_confirm()

        current_addresses = self._async_current_ids()
        for discovery_info in async_discovered_service_info(self.hass):
            address = discovery_info.address
            if address in current_addresses or address in self._discovered_devices:
                continue

            if not any(uuid in SERVICE_UUIDS for uuid in discovery_info.service_uuids):
                continue

            try:
                device = await self._get_device_data(discovery_info)
            except BatMonDeviceUpdateError:
                continue
            except Exception:
                continue

            name = get_name(device)
            self._discovered_devices[address] = Discovery(
                name, discovery_info, device)

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        titles = {address: discovery.name for address,
                  discovery in self._discovered_devices.items()}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In(titles)}),
        )

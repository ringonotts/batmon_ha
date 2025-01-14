import asyncio
from bleak import BleakClient
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers import device_registry as dr
from datetime import datetime, timedelta
import logging

from .const import SCAN_INTERVAL, UUID_SENSORS_COMMAND, DOMAIN, BatmonSensorCommand, BmConst, CPPushByteArray

_LOGGER = logging.getLogger(__name__)


class BatMonDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator for fetching BatMon sensor data."""

    def __init__(self, hass, config_entry):
        """Initialize the coordinator."""
        self.config_entry = config_entry
        self.data = {}
        self.device_locks = {}  # Store locks for each device
        # Remember config_entry has to be configured above here!
        super().__init__(
            hass,
            _LOGGER,
            name="BatMon",
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )

    @property
    def config(self):
        """Convenience property to access static configuration data."""
        return self.config_entry.data

    async def _async_update_data(self):

        _LOGGER.debug(f"_async_update_data called at {datetime.now()}")
        try:
            """Fetch data for existing devices."""
            if "devices" not in self.config:
                _LOGGER.error(
                    "No 'devices' key found in config. Please check your configuration.")
                return {}

            # Ensure self.data is a dictionary
            if self.data is None:
                _LOGGER.warning(
                    "self.data was None, resetting to an empty dictionary.")
                self.data = {}

            # Fetch data for existing devices
            for device in self.config.get("devices", []):
                mac = device.get("mac_address")
                name = device.get("name")
                capacity = device.get("battery_size_ah")
                is_soc_required = device.get("state_of_charge_handling")

                if not mac:
                    _LOGGER.warning(
                        f"Skipping device {name} due to missing MAC address.")
                    continue
                if name not in self.data:
                    self.data[name] = {
                        "name": name,
                        "address": mac,
                        "sensors": {},
                        "registered": False,
                    }

                if name not in self.device_locks:
                    self.device_locks[name] = asyncio.Lock()

                async with self.device_locks[name]:
                    client = BleakClient(mac)
                    await client.connect()
                    _LOGGER.info(f"Connected to {name} ({mac})")
                    self.data[name]["sensors"] = await self.fetch_batmon_data(client, name, capacity, is_soc_required)
                    if "registered" not in self.data[name]:
                        self.data[name]["registered"] = True
                        self.register_device(
                            self.hass, self.config_entry, device)
                    await client.disconnect()
                    _LOGGER.info(f"Disconnected from {name} ({mac})")
        except Exception as e:
            _LOGGER.error(f"Error during polling: {e}")
            raise e

        return self.data

    def register_device(self, hass, config_entry, device):
        """Register a BatMon device in Home Assistant."""
        device_registry = dr.async_get(hass)
        device_registry.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            # Unique identifier for the device
            identifiers={(DOMAIN, device["mac_address"])},
            manufacturer="Monitor of Things",              # Manufacturer name
            name=device["name"],                           # Device name
            model="BatMon",                       # Device model
            sw_version="1.0",                              # Optional: software version
        )

    async def fetch_batmon_sensor_data(self, client, sensor_type):
        mode = BmConst.Mode.VALUE
        raw = CPPushByteArray()
        raw.pushI08(sensor_type)
        raw.pushI08(mode)
        raw.pushI08(0)
        n = raw.getList()
        await client.write_gatt_char(UUID_SENSORS_COMMAND, n, response=True)
        data = await client.read_gatt_char(UUID_SENSORS_COMMAND)
        return BatmonSensorCommand(data)

    def calculate_state_of_charge(self, capacity, max_ah, amp_hours):
        tmp_ah = 0
        if max_ah > 0:
            tmp_ah = max_ah
        return round(100 + (((amp_hours-tmp_ah) / capacity) * 100), 1)

    async def fetch_batmon_max_sensor_data(self, client, sensor_type):
        mode = BmConst.Mode.MAX
        raw = CPPushByteArray()
        raw.pushI08(sensor_type)
        raw.pushI08(mode)
        raw.pushI08(0)
        n = raw.getList()
        await client.write_gatt_char(UUID_SENSORS_COMMAND, n, response=True)
        data = await client.read_gatt_char(UUID_SENSORS_COMMAND)
        return BatmonSensorCommand(data)

    async def fetch_batmon_data(self, client, name, capacity, is_soc_required):
        """Fetch sensor data for a specific BatMon device."""
        data = {}
        for attr, sensor_type in [
            ("volts", BmConst.Type.BAT_VOLTS),
            ("ext_volts", BmConst.Type.EXT_VOLTS),
            ("current", BmConst.Type.BAT_CURRENT),
            ("int_temperature", BmConst.Type.INT_TEMP),
            ("ext_temperature", BmConst.Type.EXT_TEMP),
            ("watt_hours", BmConst.Type.BAT_AMPHOURS),
            ("relay_state", BmConst.Type.RELAY_PIN),  # RELAY_PIN_STATE
            ("switch_state", BmConst.Type.SWITCH_PIN),  # IO_PIN_STATE
            ("state_of_charge", BmConst.Type.BAT_AMPHOURS),
            ("amp_hours", BmConst.Type.BAT_AMPHOURS),
        ]:
            try:
                response = await self.fetch_batmon_sensor_data(client, sensor_type)
                if attr in ["volts", "ext_volts", "int_temperature", "ext_temperature"]:
                    data[attr] = round(
                        response.value, 2) if response.value is not None else None
                elif attr in ["current"]:
                    data[attr] = round(
                        response.value, 2) if response.value is not None else None
                    # Lets add Watts to this now we have voltage and current
                    data["watts"] = round(
                        (response.value * data["volts"]), 2) if response.value is not None else None
                elif attr in ["watt_hours"]:
                    amp_hours = round(
                        response.value, 2) if response.value is not None else None
                    data[attr] = round(
                        (amp_hours * data["volts"]), 2) if response.value is not None else None
                    max_ah = await self.fetch_batmon_max_sensor_data(client, sensor_type)
                elif attr in ["relay_state", "switch_state"]:
                    data[attr] = bool(
                        response.value) if response.value is not None else None
                elif attr in ["state_of_charge"]:
                    data[attr] = 0
                    if is_soc_required == "Calculate State of Charge":
                        data[attr] = self.calculate_state_of_charge(
                            capacity, max_ah.maxValue, amp_hours)
                elif attr in ["amp_hours"]:
                    data[attr] = amp_hours

            except Exception as e:
                _LOGGER.warning(f"Error fetching {attr} for {name}: {e}")

        return data

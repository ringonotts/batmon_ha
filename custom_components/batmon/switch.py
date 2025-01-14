from bleak import BleakClient
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, SWITCH_DESCRIPTIONS, UUID_DEVICE_API, UUID_SENSORS_COMMAND, BatmonSensorCommand, BmConst, CPPushByteArray
import logging
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up BatMon binary sensors dynamically."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = []

    # Iterate over devices and their binary sensor attributes
    for device_name, device_data in coordinator.data.items():
        for attribute, description in SWITCH_DESCRIPTIONS.items():
            if "sensors" in device_data and attribute in device_data["sensors"]:
                # if attribute in device_data:
                entities.append(BatMonSwitch(
                    coordinator, device_name, attribute, description))

    async_add_entities(entities)


class BatMonSwitch(CoordinatorEntity, SwitchEntity):
    """Representation of a BatMon binary sensor."""
    _attr_has_entity_name = True

    def __init__(self, coordinator, device_name, attribute, description):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.device_name = device_name
        self.attribute = attribute
        self.entity_description = description
        self._attr_unique_id = f"{device_name}_{attribute}"

    @property
    def mac_address(self):
        """Return the MAC address for the device."""
        device_data = self.coordinator.data.get(self.device_name)
        if device_data:
            return device_data.get("address")
        return None

    @property
    def is_on(self):
        """Return the state of the binary sensor."""
        return self.coordinator.data[self.device_name]["sensors"].get(self.attribute)

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        _LOGGER.debug(f"Turning ON switch {
                      self.device_name} ({self.attribute})")
        await self._send_switch_command(self.attribute, True)
        # Update the coordinator's data to reflect the new state
        self.coordinator.data[self.device_name]["sensors"][self.attribute] = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        _LOGGER.debug(f"Turning OFF switch {
                      self.device_name} ({self.attribute})")
        await self._send_switch_command(self.attribute, False)
        # Update the coordinator's data to reflect the new state
        self.coordinator.data[self.device_name]["sensors"][self.attribute] = False
        self.async_write_ha_state()

    @property
    def name(self):
        """Return the name of the binary sensor."""
        # return f"{self.device_name} {self.entity_description.key.capitalize()}"
        return f"{self.device_name} {self.entity_description.name}"

    @property
    def unique_id(self):
        """Return a unique ID for the binary sensor."""
        return f"{self.device_name}_{self.entity_description.key}"

    @property
    def device_info(self):
        """Return device information for grouping entities."""
        return {
            # Unique identifier for the device
            "identifiers": {(DOMAIN, self.device_name)},
            "name": "BatMon",  # Group name shown in the UI
            "manufacturer": "Monitor of Things",
            "model": "BatMon Sensor",
            "sw_version": "1.0",
            "entry_type": None,  # Explicitly avoid marking this as a "control" entity
        }

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

    async def _send_switch_command(self, attr, turn_on: bool):
        """Send a command over Bluetooth to turn the relay or switch on or off."""
        int_value = 0
        io_type = 2  # 3 == Switch. 2 == Relay
        api_ref = 606
        sensor_type = BmConst.Type.RELAY_PIN
        if attr == "switch_state":
            sensor_type = BmConst.Type.SWITCH_PIN
            io_type = 3

        if turn_on:
            int_value = 1

        raw = CPPushByteArray()
        raw.pushI16(api_ref)
        raw.pushI08(1)  # Next arg is a int32
        raw.pushI32(io_type)
        raw.pushI08(1)  # Next arg is a int32
        raw.pushI32(int_value)
        raw.pushI08(0)  # Null terminator
        raw_list = raw.getList()

        mac = self.mac_address
        if not mac:
            _LOGGER.error(f"MAC address for {self.device_name} not found.")
            return

        lock = self.coordinator.device_locks.get(self.device_name)
        if lock is None:
            _LOGGER.error(f"No lock found for device {self.device_name}.")
            return

        async with lock:
            client = BleakClient(mac)
            await client.connect()
            ret = await client.write_gatt_char(UUID_DEVICE_API, raw_list, response=True)
            response = await self.fetch_batmon_sensor_data(client, sensor_type)
            new_state = bool(
                response.value) if response.value is not None else None
            _LOGGER.debug(f"New state of switch: {new_state} .")
            await client.disconnect()

import asyncio
from enum import IntEnum
from functools import partial
import logging
from struct import pack, unpack
import sys
from bleak import BleakClient, BleakError
from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from async_interrupt import interrupt

from .const import DEFAULT_MAX_UPDATE_ATTEMPTS, UPDATE_TIMEOUT, UUID_DEVICE_API, UUID_SENSORS_COMMAND

if sys.version_info[:2] < (3, 11):
    from async_timeout import timeout as asyncio_timeout
else:
    from asyncio import timeout as asyncio_timeout

_LOGGER = logging.getLogger(__name__)


class DisconnectedError(Exception):
    """Disconnected from device."""


class UnsupportedDeviceError(Exception):
    """Unsupported device."""


class BmConst:
    class Mode(IntEnum):
        VALUE = 0
        MIN = 1
        MAX = 2
        LIN_EQU = 20
        TEMPCO = 21
        THRESHOLD = 22
        RESET_MINMAX = 23

    class Type(IntEnum):
        BAT_VOLTS = 0
        EXT_VOLTS = 1
        INT_TEMP = 2
        EXT_TEMP = 3
        BAT_CURRENT = 4
        BAT_AMPHOURS = 5
        RELAY_PIN = 6
        SWITCH_PIN = 7
        MAX_TYPES = 7


class CPopByteArray:
    def init(self, raw):
        self.m_BinStr = ''.join(format(byte, '08b') for byte in raw)
        self.m_Index = 0

    def popBin(self, numBits):
        s = self.m_BinStr[:numBits]
        self.m_BinStr = self.m_BinStr[numBits:]
        return s if s != '' else '0'

    def binToUint(self, sbin):
        return int(sbin, 2)

    def UintToSigned(self, val, bits):
        if val >= 1 << (bits - 1):
            val -= 1 << bits
        return val

    def popU08(self):
        return self.binToUint(self.popBin(8))

    def popI08(self):
        return self.UintToSigned(self.popU08(), 8)

    def popU32(self):
        return int(self.popBin(32), 2)

    def popFlt(self):
        s = self.popBin(32)
        return unpack('>f', pack('I', int(s, 2)))[0]


class BatmonSensorCommand:
    def __init__(self, received_bytes):
        popv = CPopByteArray()
        popv.init(received_bytes)
        self.type = popv.popU08()
        self.mode = popv.popU08()
        self.len = popv.popU08()

        if self.mode == BmConst.Mode.VALUE:
            self.value = popv.popFlt()
        elif self.mode == BmConst.Mode.MIN:
            self.minValue = popv.popFlt()
            self.minEpoch = popv.popU32()
        elif self.mode == BmConst.Mode.MAX:
            self.maxValue = popv.popFlt()
            self.maxEpoch = popv.popU32()


class CPPushByteArray:
    def __init__(self):
        self.data = bytearray()

    def pushI08(self, value):
        self.data.append(value & 0xff)

    def pushI16(self, value):
        self.pushI08(value & 0xff)
        self.pushI08((value >> 8) & 0xff)

    def pushI32(self, value):
        self.pushI08(value & 0xff)
        self.pushI08((value >> 8) & 0xff)
        self.pushI08((value >> 16) & 0xff)
        self.pushI08((value >> 24) & 0xff)

    def getList(self):
        return bytes(self.data)


BATMON_SENSOR_MAPPING = [
    ("volts", BmConst.Type.BAT_VOLTS),
    ("volts_ext", BmConst.Type.EXT_VOLTS),
    ("current", BmConst.Type.BAT_CURRENT),
    ("int_temperature", BmConst.Type.INT_TEMP),
    ("ext_temperature", BmConst.Type.EXT_TEMP),
    ("watt_hours", BmConst.Type.BAT_AMPHOURS),
    ("relay_state", BmConst.Type.RELAY_PIN),  # RELAY_PIN_STATE
    ("switch_state", BmConst.Type.SWITCH_PIN),  # IO_PIN_STATE
    ("state_of_charge", BmConst.Type.BAT_AMPHOURS),
    ("amp_hours", BmConst.Type.BAT_AMPHOURS),
]

# class BatMonDeviceInfo:
#     """Response data with information about the BatMon device without sensors."""
#     def __init__(self, name: str, address: str = "", did_first_sync: bool = False):
#         self.name = name
#         self.address = address
#         self.did_first_sync = did_first_sync
#         self.name = name

#     address: str = ""
#     did_first_sync: bool = False

#     def friendly_name(self) -> str:
#         return self.name


class BatMonDevice():
    """Response data with information about the BatMon device"""

    def __init__(self, name: str, address: str):
        self.name = name
        if name.startswith("BK-"):
            # Slice the string to remove the first three characters
            self.name = name[3:]
        self.address = address
        self.sensors: dict[str, str | float | None] = {}

    def friendly_name(self) -> str:
        """Generate a name for the device."""
        return self.name


class BatMonBluetoothDeviceData:
    """Data for BatMon BLE sensors."""

    def __init__(
        self,
        is_metric: bool = True,
        max_attempts: int = DEFAULT_MAX_UPDATE_ATTEMPTS,
    ) -> None:
        """Initialize the BatMon BLE sensor data object."""
        self.is_metric = is_metric
        self.max_attempts = max_attempts

    def set_max_attempts(self, max_attempts: int) -> None:
        """Set the number of attempts."""
        self.max_attempts = max_attempts

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
        try:
            capacity = float(capacity)
            max_ah = float(max_ah)
            amp_hours = float(amp_hours)
        except ValueError as e:
            raise ValueError(
                f"Invalid input to calculate_state_of_charge: {e}")

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

    async def fetch_batmon_data(self, client, device, capacity, is_soc_required):
        """Fetch sensor data for a specific BatMon device."""
        data = {}
        name = device.name
        amp_hours = None
        max_ah = None

        for attr, sensor_type in BATMON_SENSOR_MAPPING:
            try:
                response = await self.fetch_batmon_sensor_data(client, sensor_type)
                if attr in ["volts", "volts_ext", "int_temperature", "ext_temperature"]:
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
                    if is_soc_required == True:
                        data[attr] = self.calculate_state_of_charge(
                            capacity, max_ah.maxValue, amp_hours)
                elif attr in ["amp_hours"]:
                    data[attr] = amp_hours

            except Exception as e:
                _LOGGER.warning(f"Error fetching {attr} for {name}: {e}")

        return data

    def _handle_disconnect(
        self, disconnect_future: asyncio.Future[bool], client: BleakClient
    ) -> None:
        """Handle disconnect from device."""
        _LOGGER.debug(f"Disconnected from:  {client.address}")
        if not disconnect_future.done():
            disconnect_future.set_result(True)

    async def update_device(self, ble_device: BLEDevice, is_soc_required, capacity) -> BatMonDevice:
        """Connects to the device through BLE and retrieves relevant data"""
        for attempt in range(self.max_attempts):
            is_final_attempt = attempt == self.max_attempts - 1
            try:
                return await self._update_device(ble_device, is_soc_required, capacity)
            except DisconnectedError:
                if is_final_attempt:
                    raise
                _LOGGER.debug(
                    "Unexpectedly disconnected from %s", ble_device.address
                )
            except BleakError as err:
                if is_final_attempt:
                    raise
                _LOGGER.debug("Bleak error: %s", err)
        raise RuntimeError("Should not reach this point")

    async def _update_device(self, ble_device: BLEDevice, is_soc_required, capacity) -> BatMonDevice:
        """Connects to the device through BLE and retrieves relevant data"""
        device = BatMonDevice(ble_device.name, ble_device.address)
        loop = asyncio.get_running_loop()
        disconnect_future = loop.create_future()
        client: BleakClientWithServiceCache = (
            await establish_connection(  # pylint: disable=line-too-long
                BleakClientWithServiceCache,
                ble_device,
                ble_device.address,
                disconnected_callback=partial(
                    self._handle_disconnect, disconnect_future
                ),
            )
        )
        try:
            async with interrupt(
                disconnect_future,
                DisconnectedError,
                f"Disconnected from {client.address}",
            ), asyncio_timeout(UPDATE_TIMEOUT):
                # _LOGGER.debug(f"Device:  {device.name}, is soc required: {is_soc_required}, capacity: {capacity}")
                device.sensors = await self.fetch_batmon_data(client, device, capacity, is_soc_required)
        except BleakError as err:
            if "not found" in str(err):  # In future bleak this is a named exception
                # Clear the char cache since a char is likely
                # missing from the cache
                await client.clear_cache()
            raise
        except UnsupportedDeviceError:
            await client.disconnect()
            raise
        finally:
            await client.disconnect()

        return device

    async def _set_batmon_switch(self, client, device, attr, turn_on):
        int_value = 0
        io_type = 2  # 3 == Switch. 2 == Relay
        api_ref = 606
        switch_type = BmConst.Type.RELAY_PIN
        if attr == "switch_state":
            switch_type = BmConst.Type.SWITCH_PIN
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

        ret = await client.write_gatt_char(UUID_DEVICE_API, raw_list, response=True)
        response = await self.fetch_batmon_sensor_data(client, switch_type)
        new_state = bool(
            response.value) if response.value is not None else None

        return new_state

    async def send_switch_command(self, ble_device: BLEDevice, attr, turn_on: bool):
        """Send a command over Bluetooth to turn the relay or switch on or off."""
        ret = False
        device = BatMonDevice(ble_device.name, ble_device.address)
        loop = asyncio.get_running_loop()
        disconnect_future = loop.create_future()
        client: BleakClientWithServiceCache = (
            await establish_connection(  # pylint: disable=line-too-long
                BleakClientWithServiceCache,
                ble_device,
                ble_device.address,
                disconnected_callback=partial(
                    self._handle_disconnect, disconnect_future
                ),
            )
        )
        try:
            async with interrupt(
                disconnect_future,
                DisconnectedError,
                f"Disconnected from {client.address}",
            ), asyncio_timeout(UPDATE_TIMEOUT):
                _LOGGER.debug(f"Sending relay switch command from:  {
                              client.address}")
                ret = await self._set_batmon_switch(client, device, attr, turn_on)
        except BleakError as err:
            if "not found" in str(err):  # In future bleak this is a named exception
                # Clear the char cache since a char is likely
                # missing from the cache
                await client.clear_cache()
            raise
        except UnsupportedDeviceError:
            await client.disconnect()
            raise
        finally:
            await client.disconnect()

        return ret

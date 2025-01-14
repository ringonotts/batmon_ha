from enum import IntEnum
from struct import pack, unpack
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.const import (
    UnitOfTemperature,
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfEnergy,
)
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.switch import SwitchEntityDescription

DOMAIN = "batmon"
SCAN_INTERVAL = 30  # Poll every 30 seconds
UUID_SENSORS_COMMAND = "00000303-8e22-4541-9d4c-21edae82ed19"
UUID_DEVICE_API = "00000105-8e22-4541-9d4c-21edae82ed19"


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


SWITCH_DESCRIPTIONS = {
    "relay_state": SwitchEntityDescription(
        key="relay_state",
        name="Relay State",
    ),
    "switch_state": SwitchEntityDescription(
        key="switch_state",
        name="Switch State",
    ),
}

SENSOR_DESCRIPTIONS = {
    "volts": SensorEntityDescription(
        key="volts",
        name="Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "ext_volts": SensorEntityDescription(
        key="ext_volts",
        name="External Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "current": SensorEntityDescription(
        key="current",
        name="Current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "watts": SensorEntityDescription(
        key="watts",
        name="Watts",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement="W",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "int_temperature": SensorEntityDescription(
        key="int_temperature",
        name="CPU Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "ext_temperature": SensorEntityDescription(
        key="ext_temperature",
        name="External Sensor Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "watt_hours": SensorEntityDescription(
        key="watt_hours",
        name="Watt Hours",
        device_class=None,  # No specific device class for watt-hours
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "amp_hours": SensorEntityDescription(
        key="amp_hours",
        name="Amp Hours",
        device_class=None,  # No specific device class for amp-hours
        native_unit_of_measurement="Ah",  # Custom unit
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "state_of_charge": SensorEntityDescription(
        key="state_of_charge",
        name="State of Charge",
        device_class=SensorDeviceClass.BATTERY,  # Device class for battery percentage
        native_unit_of_measurement="%",  # Unit for percentage
        # State class indicating this is a measurement
        state_class=SensorStateClass.MEASUREMENT,
    ),
}

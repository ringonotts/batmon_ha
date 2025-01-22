"""Support for BatMon ble sensors."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    Platform,
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfEnergy,
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

from .const import DOMAIN
from .batmon import BatMonDevice
from .coordinator import BatMonBLEDataUpdateCoordinator, BatMonBLEConfigEntry

_LOGGER = logging.getLogger(__name__)

SENSORS_MAPPING_TEMPLATE: dict[str, SensorEntityDescription] = {
    "volts": SensorEntityDescription(
        key="volts",
        name="Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "volts_ext": SensorEntityDescription(
        key="volts_ext",
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
        native_unit_of_measurement=PERCENTAGE,  # Unit for percentage
        # State class indicating this is a measurement
        state_class=SensorStateClass.MEASUREMENT,
    ),
}


@callback
def async_migrate(hass: HomeAssistant, address: str, sensor_name: str) -> None:
    """Migrate entities to new unique ids (with BLE Address)."""
    ent_reg = er.async_get(hass)
    unique_id_trailer = f"_{sensor_name}"
    new_unique_id = f"{address}{unique_id_trailer}"
    _LOGGER.debug(f"sensor async migrate Sensor: {DOMAIN}, uniquie ID: {new_unique_id} ")
    if ent_reg.async_get_entity_id(DOMAIN, Platform.SENSOR, new_unique_id):
        # New unique id already exists
        _LOGGER.debug(f"uniquie ID already exists: {new_unique_id} ")
        return
    dev_reg = dr.async_get(hass)
    if not (
        device := dev_reg.async_get_device(
            connections={(CONNECTION_BLUETOOTH, address)}
        )
    ):
        return
    entities = async_entries_for_device(
        ent_reg,
        device_id=device.id,
        include_disabled_entities=True,
    )
    matching_reg_entry: RegistryEntry | None = None
    for entry in entities:
        #_LOGGER.debug(f"Evaluating entity: {entry.unique_id} WITH: {unique_id_trailer}")
        if entry.unique_id.endswith(unique_id_trailer) and (
            not matching_reg_entry or "(" not in entry.unique_id
        ):
            matching_reg_entry = entry
    #_LOGGER.debug(f"MAtching entity: {matching_reg_entry.unique_id}, WITH: {new_unique_id}")
    if not matching_reg_entry or matching_reg_entry.unique_id == new_unique_id:
        # Already has the newest unique id format
        return
    entity_id = matching_reg_entry.entity_id
    ent_reg.async_update_entity(entity_id=entity_id, new_unique_id=new_unique_id)
    _LOGGER.debug("Migrated entity '%s' to unique id '%s'", entity_id, new_unique_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BatMonBLEConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BatMon BLE sensors."""
    is_metric = hass.config.units is METRIC_SYSTEM

    coordinator = entry.runtime_data

    # we need to change some units
    sensors_mapping = SENSORS_MAPPING_TEMPLATE.copy()
    # if not is_metric:
    #     for key, val in sensors_mapping.items():
    #         if val.native_unit_of_measurement is not VOLUME_BECQUEREL:
    #             continue
    #         sensors_mapping[key] = dataclasses.replace(
    #             val,
    #             native_unit_of_measurement=VOLUME_PICOCURIE,
    #             suggested_display_precision=1,
    #         )

    entities = []
    for sensor_type, sensor_value in coordinator.data.sensors.items():
        if sensor_type not in sensors_mapping:
            _LOGGER.warning(f"Sensor type {sensor_type} not in sensors mapping")
            continue
        async_migrate(hass, coordinator.data.address, sensor_type)
        _LOGGER.debug(f"SENSOR setup sensor type: {sensor_type}, mapping: {sensors_mapping[sensor_type]}")
        entities.append(
            BatMonSensor(coordinator, coordinator.data, sensors_mapping[sensor_type])
        )

    async_add_entities(entities)


class BatMonSensor(
    CoordinatorEntity[BatMonBLEDataUpdateCoordinator], SensorEntity
):
    """BatMon BLE sensors for the device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BatMonBLEDataUpdateCoordinator,
        batmon_device: BatMonDevice,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Populate the BatMon entity with relevant data."""
        super().__init__(coordinator)
        self.entity_description = entity_description

        name = batmon_device.name
        self._attr_unique_id = f"{batmon_device.address}_{entity_description.key}"
        _LOGGER.debug(f"SENSOR Coordinator BatMon Sensor name: {name}, unique_id: {self._attr_unique_id}")
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
    def available(self) -> bool:
        """Check if device and sensor is available in data."""
        return (
            super().available
            and self.entity_description.key in self.coordinator.data.sensors
        )

    @property
    def native_value(self) -> StateType:
        """Return the value reported by the sensor."""
        return self.coordinator.data.sensors[self.entity_description.key]

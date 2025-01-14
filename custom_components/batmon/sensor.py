from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .const import SENSOR_DESCRIPTIONS
import logging
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up BatMon sensors dynamically."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = []
    data_items = coordinator.data.items()

    for device_name, device_data in data_items:
        for attribute, description in SENSOR_DESCRIPTIONS.items():
            if "sensors" in device_data and attribute in device_data["sensors"]:
                _LOGGER.debug(f"Sensor entitiy being added: {
                              attribute}, {description}")
                entities.append(BatMonSensor(
                    coordinator, device_name, attribute, description))

    async_add_entities(entities)


class BatMonSensor(CoordinatorEntity, SensorEntity):
    """Representation of a BatMon sensor."""
    _attr_has_entity_name = True

    def __init__(self, coordinator, device_name, attribute, description):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.device_name = device_name
        self.attribute = attribute
        self.entity_description = description
        self._attr_unique_id = f"{device_name}_{attribute}"

    @property
    def name(self):
        """Return the name of the sensor."""
        # return f"{self.device_name} {self.entity_description.key.capitalize()}"
        return f"{self.device_name} {self.entity_description.name}"

    @property
    def unique_id(self):
        """Return a unique ID for the sensor."""
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

    @property
    def native_value(self):
        """Return the current value of the sensor."""
        return self.coordinator.data[self.device_name]["sensors"].get(self.attribute)

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement for the sensor."""
        return self.entity_description.native_unit_of_measurement

    @property
    def device_class(self):
        """Return the device class of the sensor."""
        return self.entity_description.device_class

    @property
    def state_class(self):
        """Return the state class of the sensor."""
        return self.entity_description.state_class

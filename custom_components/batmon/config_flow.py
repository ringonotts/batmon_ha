from .options_flow import BatMonOptionsFlow
import voluptuous as vol
from homeassistant import config_entries
import logging
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class BatMonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BatMon."""

    VERSION = 1

    def __init__(self):
        self.devices = []  # Temporary storage for devices

    async def async_step_user(self, user_input=None):
        """Handle the initial user setup step."""
        if user_input is not None:
            # Add the entered device to the list
            self.devices.append(
                {
                    "name": user_input["name"],
                    "mac_address": user_input["mac_address"],
                    "battery_size_ah": user_input.get("battery_size_ah", 0),
                    "state_of_charge_handling": user_input.get("state_of_charge_handling", "Ignore State of Charge"),
                }
            )

            # Check if the user wants to add another device
            if user_input.get("add_another", False):
                return await self.async_step_add_device()

            # Finalize setup and create the entry
            return self.async_create_entry(
                title="BatMon",
                data={"devices": self.devices, },
            )

        # Schema for the initial form
        schema = vol.Schema(
            {
                vol.Required("name"): str,
                vol.Required("mac_address"): str,
                vol.Required(
                    "state_of_charge_handling",
                    default="Ignore State of Charge",
                ): vol.In(["Calculate State of Charge", "Ignore State of Charge"]),
                vol.Optional("battery_size_ah", default=0): vol.All(vol.Coerce(int), vol.Range(min=0)),
                vol.Optional("add_another", default=False): bool,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            description_placeholders={
                "battery_size_ah": "Specify the battery size in Amp Hours (e.g., 105).",
            },
        )

    async def async_step_add_device(self, user_input=None):
        """Step for adding additional devices."""
        if user_input is not None:
            # Add the additional device
            self.devices.append(
                {
                    "name": user_input["name"],
                    "mac_address": user_input["mac_address"],
                    "battery_size_ah": user_input.get("battery_size_ah", 0),
                    "state_of_charge_handling": user_input.get("state_of_charge_handling", 0),
                }
            )

            # Check if the user wants to add another device
            if user_input.get("add_another", False):
                return await self.async_step_add_device()

            # Finalize setup and create the entry
            return self.async_create_entry(
                title="BatMon",
                data={"devices": self.devices},
            )

        # Schema for adding another device
        schema = vol.Schema(
            {
                vol.Required("name"): str,
                vol.Required("mac_address"): str,
                vol.Required(
                    "state_of_charge_handling",
                    default="Ignore State of Charge",
                ): vol.In(["Calculate State of Charge", "Ignore State of Charge"]),
                vol.Optional("battery_size_ah", default=0): vol.All(vol.Coerce(int), vol.Range(min=0)),
                vol.Optional("add_another", default=False): bool,
            }
        )

        return self.async_show_form(step_id="add_device", data_schema=schema)

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return BatMonOptionsFlow(config_entry)

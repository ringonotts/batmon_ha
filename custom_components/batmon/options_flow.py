from homeassistant import config_entries
import voluptuous as vol


class BatMonOptionsFlow(config_entries.OptionsFlow):
    """Handle BatMon options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the BatMon options."""
        if user_input is not None:
            # Save the updated settings
            return self.async_create_entry(title="", data=user_input)

        # Get current settings
        devices = self.config_entry.data.get("devices", [])
        current_state_of_charge_handling = self.config_entry.options.get(
            "state_of_charge_handling", "Ignore State of Charge"
        )
        current_battery_size = self.config_entry.options.get(
            "battery_size_ah", 105)

        # Build the schema dynamically
        schema_fields = {
            vol.Required(f"device_{i}_name", default=device["name"]): str
            for i, device in enumerate(devices)
        }

        schema_fields.update({
            vol.Required(f"device_{i}_mac_address", default=device["mac_address"]): str
            for i, device in enumerate(devices)
        })

        schema_fields.update({
            vol.Required(
                "state_of_charge_handling",
                default=current_state_of_charge_handling,
            ): vol.In(["Calculate State of Charge", "Ignore State of Charge"]),
        })

        # Add conditional fields based on state_of_charge_handling
        if current_state_of_charge_handling == "Calculate State of Charge":
            schema_fields.update({
                vol.Optional("battery_size_ah", default=current_battery_size): vol.All(
                    vol.Coerce(int), vol.Range(min=1)
                ),
            })

        # Create the final schema
        schema = vol.Schema(schema_fields)

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "battery_size_ah": "Specify the battery size in Amp Hours (e.g., 105).",
            },
        )

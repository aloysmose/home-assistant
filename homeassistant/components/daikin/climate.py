"""Support for the Daikin HVAC."""
import logging
import re

import voluptuous as vol

from homeassistant.components.climate import PLATFORM_SCHEMA, ClimateDevice
from homeassistant.const import (
    ATTR_TEMPERATURE, CONF_HOST, CONF_NAME, TEMP_CELSIUS)
from homeassistant.components.climate.const import (
    SUPPORT_TARGET_TEMPERATURE, SUPPORT_FAN_MODE, SUPPORT_PRESET_MODE,
    SUPPORT_SWING_MODE,
    HVAC_MODE_OFF, HVAC_MODE_HEAT, HVAC_MODE_COOL, HVAC_MODE_HEAT_COOL,
    HVAC_MODE_DRY, HVAC_MODE_FAN_ONLY,
    PRESET_AWAY, PRESET_NONE,
    ATTR_CURRENT_TEMPERATURE, ATTR_FAN_MODE,
    ATTR_HVAC_MODE, ATTR_SWING_MODE,
    ATTR_PRESET_MODE)
import homeassistant.helpers.config_validation as cv

from . import DOMAIN as DAIKIN_DOMAIN
from .const import (
    ATTR_INSIDE_TEMPERATURE, ATTR_OUTSIDE_TEMPERATURE, ATTR_STATE_OFF,
    ATTR_STATE_ON, ATTR_TARGET_TEMPERATURE)

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_NAME): cv.string,
})

HA_STATE_TO_DAIKIN = {
    HVAC_MODE_FAN_ONLY: 'fan',
    HVAC_MODE_DRY: 'dry',
    HVAC_MODE_COOL: 'cool',
    HVAC_MODE_HEAT: 'hot',
    HVAC_MODE_HEAT_COOL: 'auto',
    HVAC_MODE_OFF: 'off',
}

DAIKIN_TO_HA_STATE = {
    'fan': HVAC_MODE_FAN_ONLY,
    'dry': HVAC_MODE_DRY,
    'cool': HVAC_MODE_COOL,
    'hot': HVAC_MODE_HEAT,
    'auto': HVAC_MODE_HEAT_COOL,
    'off': HVAC_MODE_OFF,
}

HA_PRESET_TO_DAIKIN = {
    PRESET_AWAY: 'on',
    PRESET_NONE: 'off'
}

HA_ATTR_TO_DAIKIN = {
    ATTR_PRESET_MODE: 'en_hol',
    ATTR_HVAC_MODE: 'mode',
    ATTR_FAN_MODE: 'f_rate',
    ATTR_SWING_MODE: 'f_dir',
    ATTR_INSIDE_TEMPERATURE: 'htemp',
    ATTR_OUTSIDE_TEMPERATURE: 'otemp',
    ATTR_TARGET_TEMPERATURE: 'stemp'
}


async def async_setup_platform(
        hass, config, async_add_entities, discovery_info=None):
    """Old way of setting up the Daikin HVAC platform.

    Can only be called when a user accidentally mentions the platform in their
    config. But even in that case it would have been ignored.
    """
    pass


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Daikin climate based on config_entry."""
    daikin_api = hass.data[DAIKIN_DOMAIN].get(entry.entry_id)
    async_add_entities([DaikinClimate(daikin_api)])


class DaikinClimate(ClimateDevice):
    """Representation of a Daikin HVAC."""

    def __init__(self, api):
        """Initialize the climate device."""
        from pydaikin import appliance

        self._api = api
        self._list = {
            ATTR_HVAC_MODE: list(HA_STATE_TO_DAIKIN),
            ATTR_FAN_MODE: self._api.device.fan_rate,
            ATTR_SWING_MODE: list(
                map(
                    str.title,
                    appliance.daikin_values(HA_ATTR_TO_DAIKIN[ATTR_SWING_MODE])
                )
            ),
        }

        self._supported_features = SUPPORT_TARGET_TEMPERATURE

        if self._api.device.support_away_mode:
            self._supported_features |= SUPPORT_PRESET_MODE

        if self._api.device.support_fan_rate:
            self._supported_features |= SUPPORT_FAN_MODE

        if self._api.device.support_swing_mode:
            self._supported_features |= SUPPORT_SWING_MODE

    def get(self, key):
        """Retrieve device settings from API library cache."""
        value = None
        cast_to_float = False

        if key in [ATTR_TEMPERATURE, ATTR_INSIDE_TEMPERATURE,
                   ATTR_CURRENT_TEMPERATURE]:
            key = ATTR_INSIDE_TEMPERATURE

        daikin_attr = HA_ATTR_TO_DAIKIN.get(key)

        if key == ATTR_INSIDE_TEMPERATURE:
            value = self._api.device.values.get(daikin_attr)
            cast_to_float = True
        elif key == ATTR_TARGET_TEMPERATURE:
            value = self._api.device.values.get(daikin_attr)
            cast_to_float = True
        elif key == ATTR_OUTSIDE_TEMPERATURE:
            value = self._api.device.values.get(daikin_attr)
            cast_to_float = True
        elif key == ATTR_FAN_MODE:
            value = self._api.device.represent(daikin_attr)[1].title()
        elif key == ATTR_SWING_MODE:
            value = self._api.device.represent(daikin_attr)[1].title()
        elif key == ATTR_HVAC_MODE:
            # Daikin can return also internal states auto-1 or auto-7
            # and we need to translate them as AUTO
            daikin_mode = re.sub(
                '[^a-z]', '',
                self._api.device.represent(daikin_attr)[1])
            ha_mode = DAIKIN_TO_HA_STATE.get(daikin_mode)
            value = ha_mode
        elif key == ATTR_PRESET_MODE:
            if self._api.device.represent(
                    daikin_attr)[1] == HA_PRESET_TO_DAIKIN[PRESET_AWAY]:
                return PRESET_AWAY
            return PRESET_NONE

        if value is None:
            _LOGGER.error("Invalid value requested for key %s", key)
        else:
            if value in ("-", "--"):
                value = None
            elif cast_to_float:
                try:
                    value = float(value)
                except ValueError:
                    value = None

        return value

    async def _set(self, settings):
        """Set device settings using API."""
        values = {}

        for attr in [ATTR_TEMPERATURE, ATTR_FAN_MODE, ATTR_SWING_MODE,
                     ATTR_HVAC_MODE]:
            value = settings.get(attr)
            if value is None:
                continue

            daikin_attr = HA_ATTR_TO_DAIKIN.get(attr)
            if daikin_attr is not None:
                if attr == ATTR_HVAC_MODE:
                    values[daikin_attr] = HA_STATE_TO_DAIKIN[value]
                elif value in self._list[attr]:
                    values[daikin_attr] = value.lower()
                else:
                    _LOGGER.error("Invalid value %s for %s", attr, value)

            # temperature
            elif attr == ATTR_TEMPERATURE:
                try:
                    values['stemp'] = str(int(value))
                except ValueError:
                    _LOGGER.error("Invalid temperature %s", value)

        if values:
            await self._api.device.set(values)

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._supported_features

    @property
    def name(self):
        """Return the name of the thermostat, if any."""
        return self._api.name

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._api.mac

    @property
    def temperature_unit(self):
        """Return the unit of measurement which this thermostat uses."""
        return TEMP_CELSIUS

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self.get(ATTR_CURRENT_TEMPERATURE)

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self.get(ATTR_TARGET_TEMPERATURE)

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return 1

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        await self._set(kwargs)

    @property
    def hvac_mode(self):
        """Return current operation ie. heat, cool, idle."""
        return self.get(ATTR_HVAC_MODE)

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        return self._list.get(ATTR_HVAC_MODE)

    async def async_set_hvac_mode(self, hvac_mode):
        """Set HVAC mode."""
        await self._set({ATTR_HVAC_MODE: hvac_mode})

    @property
    def fan_mode(self):
        """Return the fan setting."""
        return self.get(ATTR_FAN_MODE)

    async def async_set_fan_mode(self, fan_mode):
        """Set fan mode."""
        await self._set({ATTR_FAN_MODE: fan_mode})

    @property
    def fan_modes(self):
        """List of available fan modes."""
        return self._list.get(ATTR_FAN_MODE)

    @property
    def swing_mode(self):
        """Return the fan setting."""
        return self.get(ATTR_SWING_MODE)

    async def async_set_swing_mode(self, swing_mode):
        """Set new target temperature."""
        await self._set({ATTR_SWING_MODE: swing_mode})

    @property
    def swing_modes(self):
        """List of available swing modes."""
        return self._list.get(ATTR_SWING_MODE)

    @property
    def preset_mode(self):
        """Return the preset_mode."""
        return self.get(ATTR_PRESET_MODE)

    async def async_set_preset_mode(self, preset_mode):
        """Set preset mode."""
        if preset_mode == PRESET_AWAY:
            await self._api.device.set_holiday(ATTR_STATE_ON)
        else:
            await self._api.device.set_holiday(ATTR_STATE_OFF)

    @property
    def preset_modes(self):
        """List of available preset modes."""
        return list(HA_PRESET_TO_DAIKIN)

    async def async_update(self):
        """Retrieve latest state."""
        await self._api.async_update()

    async def async_turn_on(self):
        """Turn device on."""
        await self._api.device.set({})

    async def async_turn_off(self):
        """Turn device off."""
        await self._api.device.set({
            HA_ATTR_TO_DAIKIN[ATTR_HVAC_MODE]:
            HA_STATE_TO_DAIKIN[HVAC_MODE_OFF]
        })

    @property
    def device_info(self):
        """Return a device description for device registry."""
        return self._api.device_info

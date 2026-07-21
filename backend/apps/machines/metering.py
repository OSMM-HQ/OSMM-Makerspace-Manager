"""Canonical machine metering units and type-config validation."""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import models


class MeteringUnit(models.TextChoices):
    MINUTES = "minutes", "Minutes"
    WEIGHT = "weight", "Weight"
    VOLUME = "volume", "Volume"
    LENGTH = "length", "Length"
    COUNT = "count", "Count"


class ConsumablePoolUnit(models.TextChoices):
    GRAMS = "grams", "Grams"
    MILLILITERS = "milliliters", "Milliliters"
    MILLIMETERS = "millimeters", "Millimeters"
    COUNT = "count", "Count"


_POOL_UNITS = {
    MeteringUnit.WEIGHT: ConsumablePoolUnit.GRAMS,
    MeteringUnit.VOLUME: ConsumablePoolUnit.MILLILITERS,
    MeteringUnit.LENGTH: ConsumablePoolUnit.MILLIMETERS,
    MeteringUnit.COUNT: ConsumablePoolUnit.COUNT,
}
_METERING_UNITS = {value: key for key, value in _POOL_UNITS.items()}


def pool_unit_for_metering(unit):
    return _POOL_UNITS.get(unit)


def metering_unit_for_pool(unit):
    return _METERING_UNITS.get(unit)


def validate_type_config(config):
    """Validate optional generic metering keys without constraining old type packs."""
    if not isinstance(config, dict):
        raise ValidationError("Machine type capability_config must be an object.")
    if "metering_unit" in config and config["metering_unit"] not in MeteringUnit.values:
        raise ValidationError("metering_unit must be a supported metering unit.")
    for key in ("rate_per_unit", "flat_fee"):
        if key in config:
            _nonnegative_decimal(config[key], key)
    if "currency" in config:
        currency = config["currency"]
        if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha() or currency != currency.upper():
            raise ValidationError("currency must be a three-letter uppercase ISO code.")
    if "requires_booking" in config and type(config["requires_booking"]) is not bool:
        raise ValidationError("requires_booking must be true or false.")


def _nonnegative_decimal(value, key):
    if isinstance(value, bool):
        raise ValidationError(f"{key} must be numeric.")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(f"{key} must be numeric.") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValidationError(f"{key} must be non-negative.")
    return parsed

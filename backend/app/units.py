from math import isfinite
def normalize_value(value, unit):
    """Preserve original values. Phase 1 does not extract properties automatically."""
    if value is None:
        return {"original_value": None, "original_unit": unit, "normalized_value": None, "normalized_unit": None, "conversion_performed": None}
    if not isinstance(value, (float, int)) or isinstance(value, bool) or not isfinite(value):
        raise ValueError("Value must be a finite number or null")
    conversions = {
        "°C": ("K", 1.0, 273.15), "C": ("K", 1.0, 273.15),
        "K": ("K", 1.0, 0.0), "nm": ("m", 1e-9, 0.0),
        "µm": ("m", 1e-6, 0.0), "um": ("m", 1e-6, 0.0),
        "g/cm³": ("kg/m³", 1000.0, 0.0), "eV": ("eV", 1.0, 0.0),
    }
    if unit not in conversions:
        return {"original_value": value, "original_unit": unit, "normalized_value": None, "normalized_unit": None, "conversion_performed": None}
    target, scale, offset = conversions[unit]
    return {"original_value": value, "original_unit": unit, "normalized_value": value * scale + offset, "normalized_unit": target, "conversion_performed": f"value * {scale} + {offset}"}

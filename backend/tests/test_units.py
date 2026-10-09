import pytest
from app.units import normalize_value
def test_original_and_normalized_values_preserved():
    value = normalize_value(25,"°C")
    assert value["original_value"] == 25
    assert value["original_unit"] == "°C"
    assert value["normalized_value"] == pytest.approx(298.15)
    assert value["normalized_unit"] == "K"
    assert value["conversion_performed"]
def test_wavelength_and_density():
    assert normalize_value(1550,"nm")["normalized_value"] == pytest.approx(1.55e-6)
    assert normalize_value(5.5,"g/cm³")["normalized_value"] == 5500
def test_missing_and_unrecognized_values_not_invented():
    assert normalize_value(None,"K")["normalized_value"] is None
    assert normalize_value(3,"arbitrary")["normalized_unit"] is None
    with pytest.raises(ValueError):
        normalize_value(float("nan"),"K")

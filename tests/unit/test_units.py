from app.units import format_units


def test_units_are_pluralized_without_duplicating_the_suffix():
    assert format_units(112, "pieces") == "112 pieces"
    assert format_units(46, "litre") == "46 litres"
    assert format_units(10, "kg") == "10 kg"


def test_singular_units_keep_their_operator_wording():
    assert format_units(1, "pieces") == "1 piece"
    assert format_units(1, "litre") == "1 litre"

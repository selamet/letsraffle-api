"""
Tests for public name masking
"""

import pytest
from app.utils.names import public_display_name


@pytest.mark.utils
@pytest.mark.parametrize("first,last,expected", [
    ("Ayşe", "Demir", "Ayşe D."),
    (" Mert ", " kaya ", "Mert K."),
    ("Elif", "", "Elif"),
])
def test_public_display_name(first, last, expected):
    assert public_display_name(first, last) == expected

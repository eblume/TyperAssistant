"""Tests of the testing system. These are a sanity test for your testing workflow."""

import pytest


@pytest.mark.parametrize("x,y,z", [(1, 2, 3), (4, 5, 9)])
def test_can_add(x: int, y: int, z: int) -> None:
    """Can add two numbers."""
    assert x + y == z


@pytest.mark.openai
def test_openai_mark(pytestconfig):
    """If you run pytest without --openai, this test should be skipped."""
    assert pytestconfig.getoption("--openai")

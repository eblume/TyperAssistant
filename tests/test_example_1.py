"""Tests of examples/example_1.py."""

import pytest
from typer import Typer
from typer.testing import CliRunner

runner = CliRunner()
pytestmark = pytest.mark.parametrize("example_name", ["example_1"], indirect=True)


@pytest.mark.openai
def test_can_ask(example_app: Typer):
    result = runner.invoke(example_app, ["--help"])
    assert result.exit_code == 0
    assert "ask" in result.stdout


@pytest.mark.openai
def test_can_say_hello(example_app: Typer):
    result = runner.invoke(example_app, ["ask", "--no-prompt", "Please greet me by name"])
    assert result.exit_code == 0
    assert "get_current_user" in result.stdout
    assert "say_hello" in result.stdout
    assert "Hello, " in result.stdout

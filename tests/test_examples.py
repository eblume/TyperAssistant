"""Tests of examples/example_1.py."""
import importlib.util
import os

import pytest
from typer import Typer
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture(scope="session")
def example_app(example_name: str) -> Typer:
    """Load an example app from the examples directory."""
    example_path = os.path.join(os.path.dirname(__file__), "..", "examples", f"{example_name}.py")
    spec = importlib.util.spec_from_file_location(example_name, example_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load example {example_name}")
    example = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(example)
    return example.app


@pytest.fixture(scope="session", params=["example_1", "example_3"])
def example_name(request) -> str:
    """Override the params of this fixture to specify which example to load."""
    return request.param


@pytest.mark.openai
@pytest.mark.parametrize("example_name", ["example_1", "example_3"], indirect=True)
def test_can_ask(example_app: Typer):
    result = runner.invoke(example_app, ["--help"])
    assert result.exit_code == 0
    assert "ask" in result.stdout


@pytest.mark.openai
@pytest.mark.parametrize("example_name", ["example_1"], indirect=True)
def test_can_say_hello(example_app: Typer):
    result = runner.invoke(example_app, ["ask", "--no-prompt", "Please greet me by name"])
    assert result.exit_code == 0
    assert "get_current_user" in result.stdout
    assert "say_hello" in result.stdout
    assert "Hello, " in result.stdout


@pytest.mark.openai
@pytest.mark.parametrize("example_name", ["example_3"], indirect=True)
def test_can_off_a_cat(example_app: Typer):
    result = runner.invoke(example_app, ["ask", "--no-prompt", "Please send Macavity to the Heviside Layer"])
    assert result.exit_code == 0
    assert "Up up up past the Russell Hotel with Macavity!" in result.stdout


# TODO: test example_2.py
# (This API is likely to be refactored soon so I left it out for now.)

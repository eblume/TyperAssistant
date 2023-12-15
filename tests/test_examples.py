"""Tests of the examples/ directory.

These tests work by loading each example as a module. In the case of examples which create an 'app' object, the typer
CliRunner test runner is used to test command invocation. Other tests test the module explicitly (eg example_2.py).

None of these tests are considered to be comprehensive, but rather they seek to validate that the examples work as
written. Therefore, most of these tests require OpenAI integration via `pytest --openai`.

Note that the assistant fixtures loaded in these tests are "session" fixtures to avoid churn on the OpenAI API. This
will cause the tests to behave non-idempotently, especially when testing the 'replace' keyword, and therefore tests of
idempotent behavior should not be included here but rather in other non-example test cases where object lifecycle is
managed more granularly.
"""
import importlib.util
import os
from importlib.machinery import ModuleSpec
from types import ModuleType

import pytest
from typer import Typer
from typer.testing import CliRunner

runner = CliRunner()
pytest_mark = pytest.mark.openai


@pytest.fixture(scope="session", params=["example_1", "example_3"])
def example_name(request) -> str:
    """Override the params of this fixture to specify which example to load."""
    return request.param


@pytest.fixture(scope="session")
def example_spec(example_name: str) -> ModuleSpec:
    example_path = os.path.join(os.path.dirname(__file__), "..", "examples", f"{example_name}.py")
    spec = importlib.util.spec_from_file_location(example_name, example_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load example {example_name}")
    return spec


@pytest.fixture(scope="session")
def example_module(example_spec: ModuleSpec) -> ModuleType:
    example = importlib.util.module_from_spec(example_spec)
    return example


@pytest.fixture(scope="session")
def example_app(example_spec: ModuleSpec, example_module: ModuleType) -> Typer:
    """Load an example app from the examples directory."""
    assert example_spec.loader is not None
    example_spec.loader.exec_module(example_module)
    return example_module.app


####################


@pytest.mark.openai
@pytest.mark.parametrize(
    "example_name,ask_command_name",
    [
        ("example_1", "ask"),
        ("example_3", "deuteronomy"),
    ],
    indirect=["example_name"],
    scope="session",
)
def test_can_ask(example_app: Typer, ask_command_name: str):
    result = runner.invoke(example_app, ["--help"])
    assert result.exit_code == 0
    assert ask_command_name in result.stdout


@pytest.mark.openai
@pytest.mark.parametrize("example_name", ["example_1"], indirect=True)
def test_can_say_hello(example_app: Typer):
    result = runner.invoke(example_app, ["ask", "--no-confirm-commands", "Please greet me by name"])
    assert result.exit_code == 0
    assert "get_current_user" in result.stdout
    assert "say_hello" in result.stdout
    assert "Hello, " in result.stdout


@pytest.mark.openai
@pytest.mark.parametrize("example_name", ["example_2"], indirect=True)
def test_can_ask_superbot(example_spec: ModuleSpec, example_module: ModuleType, capsys, monkeypatch):
    assert example_spec.loader is not None
    monkeypatch.setattr("builtins.input", lambda _: "This sentence is false!")
    example_spec.loader.exec_module(example_module)
    # Capture stdout to check module load printing, as per example_2
    captured = capsys.readouterr()
    # Check that superbot actually said something. 10 chars is a pretty low bar.
    assert len(captured.out) > 10


@pytest.mark.openai
@pytest.mark.parametrize("example_name", ["example_3"], indirect=True)
def test_can_off_a_cat(example_app: Typer):
    # I just have to say that this is my favorite test, ever
    before = {cat.strip() for cat in runner.invoke(example_app, ["cats", "list"]).stdout.splitlines()}
    result = runner.invoke(
        example_app, ["deuteronomy", "Please pick a cat, send it to the Heaviside Layer, and then confirm it's gone"]
    )
    assert result.exit_code == 0
    after = {cat.strip() for cat in runner.invoke(example_app, ["cats", "list"]).stdout.splitlines()}
    assert len(before) - len(after) == 1
    winner = list(before - after)[0]
    assert f"Up up up past the Russell Hotel with {winner}!" in result.stdout

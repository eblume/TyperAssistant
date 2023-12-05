import importlib.util
import os
import sys

import pytest
from typer import Typer


def pytest_addoption(parser):
    parser.addoption(
        "--openai",
        action="store_true",
        default=False,
        help="run integration tests against env[OPENAI_API_KEY]. Costs money and mutates remote state.",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "openai: mark test as integration test (COSTS MONEY)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--openai"):
        return
    skip_openai = pytest.mark.skip(reason="need --openai option to run - COSTS MONEY")
    for item in items:
        if "openai" in item.keywords:
            item.add_marker(skip_openai)


@pytest.fixture(scope="session", autouse=True)
def mock_openai(session_mocker, pytestconfig):
    """MagicMock openai.OpenAI if --openai is not passed."""
    if pytestconfig.getoption("--openai"):
        if "OPENAI_API_KEY" not in os.environ:
            sys.stderr.write(
                "WARNING: --openai is set but OPENAI_API_KEY is not in the environment. "
                "Integration tests will fail.\n"
            )
        yield None
        return

    # Extra protection against accidentally running integration tests
    if "OPENAI_API_KEY" in os.environ:
        del os.environ["OPENAI_API_KEY"]
    mock = session_mocker.patch("openai.OpenAI", autospec=True)
    yield mock


@pytest.fixture
def example_app(example_name: str) -> Typer:
    """Load an example app from the examples directory."""
    example_path = os.path.join(os.path.dirname(__file__), "..", "examples", f"{example_name}.py")
    spec = importlib.util.spec_from_file_location(example_name, example_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load example {example_name}")
    example = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(example)
    return example.app


@pytest.fixture(params=["example_1", "example_3"])
def example_name(request) -> str:
    """Override the params of this fixture to specify which example to load."""
    return request.param

import os
import sys

import pytest


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
def unset_openai_env(pytestconfig):
    """Disarm openai.OpenAI if --openai is not passed.

    Works by unsetting OPENAI_API_KEY in the environment, as a safety measure against accidentally mutating remote state.
    """
    if pytestconfig.getoption("--openai"):
        if "OPENAI_API_KEY" not in os.environ:
            sys.stderr.write(
                "WARNING: --openai is set but OPENAI_API_KEY is not in the environment. "
                "Integration tests will fail.\n"
            )
        return

    # Extra protection against accidentally running integration tests
    if "OPENAI_API_KEY" in os.environ:
        del os.environ["OPENAI_API_KEY"]

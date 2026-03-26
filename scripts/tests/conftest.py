import importlib.util
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _import_script(name):
    mod_name = name.replace("-", "_").replace(".py", "")
    spec = importlib.util.spec_from_file_location(mod_name, SCRIPTS_DIR / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def extract_mod():
    return _import_script("extract-grpc-calls.py")


@pytest.fixture(scope="session")
def analyze_mod():
    return _import_script("analyze-queues.py")


@pytest.fixture(scope="session")
def sequence_mod():
    return _import_script("sequence-diagram.py")


@pytest.fixture(scope="session")
def sample_calls_dir():
    return str(FIXTURES_DIR / "sample-calls")


@pytest.fixture(scope="session")
def replay_calls_dir():
    return str(FIXTURES_DIR / "replay-calls")


@pytest.fixture(scope="session")
def eager_calls_dir():
    return str(FIXTURES_DIR / "eager-calls")

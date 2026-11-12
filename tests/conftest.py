import pytest

from driver.lock import gate


@pytest.fixture(autouse=True)
def fresh_run_gate():
    """A run that is left going in one test must not block the next test."""
    gate.reset()
    yield
    gate.reset()

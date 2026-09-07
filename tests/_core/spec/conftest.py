import pytest

from tests._core.spec.bdd import CacheScenario


@pytest.fixture
def cache() -> CacheScenario:
    """A shared cache with default options and empty storage."""
    return CacheScenario()

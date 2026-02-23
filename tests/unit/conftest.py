"""Unit test fixtures."""

import pytest


@pytest.fixture
def sample_text() -> str:
    """Sample text for testing."""
    return "Hello, this is a test."

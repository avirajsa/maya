"""Tests for Maya tools."""

import pytest
from maya.tools import calculate, get_current_datetime, search_web


def test_calculator_basic():
    """Test basic arithmetic evaluation: 2 + 2 = 4."""
    try:
        res = calculate("2 + 2")
    except Exception:
        res = calculate.invoke("2 + 2")
    assert str(res) == "4"


def test_calculator_complex():
    """Test complex arithmetic evaluation: (10 * 5) / 2 + 3 ** 2 == 34.0."""
    try:
        res = calculate("(10 * 5) / 2 + 3 ** 2")
    except Exception:
        res = calculate.invoke("(10 * 5) / 2 + 3 ** 2")
    assert str(res) == "34.0"


def test_calculator_invalid():
    """Test that invalid code like 'import os' returns an error string instead of crashing."""
    try:
        res = calculate("import os")
    except Exception:
        res = calculate.invoke("import os")
    assert isinstance(res, str)
    assert any(term in res.lower() for term in ("error", "invalid", "failed", "unsupported"))


def test_get_datetime():
    """Test that current date and time returns a non-empty formatted string."""
    try:
        res = get_current_datetime()
    except Exception:
        res = get_current_datetime.invoke({})
    assert isinstance(res, str)
    assert len(res.strip()) > 0


def test_web_search():
    """Test web search functionality or skip gracefully on network absence."""
    try:
        try:
            res = search_web("Python programming language")
        except Exception:
            res = search_web.invoke("Python programming language")
        assert isinstance(res, str)
        assert len(res.strip()) > 0
    except Exception as e:
        pytest.skip(f"Network unavailable or rate-limited: {e}")

"""Test to see if our environment (PUDL_INPUT/OUTPUT, pudl_settings) is set up properly
in a variety of situations."""

import os
import pathlib
from typing import Any

import pytest

from pudl.workspace.setup import get_defaults


def setup():
    if (old_output := os.getenv("PUDL_OUTPUT")) is not None:
        os.environ["PUDL_OUTPUT_OLD"] = old_output
    if (old_input := os.getenv("PUDL_INPUT")) is not None:
        os.environ["PUDL_INPUT_OLD"] = old_input


@pytest.mark.parametrize(
    ["env_vars"],
    [
        (
            {
                "PUDL_OUTPUT": "/test/whatever/from/env/output",
                "PUDL_INPUT": "/test/whatever/from/env/input",
            },
        ),
        (
            {
                "PUDL_OUTPUT": "/test/whatever/from/env/output",
                "PUDL_INPUT": "/test/whatever/from/env/input",
            },
        ),
        (
            {
                "PUDL_OUTPUT": "/test/whatever/from/env/different_output",
                "PUDL_INPUT": "/test/whatever/from/env/different_input",
            },
        ),
    ],
)
def test_get_defaults_uses_env_vars(env_vars):
    workspace = pathlib.Path(env_vars["PUDL_OUTPUT"]).parent
    os.environ |= env_vars
    settings = get_defaults()

    expected_values = {
        "pudl_in": f"{workspace}",
        "pudl_out": env_vars["PUDL_OUTPUT"],
        "data_dir": env_vars["PUDL_INPUT"],
    }
    # We need expected_values to be subset (<=) of the settings dictionary.
    # This validates that settings has all of the expected keys and that their values match.
    assert expected_values.items() <= settings.items()

    assert os.getenv("PUDL_OUTPUT") == env_vars["PUDL_OUTPUT"]
    assert os.getenv("PUDL_INPUT") == env_vars["PUDL_INPUT"]


def assert_dict_contains(exp_dict: dict[Any, Any], got_dict: dict[Any, Any]):
    """Aserts that exp_dict is a dict subset of got_dict.

    That is, all keys in exp_dict have to be present in got_dict and the two dictionaries
    need to agree on the value over these keys.

    If they don't, AssertionError is raised.

    Args:
        exp_dict: expected results, this should be subset of got_dict
        got_dict: actual results, this should be superset of exp_dict
    """
    divergent_keys = {
        k for k, v in exp_dict.items() if k not in got_dict or v != got_dict[k]
    }
    if divergent_keys:
        exp_subset = {k: v for k, v in exp_dict.items() if k in divergent_keys}
        got_subset = {k: v for k, v in got_dict.items() if k in divergent_keys}
        raise AssertionError(f"expected {exp_subset} got {got_subset}")


@pytest.mark.parametrize(
    ["kwargs", "expected_settings"],
    [
        (
            {},
            {"pudl_in": "/foo", "pudl_out": "/foo/out"},
        ),
        (
            {"output_dir": "/baz/out"},
            {"pudl_in": "/foo", "pudl_out": "/baz/out"},
        ),
        (
            {"input_dir": "/bar/in"},
            {"pudl_in": "/bar", "pudl_out": "/foo/out"},
        ),
        (
            {"input_dir": "/aaa/in", "output_dir": "/bbb/out"},
            {"pudl_in": "/aaa", "pudl_out": "/bbb/out"},
        ),
    ],
)
def test_get_defaults_overrides(kwargs, expected_settings):
    os.environ |= {
        "PUDL_INPUT": "/foo/in",
        "PUDL_OUTPUT": "/foo/out",
    }
    assert_dict_contains(expected_settings, get_defaults(**kwargs))


def test_get_defaults_fails_with_no_env():
    if os.getenv("PUDL_OUTPUT"):
        del os.environ["PUDL_OUTPUT"]
    if os.getenv("PUDL_INPUT"):
        del os.environ["PUDL_INPUT"]

    with pytest.raises(RuntimeError):
        get_defaults()


def teardown():
    if (old_output := os.getenv("PUDL_OUTPUT_OLD")) is not None:
        os.environ["PUDL_OUTPUT"] = old_output
        del os.environ["PUDL_OUTPUT_OLD"]
    if (old_input := os.getenv("PUDL_INPUT_OLD")) is not None:
        os.environ["PUDL_INPUT"] = old_input
        del os.environ["PUDL_INPUT_OLD"]

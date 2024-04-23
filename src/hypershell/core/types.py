# SPDX-FileCopyrightText: 2023 Geoffrey Lentner
# SPDX-License-Identifier: Apache-2.0

"""Automatic type coercion of input data."""


# type annotations
from typing import TypeVar

# public interface
__all__ = ['smart_coerce', 'JSONValue']


# Each possible input type
JSONValue = TypeVar('JSONValue', bool, int, float, str, type(None))


def smart_coerce(value: str) -> JSONValue:
    """Automatically coerce string to typed value."""
    if value.lower() in ('null', 'none', ):
        return None
    if value.lower() in ('true', ):
        return True
    if value.lower() in ('false', ):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value

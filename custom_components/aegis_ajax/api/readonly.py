"""Read-only build: nothing that changes the alarm, the devices or the hub is ever sent to Ajax.

This fork of Aegis for Ajax only reads (sensors, battery, signal, events). Every API method that would send
a command is wrapped with ``@read_only`` and raises ``ReadOnlyError`` instead, so no other part of the
integration (or a future change) can arm, disarm, bypass, switch or reconfigure anything by accident.
"""

from __future__ import annotations

import functools
from typing import Any, Awaitable, Callable, TypeVar

_F = TypeVar("_F", bound=Callable[..., Awaitable[Any]])


class ReadOnlyError(Exception):
    """Raised when a command is attempted in this read-only build."""


def read_only(func: _F) -> _F:
    """Replace an async API method with one that always refuses."""

    @functools.wraps(func)
    async def _blocked(*args: Any, **kwargs: Any) -> Any:
        raise ReadOnlyError(
            f"{func.__qualname__} is disabled: this is a read-only build of Aegis (sensors only)"
        )

    return _blocked  # type: ignore[return-value]

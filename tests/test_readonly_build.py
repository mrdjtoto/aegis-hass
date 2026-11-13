"""Guards of the read-only build: no command can reach Ajax. Needs no Home Assistant (reads the source)."""

from __future__ import annotations

import ast
import asyncio
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent / "custom_components" / "aegis_ajax"

# Every API method that sends something to Ajax that is not a login/session/read call.
BLOCKED = {
    "api/security.py": {"arm", "disarm", "arm_night_mode", "disarm_from_night_mode", "arm_group", "disarm_group"},
    "api/spaces.py": {"press_panic_button"},
    "api/devices.py": {
        "send_command", "_update_siren_settings", "_update_night_mode_arm", "_device_bypass", "_device_on",
        "_device_off", "_device_brightness", "switch_smart_lock", "set_photo_on_demand_mode", "start_sound_test",
        "set_chimes_mode",
    },
    "api/hts/client.py": {"restore_after_alarm", "write_device_parameter", "_send_hub_command"},
}


def _load_readonly():
    spec = importlib.util.spec_from_file_location("aegis_readonly", ROOT / "api" / "readonly.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("path", sorted(BLOCKED))
def test_command_methods_are_decorated(path: str) -> None:
    tree = ast.parse((ROOT / path).read_text())
    decorated = {
        n.name
        for c in ast.walk(tree) if isinstance(c, ast.ClassDef)
        for n in c.body
        if isinstance(n, ast.AsyncFunctionDef)
        and any(isinstance(d, ast.Name) and d.id == "read_only" for d in n.decorator_list)
    }
    assert BLOCKED[path] <= decorated, f"missing @read_only in {path}: {BLOCKED[path] - decorated}"


def test_decorator_always_refuses() -> None:
    mod = _load_readonly()

    @mod.read_only
    async def arm(space_id: str) -> str:
        return "armed"

    with pytest.raises(mod.ReadOnlyError):
        asyncio.run(arm("x"))


def test_only_reading_platforms_are_loaded() -> None:
    tree = ast.parse((ROOT / "__init__.py").read_text())
    platforms: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "PLATFORMS" for t in node.targets):
            platforms = [e.attr for e in node.value.elts]
    assert set(platforms) == {"BINARY_SENSOR", "EVENT", "SENSOR", "UPDATE"}


def test_no_arming_service_is_registered() -> None:
    tree = ast.parse((ROOT / "__init__.py").read_text())
    names: tuple[str, ...] = ()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "_CUSTOM_SERVICE_NAMES" for t in node.targets):
            names = tuple(e.value for e in node.value.elts)
    assert names and not {"force_arm", "force_arm_night", "disarm_night_mode", "press_panic_button"} & set(names)

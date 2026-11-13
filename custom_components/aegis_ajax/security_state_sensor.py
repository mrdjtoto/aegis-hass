"""Read-only arming state of the space and of each group (READ-ONLY BUILD).

The upstream integration shows the arming state through alarm panels, which also arm and disarm.
The read-only build drops the panels, so the same state is exposed here as plain enum sensors:
no service, no command, nothing a caller can use to change the alarm.

States follow Home Assistant's alarm-panel vocabulary, so automations read the same words:
disarmed, armed_away, armed_night, partially_armed, arming, pending, triggered.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.aegis_ajax.const import DOMAIN, MANUFACTURER, SecurityState
from custom_components.aegis_ajax.delay_states import DelayKind
from custom_components.aegis_ajax.entity import build_device_info

if TYPE_CHECKING:
    from custom_components.aegis_ajax.api.models import Group, Space
    from custom_components.aegis_ajax.coordinator import AjaxCobrandedCoordinator

DISARMED = "disarmed"
ARMED_AWAY = "armed_away"
ARMED_NIGHT = "armed_night"
PARTIALLY_ARMED = "partially_armed"
ARMING = "arming"
PENDING = "pending"
TRIGGERED = "triggered"

OPTIONS = [DISARMED, ARMED_AWAY, ARMED_NIGHT, PARTIALLY_ARMED, ARMING, PENDING, TRIGGERED]

_STATE_MAP = {
    SecurityState.NONE: DISARMED,
    SecurityState.DISARMED: DISARMED,
    SecurityState.ARMED: ARMED_AWAY,
    SecurityState.NIGHT_MODE: ARMED_NIGHT,
    SecurityState.PARTIALLY_ARMED: PARTIALLY_ARMED,
    SecurityState.AWAITING_EXIT_TIMER: ARMING,
    SecurityState.AWAITING_SECOND_STAGE: ARMING,
    SecurityState.TWO_STAGE_INCOMPLETE: ARMING,
    SecurityState.AWAITING_VDS: ARMING,
}

_OFF = (SecurityState.DISARMED, SecurityState.NONE)


def state_name(state: SecurityState) -> str:
    """Map an Ajax security state to the sensor value."""
    return _STATE_MAP.get(state, DISARMED)


def space_state(
    security_state: SecurityState,
    *,
    night_mode_enabled: bool,
    alarmed: bool,
    delay: DelayKind | None,
) -> str:
    """The space value, with the same overlays the upstream panel applies (#426, #454, #284)."""
    if security_state not in _OFF:
        if alarmed:
            return TRIGGERED
        if delay is not None:
            return PENDING if delay is DelayKind.PENDING else ARMING
    # In group mode Ajax reports PARTIALLY_ARMED while night mode is on; the flag tells them apart.
    if security_state == SecurityState.PARTIALLY_ARMED and night_mode_enabled:
        return ARMED_NIGHT
    return state_name(security_state)


def build_security_state_sensors(coordinator: AjaxCobrandedCoordinator) -> list[SensorEntity]:
    """One sensor per space, plus one per group when the space uses groups."""
    entities: list[SensorEntity] = []
    for space_id, space in coordinator.spaces.items():
        entities.append(AjaxSpaceSecurityStateSensor(coordinator, space_id))
        if space.group_mode_enabled and space.groups:
            entities.extend(
                AjaxGroupSecurityStateSensor(coordinator, space_id, group.id) for group in space.groups
            )
    return entities


class _SecurityStateBase(CoordinatorEntity["AjaxCobrandedCoordinator"], SensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = OPTIONS
    _attr_icon = "mdi:shield-home"

    def __init__(self, coordinator: AjaxCobrandedCoordinator, space_id: str) -> None:
        super().__init__(coordinator)
        self._space_id = space_id
        space = coordinator.spaces.get(space_id)
        hub_id = space.hub_id if space else space_id
        hub_device = coordinator.devices.get(hub_id)
        if hub_device:
            self._attr_device_info = build_device_info(hub_device, coordinator.rooms)
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, hub_id)},
                name=space.name if space else "Ajax Hub",
                manufacturer=MANUFACTURER,
                model="Hub",
            )

    @property
    def _space(self) -> Space | None:
        return self.coordinator.spaces.get(self._space_id)


class AjaxSpaceSecurityStateSensor(_SecurityStateBase):
    """Arming state of the whole space (what the upstream space panel shows)."""

    _attr_name = "Arming state"

    def __init__(self, coordinator: AjaxCobrandedCoordinator, space_id: str) -> None:
        super().__init__(coordinator, space_id)
        self._attr_unique_id = f"aegis_ajax_security_state_{space_id}"

    @property
    def available(self) -> bool:
        space = self._space
        return super().available and space is not None and (space.is_online or not space.hub_id)

    @property
    def native_value(self) -> str | None:
        space = self._space
        if space is None:
            return None
        overlay = self.coordinator.delay_overlays.get(space.id)
        return space_state(
            space.security_state,
            night_mode_enabled=space.night_mode_enabled,
            alarmed=space.id in self.coordinator.alarmed_space_ids,
            delay=overlay.kind if overlay is not None else None,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        space = self._space
        if space is None:
            return {}
        return {
            "night_mode": space.night_mode_enabled,
            "group_mode": space.group_mode_enabled,
            "armed_groups": [g.name for g in space.groups if g.is_armed],
            "connection_status": space.connection_status.name,
        }


class AjaxGroupSecurityStateSensor(_SecurityStateBase):
    """Arming state of one Ajax group (zone)."""

    def __init__(self, coordinator: AjaxCobrandedCoordinator, space_id: str, group_id: str) -> None:
        super().__init__(coordinator, space_id)
        self._group_id = group_id
        self._attr_unique_id = f"aegis_ajax_security_state_{space_id}_group_{group_id}"
        group = self._group
        self._attr_name = f"Arming state {group.name if group else group_id}"

    @property
    def _group(self) -> Group | None:
        space = self._space
        return space.get_group(self._group_id) if space else None

    @property
    def available(self) -> bool:
        space = self._space
        return super().available and space is not None and space.is_online and self._group is not None

    @property
    def native_value(self) -> str | None:
        group = self._group
        return state_name(group.security_state) if group is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        group = self._group
        if group is None:
            return {}
        devices = sorted(d.name for d in self.coordinator.devices.values() if d.group_id == group.id)
        return {"group_id": group.id, "group_name": group.name, "devices": devices}

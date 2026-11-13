# Aegis for Ajax — read-only build

This branch is a fork of [bvis/aegis-hass](https://github.com/bvis/aegis-hass) that **only reads** from Ajax.
Home Assistant can show sensors, batteries, signal, temperature and events, but it can **never arm, disarm, bypass,
press the panic button, switch a relay or change a setting**.

## What changed (on top of upstream 1.30.1)
- `PLATFORMS` is only `binary_sensor`, `event`, `sensor` and `update`: no alarm panel, button, switch, light, lock,
  valve, number, select or camera.
- The arming state is exposed by read-only `enum` sensors (`security_state_sensor.py`): one for the space and one
  per group in Group (Zone) mode. They only read the coordinator and register no service.
- Only the account/session services are registered (`list_client_sessions`, `terminate_client_session`,
  `terminate_other_client_sessions`). `force_arm`, `force_arm_night`, `disarm_night_mode`, `press_panic_button`,
  `set_photo_on_demand_mode` and `refresh_alarm_images` are gone.
- Every API method that sends a command is wrapped with `@read_only` (`api/readonly.py`) and raises `ReadOnlyError`:
  `SecurityApi.arm/disarm/arm_night_mode/disarm_from_night_mode/arm_group/disarm_group`, `press_panic_button`,
  `DevicesApi.send_command` and its helpers (`_device_on/_off/_brightness/_bypass`, `_update_siren_settings`,
  `_update_night_mode_arm`, `switch_smart_lock`, `set_photo_on_demand_mode`, `start_sound_test`, `set_chimes_mode`),
  and the hub commands `HtsClient.restore_after_alarm`, `write_device_parameter`, `_send_hub_command`.

## What it does NOT protect
The Ajax login (password hash and session token) is still stored in Home Assistant's `core.config_entries`.
Anyone who can read that file can talk to Ajax directly. Use a dedicated Ajax account and watch arm/disarm events
(the arming-state sensors, or the SIA integration if you want them without the cloud).

## Keeping it up to date
```bash
git fetch upstream && git rebase upstream/main   # on branch readonly-sensors
```
Review any new command method upstream adds and wrap it with `@read_only`.

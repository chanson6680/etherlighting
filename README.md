# Etherlighting for Home Assistant

An experimental Home Assistant app for assigning switch port colors by device MAC address. Built for the **USW Pro Max 48 PoE on US2.7.5.15**.

The app supports device search, a 52-port map, saved color/brightness rules, editable color presets, rule import/export, and shared-port conflict detection. Rules persist by MAC address. Add, rename, recolor, or delete presets in **Color presets**. Presets survive restarts and act as shortcuts; existing device rules keep their saved colors. Software tests cover moving a MAC, stale entries, conflicts, restoration failures, request protection, and preset persistence.

**Status:** installed and running in Home Assistant, with verified live discovery, saved color rules, and a successful physical magenta test on port 32. The user confirmed magenta appeared and the original lighting returned after ten seconds. Individual red, green, blue, and white channels are used because the combined color-code interface changed brightness but displayed white. LED control defaults to off for new installations. This is an app with its own sidebar interface, not native Home Assistant light entities.

## Install

In Home Assistant, open **Settings → Apps → Install app**, open **Repositories** from the menu, and add `https://github.com/chanson6680/etherlighting`. Refresh the app store, open **Etherlighting**, and install it. Configure your switch connection before starting the app.

For local development, copy the inner `etherlighting` folder to `/addons/etherlighting` on HAOS using an existing SSH or Samba app, then reload the app store and install it under Local apps.

The package does not require Supervisor API access, host networking, privileged mode, or ports exposed outside Home Assistant. It supports amd64 and aarch64. Its web interface accepts connections from the Home Assistant ingress proxy only. Switch credentials, host keys, device rules, and lighting preferences are configured locally in Home Assistant and are not included in this repository.

See [the app instructions](etherlighting/DOCS.md) for configuration and the first controlled test. Home Assistant describes local installation in its [app development documentation](https://developers.home-assistant.io/docs/apps/testing/).

## Validation

Run `python -m unittest discover -s tests -v`. Twenty-seven tests passed on the development machine, covering fallback precedence, scheduling, skipped unchanged writes, forced manual refresh, and settings persistence as well as rules and presets. Browser checks verified saved lighting settings survive reload. Earlier preset browser checks covered add, rename, recolor, reload, selection in the device editor, and deletion without changing the saved device color. A live read parsed 80 MAC/VLAN rows, 79 unique MACs, and all 52 ports. Twenty ports had active links at the time of that read.

The browser check searched for Home Assistant, saved a temporary teal rule for its MAC on port 32, reloaded to verify persistence, and removed the test rule. No switch writes were made during these checks.

The `work` directory and downloaded vendor binaries are deliberately excluded from this package. No SSH password is included.

## Limitations

- A switch MAC table includes devices behind access points and other switches; one row is not proof of a direct cable. Shared ports require explicit permission, conflicting colors are blocked, and the detected uplink is excluded.
- MAC age can make a quiet device temporarily ineligible. Entries older than 300 seconds, disconnected ports, and Wi-Fi leave records are not colored.
- Device polling defaults to 30 seconds and writes only changed colors. Full color refresh defaults to 300 seconds; both intervals are adjustable in Lighting settings, and Refresh now forces a fresh read and color reapplication. Set full refresh to 0 for changes and manual refresh only. Stock firmware or a controller update may overwrite a color between refreshes.
- Optional unidentified-device color covers active ports with recent devices and no saved rules. It includes shared ports but excludes uplinks and ports reserved by paused or blocked rules. The fallback starts off on new installations; choose its color and brightness in Lighting settings.
- Stopping control requests the switch's current stock Etherlighting mode for all ports. This can replace overrides from other lighting tools. Do not run two LED controllers together.
- After a crash or network loss, immediate restoration cannot be guaranteed. A persistent recovery marker keeps the pending restoration visible. Starting the app never silently resumes color control.
- RGB channel output uses the documented 16-bit intensity range. Brightness scales these intensities, but perceived brightness and color accuracy depend on the LEDs and cable material. Check new colors with the ten-second test.

See [the compatibility notes](COMPATIBILITY.md) for evidence and remaining checks.

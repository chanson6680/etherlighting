# 0.4.0

- Detect Pro Max 16/24/48 PoE and non-PoE switches with model-specific port maps and discovery/LED bounds.
- Add opt-in experimental profiles and firmware support with RGBW checks; only Pro Max 48 PoE on US2.7.5.15 remains hardware tested.
- Block unknown families, incompatible interfaces, unsupported restoration modes, and mid-session identity changes.
- Add installation, troubleshooting, compatibility evidence, screenshots with fictional devices, and a local demo.

# 0.3.1

- Prepare the public GitHub repository with installation instructions.
- Start new installations with empty connection fields; existing saved connections are preserved.

# 0.3.0

- Add an optional unidentified-device color and brightness, with saved rules taking priority.
- Add separate persistent polling and color reapplication intervals, plus Refresh now.
- Skip unchanged color writes during ordinary polls to reduce repeated flashing.
- Preserve uplink, paused-rule, shared-rule, and conflicting-rule protections.

# 0.2.0

- Add, rename, recolor, and delete color presets in the app.
- Save presets across restarts and offer them in each device's color editor.
- Preserve existing device colors when presets change; all default presets can be removed.

# 0.1.5

- Physical test verified: port 32 displayed magenta and restored its original lighting after ten seconds.
- Update setup and compatibility documentation to reflect the verified RGBW driver.
- Eighteen software tests pass; continuous control remains paused until started from the app.

# 0.1.4

- Replace the inaccurate combined color command with validated, separate RGBW channel writes.
- Clear the white channel before applying RGB; scale each channel by the chosen brightness.
- Keep the existing UniFi lighting mode and restore its colors after each test.

# 0.1.3

- Use the stock firmware's echo write form for the LED proc interface.

# 0.1.2

- Capture switch command errors returned on either output stream.

# 0.1.1

- Read-only LED interface check and operation-specific switch errors.
- HAOS build, installation, and live discovery verified. First magenta test produced no visible change; diagnosis is in progress.

# 0.1.0

- Live SSH MAC and port discovery with pinned host-key verification.
- Device search, 52-port preview, per-MAC color/brightness rules, and import/export.
- Shared-port permission, conflicting-rule checks, stale-device exclusion, and uplink protection.
- Experimental per-port RGB driver, ten-second test, stock-mode restoration, and recovery marker.
- LED writes disabled by default; hardware and HAOS container validation pending.

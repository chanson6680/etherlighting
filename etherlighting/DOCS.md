# Configure Etherlighting

1. Install the app, open **Configuration**, and enter your switch address, device SSH username, password, and independently verified SSH public host key (key type followed by its base64 key). Connection fields start empty. Home Assistant stores the password in this app's configuration; it is not sent to the browser UI or logs.
2. Leave **Allow LED control** off. Start the app and open its web interface. Enable **Show in sidebar** if desired.
3. Search for a device by name, MAC address, IP, or port. Choose a color and brightness, then save. Presets include cameras in orange and Apple TVs in blue. Presets do not guess device types.
4. Review the proposed colors on the port map. A shared port represents every device behind that cable. Only permit a shared-port rule if coloring that entire port is intentional.

## Color presets

Use **Add preset** in the **Color presets** section to save a name and color. **Edit preset** lets you rename it, change its color, or delete it. Presets are stored in Home Assistant and survive app restarts; the four starter presets can also be edited or removed.

Choose a preset in a device's color editor and save the device to apply that color. Presets are shortcuts, so editing or deleting one leaves previously saved device colors unchanged. The device's brightness stays as selected. Rules import/export contains device rules; preset choices are stored separately in the app's data and included in Home Assistant app backups.

## Unidentified devices and refresh

Open **Lighting settings** to enable a fallback color and brightness for devices without any saved rule. This includes named devices. The default selection is white at 20% brightness; fallback is initially off until you save it enabled. It colors active ports with recently learned devices, including shared ports. Saved rules take priority. Uplinks and all locations reserved by paused, ambiguous, or blocked rules are excluded, so fallback does not bypass their protections. A port without a recently learned MAC keeps stock lighting.

**Poll switch every** accepts 15–3,600 seconds (default 30). Polling discovers devices and writes only changed port colors. **Reapply colors every** accepts 15–3,600 seconds (default 300), or **0** to disable repeated writes of unchanged colors. Each reapplication reads current device locations first. Shorter color refresh intervals replace UniFi overrides sooner; longer intervals reduce repeated flashes. A forced refresh still writes the separate LED channels and can briefly flash. Removing a previously colored port from the plan restores the stock mode globally before reapplying the remaining plan, which can also flash.

**Refresh now** immediately reads the switch and reapplies all planned colors while control is running. When stopped, it reads devices only. Saving lighting settings applies changed colors immediately while running. Settings persist across restarts and are included in app backups; rules export does not include settings or presets. The configuration-page refresh option only supplies the initial poll interval until settings are saved here.

## Test a physical port

Verified on the inspected switch: port 32 turned magenta at 30% intensity and returned to its original lighting after ten seconds. Other colors and ports can be checked the same way.

Only enable **Allow LED control** when ready to verify the behavior at the switch. **Check LED interface** checks compatibility without changing lights.

Save one rule on a non-uplink port carrying a single known device. Enable the setting, restart the app, and press **Test 10 seconds** for that rule. The app writes that port's RGB code, waits ten seconds, then requests the switch's current stock lighting mode. Observe both the requested color and its restoration. If either fails, leave continuous control off and report the result.

After a successful physical test, **Start following colors** applies eligible rules and refreshes them as MAC locations change. **Stop & restore** pauses the rules and requests the stock lighting mode. Neither operation changes VLANs, PoE, port link settings, or switch firmware.

## Connection and recovery

- SSH host keys are checked strictly. A mismatch stops the connection; do not replace the pinned public key until the switch's identity has been verified independently.
- A firmware change blocks writes until compatibility is reviewed. Discovery remains available if its table format is unchanged.
- If the app reports restoration pending, reconnect and press **Stop & restore** before starting another test. Uninstalling the app while the switch is unreachable cannot restore physical LEDs.
- Rules are stored in the app's persistent data. **Export** saves them to a JSON file; **Import** merges by MAC address, replacing matching MAC rules.
- The local desktop preview uses the temporary read-only SSH helper and cannot enable LED writes. Its saved rules can be exported and imported into the HAOS installation.

## Option reference

| Option | Meaning |
|---|---|
| Switch host | The switch's IPv4 address or hostname |
| SSH username | Existing device SSH user, not the UniFi cloud account |
| SSH password | Existing device SSH password, stored in Home Assistant app configuration |
| SSH host key | Public key type and base64 key from a verified switch connection |
| Initial polling interval | Initial discovery interval, 15–300 seconds; default 30. Saved in-app Lighting settings take priority. |
| Allow LED control | Enables the experimental test/start/restore controls; default off |

# Compatibility investigation — 26 September 2026

Read-only SSH inspection confirmed:

- Board: USW-Pro-Max-48-PoE / USPM48P, system ID 0xed5d.
- Firmware: US2.7.5.15; kernel 4.4.153; big-endian MIPS.
- The expected `etherlight.mcu` ubus service is absent. The existing Pro XG 8 lighting daemon cannot be used unchanged.
- Lighting interface: `/proc/led`, lighting-controller version 1.19.4.
- The switch itself documents `/proc/led/led_code` as accepting port 1–52, three hexadecimal RGB bytes, and brightness 1–100. Its example is `1 ff cc ff 100`.
- The live MAC table is returned by `swctrl mac show`; the port table by `swctrl port show`. A `U` prefix marks the switch uplink, observed at port 51.

## Static code validation

Copies of firmware files were read to the workstation and inspected without executing them or changing the switch. Downloaded vendor binaries are not redistributed in this package.

`/bin/ubntbox`, SHA-256 `ce2e057eb7876b827b56c054db827c0caf56674825a4b4fc96893006d2becae4`, generates a stock lighting configuration sequence. At virtual address 0x440b26 it emits `echo 10 %d > /proc/led/led_config` using the configured Etherlighting mode after palette updates.

`/lib/modules/4.4.153/custom.ko`, SHA-256 `a9790d5b04ddbe4123c9ebe062b1dc93f082f61ccc81ef12f3c0abb8a28ddfc1`, registers the LED proc files. Its `led_code` write handler at .text+0x1ed80 parses `%d %x %x %x %d`, validates port and color ranges, converts the one-based port, and calls the LED update path. Its config handler at .text+0x203a0 recognizes command 10 as a mode selection and refresh operation, separate from the cold/warm reset branches. The application restricts restoration to stock modes 0, 1, and 2.

The color handler contains calibration lookup and fallback logic. Exact colors, brightness, retention duration, and successful restoration remain physical-test requirements. A successful SSH exit code alone does not prove the LEDs changed correctly.

## Scope of validation

Verified: read-only SSH, host identity, discovery parsers against the actual switch output, local rule storage, browser search/edit/reload, command validation, controller behavior with a simulated switch, and the HAOS container build, installation, start, and ingress sidebar interface.

The first physical test requested port 32 magenta (#ff00ff) at 30% brightness. The printf-based write and restoration attempt returned exit 1 without an error message. Read-only identity, LED help, and shell-output checks passed. Version 0.1.3 switched to the stock firmware's echo write form, which completed both color and restoration commands. The user confirmed brightness changes but reported white rather than magenta, even with breathing disabled.

Version 0.1.4 uses the documented `/proc/led/led_color` channel interface: port, channel (r/g/b/w), and value 0–65535. The inspected handler at .text+0x1df40 writes the chosen channel directly and commits it; it does not use the `led_code` calibration lookup. The app clears white and scales RGB by brightness. No global `led_mode` changes are used. [Etherlighter's own implementation](https://github.com/robherley/etherlighter/blob/main/internal/device/client.go) also documents incorrect combined-command colors and uses individual channels. No third-party code is executed on the switch.

Physical verification completed: on 26 September 2026 the user observed port 32 turn magenta (#ff00ff, 30% intensity) and return to its original lighting after the ten-second direct-RGBW test. The app reported success and cleared its restoration marker. Breathing was disabled by the user during troubleshooting; the app did not modify that setting.

Pending: sustained MAC-following on hardware and color accuracy across other ports/shades. MAC moves, shared ports, and restoration failures are covered by software tests. No VLAN, PoE, firmware, or switch service changes were made.

References: [Home Assistant app configuration](https://developers.home-assistant.io/docs/apps/configuration/), [local installation](https://developers.home-assistant.io/docs/apps/testing/), and [upstream Pro XG lighting research](https://github.com/Ozark-Connect/unifi-lightshow).

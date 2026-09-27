"""Known Pro Max layouts; interface compatibility is checked separately."""
import re

PROFILES = {
    f"USW-Pro-Max-{copper}{suffix}": dict(copper_ports=copper, port_count=copper+sfp,
                                         sfp_ports=sfp, rows=2 if copper == 48 else 1)
    for copper, sfp in ((16, 2), (24, 2), (48, 4)) for suffix in ("", "-PoE")
}
VERIFIED = ("USW-Pro-Max-48-PoE", "US2.7.5.15")


def identify(text):
    names = re.findall(r"^board\.name=(.+)$", text, re.MULTILINE)
    versions = [line.strip() for line in text.splitlines() if re.fullmatch(r"US[0-9][A-Za-z0-9._+-]*", line.strip())]
    if len(names) != 1 or len(versions) != 1:
        raise ValueError("Cannot identify the switch model and firmware safely.")
    model, firmware = names[0].strip(), versions[0]
    if model not in PROFILES:
        raise ValueError(f"{model} is not supported by the Pro Max RGBW driver. Pro XG and other families need a separate driver.")
    verified = (model, firmware) == VERIFIED
    return dict(PROFILES[model], model=model, firmware=firmware, verified=verified,
                compatibility="Hardware tested" if verified else "Experimental — physical test required")


def validate_interface(device, led_help, raw_help, mode, experimental=False):
    if not device["verified"] and experimental is not True:
        raise ValueError("This model/firmware is experimental. Review compatibility, then enable Allow experimental models in app configuration before a ten-second test.")
    for text in (led_help, raw_help):
        span = re.search(r"port\[1-(\d+)\]", text)
        if not span or not device["port_count"] <= int(span[1]) <= 52:
            raise ValueError("The switch LED port range does not match a supported interface.")
    if "1 ff cc ff 100" not in led_help or "r=Red g=Green b=Blue w=White" not in raw_help or "1 r 65535" not in raw_help or "0-65535" not in raw_help:
        raise ValueError("The switch RGBW channel interface differs from the supported driver.")
    if str(mode).strip() not in ("0", "1", "2"):
        raise ValueError("The current lighting mode cannot be restored by this driver; use speed, network, or PoE mode first.")

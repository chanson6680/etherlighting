"""Persistent, validated lighting preferences, independent of SSH options."""
import json
from core import COLOR


def validate_settings(value):
    if not isinstance(value, dict):
        raise ValueError("Expected lighting settings.")
    result = {}
    for key, low, high in (("poll_seconds", 15, 3600), ("push_seconds", 0, 3600),
                           ("fallback_brightness", 1, 100)):
        number = value.get(key)
        if type(number) is not int or not low <= number <= high or (key == "push_seconds" and 0 < number < 15):
            raise ValueError(f"{key.replace('_', ' ').capitalize()} must be {low}–{high}" + (" (or at least 15 when enabled)." if key == "push_seconds" else "."))
        result[key] = number
    if type(value.get("fallback_enabled")) is not bool:
        raise ValueError("Choose whether to enable the unidentified-device color.")
    color = value.get("fallback_color")
    if not isinstance(color, str) or not COLOR.fullmatch(color):
        raise ValueError("Choose a valid unidentified-device color.")
    result.update(fallback_enabled=value["fallback_enabled"], fallback_color=color.upper())
    return result


def load_settings(path, options):
    if path.exists():
        return validate_settings(json.loads(path.read_text(encoding="utf-8")))
    return validate_settings(dict(poll_seconds=max(15, min(300, int(options.get("refresh_seconds", 30)))),
                                  push_seconds=300, fallback_enabled=False,
                                  fallback_color="#FFFFFF", fallback_brightness=20))


def save_settings(path, value):
    value = validate_settings(value)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)
    return value

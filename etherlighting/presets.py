"""Persistent color shortcuts; editing a preset never rewrites device rules."""
import json
from core import COLOR

DEFAULTS = [
    {'name': 'Cameras', 'color': '#FF8A32'},
    {'name': 'Apple TVs', 'color': '#3388FF'},
    {'name': 'Home automation', 'color': '#42D9B5'},
    {'name': 'Audio', 'color': '#B784FF'},
]


def validate_presets(items):
    if not isinstance(items, list) or len(items) > 64:
        raise ValueError('Save up to 64 presets.')
    result, names = [], set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('Each preset needs a name and color.')
        name, color = item.get('name'), item.get('color')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
            raise ValueError('Give the preset a name of 1–40 characters.')
        name = name.strip()
        if any(ord(c) < 32 for c in name):
            raise ValueError('Preset names cannot contain control characters.')
        if name.casefold() in names:
            raise ValueError('A preset with that name already exists.')
        if not isinstance(color, str) or not COLOR.fullmatch(color):
            raise ValueError('Choose a valid six-digit color.')
        names.add(name.casefold())
        result.append(dict(name=name, color=color.upper()))
    return result


def load_presets(path):
    if not path.exists():
        return validate_presets(DEFAULTS)
    return validate_presets(json.loads(path.read_text(encoding='utf-8')))


def change_presets(path, current, change):
    operation = change.get('operation')
    original = change.get('original_name')
    index = next((i for i, item in enumerate(current) if item['name'] == original), None)
    if operation not in ('add', 'edit', 'delete'):
        raise ValueError('Choose add, edit, or delete.')
    if operation != 'add' and index is None:
        raise ValueError('That preset changed or was removed. Reopen the editor.')
    updated = [item.copy() for item in current]
    if operation == 'delete':
        updated.pop(index)
    else:
        item = dict(name=change.get('name'), color=change.get('color'))
        if operation == 'add':
            updated.append(item)
        else:
            updated[index] = item
    updated = validate_presets(updated)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(updated, indent=2), encoding='utf-8')
    temporary.replace(path)
    return updated

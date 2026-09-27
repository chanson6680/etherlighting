"""MAC discovery and deterministic color planning for a single UniFi switch."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

MAC = re.compile(r"[0-9a-f]{2}(?::[0-9a-f]{2}){5}")
COLOR = re.compile(r"#[0-9a-fA-F]{6}")


def mac(value):
    value = str(value).strip().lower().replace("-", ":")
    if not MAC.fullmatch(value):
        raise ValueError("Enter a MAC address such as aa:bb:cc:dd:ee:ff.")
    if int(value[:2], 16) & 1:
        raise ValueError("Use a device MAC address, not a multicast address.")
    return value


def parse_macs(text):
    lines = text.splitlines()
    header = next((i for i, line in enumerate(lines) if "mac-address" in line and "port" in line), None)
    if header is None or header + 1 >= len(lines):
        raise ValueError("The switch returned an unrecognized MAC table.")
    spans = [m.span() for m in re.finditer(r"-+", lines[header + 1])]
    if len(spans) != 8:
        raise ValueError("The switch MAC table columns have changed.")
    rows = []
    for line in lines[header + 2:]:
        if not line.strip() or line.startswith("Total number"):
            continue
        fields = [line[a:b].strip() for a, b in spans]
        try:
            port, vlan = int(fields[0]), int(fields[1])
            address = mac(fields[2])
            age = int(fields[6])
        except ValueError as error:
            raise ValueError("An unexpected row appeared in the switch MAC table.") from error
        if not 1 <= port <= 52:
            raise ValueError("The switch reported an unsupported port number.")
        rows.append(dict(mac=address, port=port, vlan=vlan, ip=fields[3],
                         name=fields[4], age=age, wireless=fields[7]))
    return rows


def parse_ports(text):
    ports = {}
    for line in text.splitlines():
        match = re.match(r"\s*(U?)(\d+)\s+(\S+/\S+)\s+(\d+)[FH]\b", line)
        if match:
            uplink, number, link, speed = match.groups()
            port = int(number)
            ports[port] = dict(port=port, uplink=bool(uplink), up=link == "U/U", speed=int(speed))
    if set(ports) != set(range(1, 53)):
        raise ValueError("Expected all 52 switch ports; discovery was incomplete.")
    return ports


def validate_rules(value):
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("This is not an Etherlighting rules file.")
    if not isinstance(value.get("rules"), list) or len(value["rules"]) > 2000:
        raise ValueError("Rules must contain a list of up to 2,000 devices.")
    result = []
    seen = set()
    for rule in value["rules"]:
        if not isinstance(rule, dict):
            raise ValueError("Each rule must describe one device.")
        address = mac(rule.get("mac", ""))
        if address in seen:
            raise ValueError("Each MAC address can have only one rule.")
        seen.add(address)
        color = str(rule.get("color", ""))
        if not COLOR.fullmatch(color):
            raise ValueError("Choose a valid six-digit color.")
        brightness = rule.get("brightness", 30)
        if type(brightness) is not int or not 1 <= brightness <= 100:
            raise ValueError("Brightness must be between 1 and 100.")
        enabled = rule.get("enabled", True)
        if type(enabled) is not bool:
            raise ValueError("Enabled must be true or false.")
        shared = rule.get("allow_shared", False)
        if type(shared) is not bool:
            raise ValueError("Shared-port permission must be true or false.")
        name = str(rule.get("name", ""))[:80]
        group = str(rule.get("group", ""))[:40]
        result.append(dict(mac=address, name=name, group=group, color=color.upper(),
                           brightness=brightness, enabled=enabled, allow_shared=shared))
    return dict(version=1, rules=result)


def load_rules(path):
    if not path.exists():
        return dict(version=1, rules=[])
    return validate_rules(json.loads(path.read_text(encoding="utf-8")))


def save_rules(path, value):
    value = validate_rules(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)
    return value


def make_plan(rows, ports, rules, max_age=300, settings=None):
    """Never choose silently between two locations or conflicting port colors."""
    by_mac, by_port = defaultdict(list), defaultdict(set)
    for row in rows:
        if row["age"] <= max_age and ports[row["port"]]["up"] and not row["wireless"].startswith("leave/"):
            by_mac[row["mac"]].append(row)
            by_port[row["port"]].add(row["mac"])
    decisions = []
    for rule in rules["rules"]:
        item = dict(rule, port=None, status="waiting", reason="Not recently seen on an active port")
        locations = {r["port"] for r in by_mac[rule["mac"]]}
        if not rule["enabled"]:
            item.update(status="paused", reason="Rule paused")
        elif len(locations) > 1:
            item.update(status="blocked", reason="MAC appears on more than one port")
        elif locations:
            port = next(iter(locations))
            item["port"] = port
            if ports[port]["uplink"]:
                item.update(status="blocked", reason="This is the switch uplink")
            elif len(by_port[port]) > 1 and not rule["allow_shared"]:
                item.update(status="blocked", reason="Shared port: choose whether this rule may color the whole port")
            else:
                item.update(status="ready", reason="Color will follow this MAC")
        decisions.append(item)
    pending = defaultdict(list)
    for item in decisions:
        if item["status"] == "ready":
            pending[item["port"]].append(item)
    desired = {}
    for port, items in pending.items():
        if len({(i["color"], i["brightness"]) for i in items}) > 1:
            for item in items:
                item.update(status="blocked", reason="Rules request different colors on this shared port")
        else:
            desired[port] = dict(color=items[0]["color"], brightness=items[0]["brightness"])
    fallback_ports = []
    if settings and settings["fallback_enabled"]:
        # Any saved rule reserves its current locations, including paused or
        # blocked rules. The fallback must not bypass their safety decisions.
        reserved = {row["port"] for rule in rules["rules"] for row in by_mac[rule["mac"]]}
        for port in sorted(by_port):
            if port not in reserved and not ports[port]["uplink"]:
                desired[port] = dict(color=settings["fallback_color"], brightness=settings["fallback_brightness"])
                fallback_ports.append(port)
    return dict(decisions=decisions, desired=desired, fallback_ports=fallback_ports)


def led_command(port, color, brightness):
    if type(port) is not int or not 1 <= port <= 52:
        raise ValueError("Unsupported port")
    if not isinstance(color, str) or not COLOR.fullmatch(color):
        raise ValueError("Invalid color")
    if type(brightness) is not int or not 1 <= brightness <= 100:
        raise ValueError("Invalid brightness")
    # The combined led_code path misrenders colors on this firmware. Use the
    # documented 16-bit PWM channels, including clearing the separate white LED.
    rgb = [round(int(color[i:i+2], 16) * 257 * brightness / 100) for i in (1, 3, 5)]
    channels = [('w', 0), *zip('rgb', rgb)]
    return ' && '.join(f"echo '{port} {channel} {value}' > /proc/led/led_color" for channel, value in channels)


def restore_command(mode):
    if type(mode) is not int or mode not in (0, 1, 2):
        raise ValueError("Unsupported stock Etherlighting mode")
    # Stock ubntbox emits this after applying its palette. It reselects the
    # current speed/network/PoE mode without changing switch networking.
    return f"echo '10 {mode}' > /proc/led/led_config"

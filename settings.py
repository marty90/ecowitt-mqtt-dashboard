"""Configuration loading and the process-wide MQTT hub, shared by run.py and app.py."""

from __future__ import annotations

import os
import threading

import yaml

from mqtt_hub import MqttHub, SensorConf

_HUBS: dict[str, MqttHub] = {}
_HUBS_LOCK = threading.Lock()


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg["dashboard"] = cfg.get("dashboard") or {}
    cfg["wh31"] = cfg.get("wh31") or []
    return cfg


def build_sensors(cfg: dict) -> list[SensorConf]:
    sensors = []
    if cfg.get("ws90"):
        w = cfg["ws90"]
        sensors.append(SensorConf(
            key="ws90", name=w.get("name", "Outdoor"), kind="ws90",
            host=w["host"], port=int(w.get("port", 1883)), topic=w["topic"].rstrip("/"),
            username=w.get("username"), password=w.get("password"),
        ))
    for i, s in enumerate(cfg["wh31"]):
        sensors.append(SensorConf(
            key=f"wh31_{i}", name=s.get("name", f"Sensor {i + 1}"), kind="wh31",
            host=s["host"], port=int(s.get("port", 1883)), topic=s["topic"].rstrip("/"),
            username=s.get("username"), password=s.get("password"),
        ))
    return sensors


def start_hub(path: str) -> MqttHub:
    """Return the MQTT hub for a config file, starting it on first use.

    There is one hub per config file per process, so run.py can start data
    collection before any browser connects and app.py reuses the same hub.
    """
    key = os.path.abspath(path)
    with _HUBS_LOCK:
        if key not in _HUBS:
            cfg = load_config(path)
            d = cfg["dashboard"]
            _HUBS[key] = MqttHub(build_sensors(cfg), d.get("history_db", "weather_history.sqlite"),
                                 int(d.get("sample_seconds", 60)))
        return _HUBS[key]

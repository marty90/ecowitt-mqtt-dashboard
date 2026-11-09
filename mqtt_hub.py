"""MQTT reader (paho-mqtt) for rtl_433 sensors, with a local SQLite history.

One paho client per broker (host:port), shared by all the sensors configured
on it. Latest values are kept in memory; a separate thread periodically saves
a sample to the SQLite history.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field

import paho.mqtt.client as mqtt

log = logging.getLogger(__name__)

# Fields that are not worth storing in the history
_NOT_HISTORY = {"id", "channel", "time", "flags", "firmware", "rain_start", "data", "mic", "model"}


@dataclass
class SensorConf:
    key: str            # unique internal id ("ws90", "wh31_0", ...)
    name: str           # display name
    kind: str           # "ws90" | "wh31"
    host: str
    port: int
    topic: str          # device base topic
    username: str | None = None
    password: str | None = None


@dataclass
class SensorState:
    values: dict = field(default_factory=dict)
    updated: float | None = None      # epoch of the last received message
    sampled: float | None = None      # epoch of the last saved sample


def _to_value(raw: str):
    raw = raw.strip()
    try:
        f = float(raw)
        return int(f) if f.is_integer() and "." not in raw else f
    except ValueError:
        return raw


class MqttHub:
    def __init__(self, sensors: list[SensorConf], db_path: str, sample_seconds: int = 60):
        self.sensors = {s.key: s for s in sensors}
        self.state = {s.key: SensorState() for s in sensors}
        self.db_path = db_path
        self.sample_seconds = sample_seconds
        self.lock = threading.Lock()
        self.broker_status: dict[str, tuple[str, str]] = {}  # broker -> (code, detail)
        self.clients: list[mqtt.Client] = []
        self._init_db()
        self._start_clients()
        threading.Thread(target=self._sampler, daemon=True, name="history-sampler").start()

    # ------------------------------------------------------------------ DB
    def _connect_db(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=10)
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def _init_db(self):
        with self._connect_db() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS samples ("
                " ts REAL NOT NULL, sensor TEXT NOT NULL, field TEXT NOT NULL, value REAL)"
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_samples ON samples(sensor, field, ts)")

    def _sampler(self):
        con = self._connect_db()
        while True:
            time.sleep(self.sample_seconds)
            rows = []
            now = time.time()
            with self.lock:
                for key, st in self.state.items():
                    if st.updated is None or (st.sampled and st.updated <= st.sampled):
                        continue
                    for f, v in st.values.items():
                        if f in _NOT_HISTORY or not isinstance(v, (int, float)):
                            continue
                        rows.append((now, key, f, float(v)))
                    st.sampled = now
            if rows:
                try:
                    con.executemany("INSERT INTO samples VALUES (?,?,?,?)", rows)
                    con.commit()
                except sqlite3.Error:
                    log.exception("Error writing history")

    def history(self, sensor_keys: list[str], since_ts: float):
        """Return rows (ts, sensor, field, value) since the given timestamp."""
        if not sensor_keys:
            return []
        q = ",".join("?" * len(sensor_keys))
        with self._connect_db() as con:
            return con.execute(
                f"SELECT ts, sensor, field, value FROM samples "
                f"WHERE sensor IN ({q}) AND ts >= ? ORDER BY ts",
                (*sensor_keys, since_ts),
            ).fetchall()

    def first_value_since(self, sensor: str, fname: str, since_ts: float):
        """First stored value of a field since the given timestamp (or None)."""
        with self._connect_db() as con:
            row = con.execute(
                "SELECT value FROM samples WHERE sensor=? AND field=? AND ts>=? ORDER BY ts LIMIT 1",
                (sensor, fname, since_ts),
            ).fetchone()
        return row[0] if row else None

    def minmax_since(self, sensor: str, fname: str, since_ts: float):
        with self._connect_db() as con:
            return con.execute(
                "SELECT MIN(value), MAX(value) FROM samples WHERE sensor=? AND field=? AND ts>=?",
                (sensor, fname, since_ts),
            ).fetchone()

    # ---------------------------------------------------------------- MQTT
    def _start_clients(self):
        brokers: dict[tuple, list[SensorConf]] = {}
        for s in self.sensors.values():
            brokers.setdefault((s.host, s.port, s.username, s.password), []).append(s)

        for (host, port, user, pwd), sens in brokers.items():
            bid = f"{host}:{port}"
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            if user:
                client.username_pw_set(user, pwd)
            client.user_data_set({"sensors": sens, "bid": bid})
            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.on_message = self._on_message
            client.reconnect_delay_set(1, 30)
            self.broker_status[bid] = ("connecting", "")
            try:
                client.connect_async(host, port, keepalive=60)
                client.loop_start()
            except Exception as e:  # noqa: BLE001
                self.broker_status[bid] = ("error", str(e))
            self.clients.append(client)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        bid = userdata["bid"]
        if reason_code.is_failure:
            self.broker_status[bid] = ("error", str(reason_code))
            return
        self.broker_status[bid] = ("connected", "")
        for s in userdata["sensors"]:
            client.subscribe(s.topic)          # JSON payload on the base topic
            client.subscribe(s.topic + "/+")   # one sub-topic per field

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.broker_status[userdata["bid"]] = ("disconnected", str(reason_code))

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode(errors="replace")
        for s in userdata["sensors"]:
            if mqtt.topic_matches_sub(s.topic, topic):
                try:
                    data = json.loads(payload)
                except ValueError:
                    continue
                if isinstance(data, dict):
                    self._update(s.key, data)
            elif mqtt.topic_matches_sub(s.topic + "/+", topic):
                fname = topic.rsplit("/", 1)[-1]
                self._update(s.key, {fname: _to_value(payload)})

    def _update(self, key: str, data: dict):
        with self.lock:
            st = self.state[key]
            st.values.update(data)
            st.updated = time.time()

    # ----------------------------------------------------------------- read
    def snapshot(self) -> dict[str, SensorState]:
        with self.lock:
            return {k: SensorState(dict(v.values), v.updated, v.sampled) for k, v in self.state.items()}

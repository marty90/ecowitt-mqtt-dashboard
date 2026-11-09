# Ecowitt MQTT Dashboard

A simple [Streamlit](https://streamlit.io) weather dashboard, inspired by the official
Ecowitt dashboard, for an **Ecowitt WS90** weather station and **WH31** temperature/humidity
sensors. Data are received over the air by an RTL-SDR dongle, decoded by
[rtl_433](https://github.com/merbanan/rtl_433), published to an MQTT broker and read by the
dashboard with [paho-mqtt](https://pypi.org/project/paho-mqtt/).

Features:

- Outdoor temperature, feels-like, dew point, humidity, today's min/max
- Wind speed, gust, max gust today, direction (compass) and Beaufort scale
- Rain rate and totals (last hour, today, last 24h, week, month, year)
- Solar radiation, brightness and UV index
- WS90 battery / supercapacitor status
- Any number of WH31 sensors with custom names
- Charts of the last 24 hours, local SQLite history
- Italian or English UI, optional password protection

## Recommended setup

```
WS90 / WH31  ))) 868 MHz )))  RTL-SDR  ->  rtl_433  ->  MQTT broker (mosquitto)  ->  dashboard
```

- **Sensors**: an Ecowitt **WS90** integrated weather station and, optionally, several
  **WH31** temperature/humidity sensors. Other sensors may be supported in the future.
- **Receiver**: an **RTL-SDR** USB dongle with an antenna for the sensors' band
  (868 MHz in Europe).
- **rtl_433**, configured to publish what it receives over MQTT, e.g.:

  ```bash
  rtl_433/src/rtl_433 -f 868M -C si -M time:unix:usec:utc -F mqtt
  ```

  `-F mqtt` publishes to the broker on `localhost:1883`; use e.g.
  `-F mqtt://192.168.1.21:1883` for a broker on another host. Topics look like
  `rtl_433/<hostname>/devices/Fineoffset-WS90/<id>/<field>`.
- **An MQTT broker**: [mosquitto](https://mosquitto.org) is recommended:

  ```bash
  sudo apt install mosquitto mosquitto-clients
  mosquitto_sub -v -t 'rtl_433/#'     # check that data are arriving
  ```

  Mosquitto 2.x only accepts local connections by default. If the dashboard runs on
  another machine, add a listener to `/etc/mosquitto/conf.d/lan.conf`:

  ```
  listener 1883
  allow_anonymous true
  ```

## Installation

```bash
git clone https://github.com/marty90/ecowitt-mqtt-dashboard.git
cd ecowitt-mqtt-dashboard
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.example.yaml config.yaml   # then edit config.yaml
.venv/bin/streamlit run app.py
```

Open http://localhost:8501. To use a different configuration file:

```bash
.venv/bin/streamlit run app.py -- --config other.yaml
```

## Configuration (`config.yaml`)

See [`config.example.yaml`](config.example.yaml) for a complete commented example.

| Key | Description |
| --- | --- |
| `password` | Optional. If set, the dashboard asks for this password. |
| `dashboard.language` | `en` or `it` |
| `dashboard.title`, `timezone`, `wind_unit` | Page title, time zone, `km/h` or `m/s` |
| `dashboard.refresh_seconds` | Page refresh interval |
| `dashboard.stale_seconds` | A sensor not updated for this long is highlighted in red |
| `dashboard.history_db`, `sample_seconds`, `chart_hours` | SQLite history file, sampling interval, chart window |
| `ws90` | `name`, `host`, `port`, optional `username`/`password`, and base `topic` of the station |
| `wh31` | List of sensors, each with `name` (display name), `host`, `port` and `topic` |

The WH31 topic is `<base>/<channel>/<id>`. The id changes when batteries are replaced; use
`+` instead of the id (e.g. `.../AmbientWeather-WH31E/1/+`) to ignore it.

Notes:

- The WS90 only sends a cumulative rain counter, so rain totals are computed from the local
  history: they only cover the time the dashboard has been running.
- The WS90 has no barometer (it is in the Ecowitt gateway), so pressure is not shown.
- The password is a simple access gate stored in plain text in `config.yaml`; put the
  dashboard behind HTTPS if it is exposed outside your LAN.

## Start at boot with cron

Run `crontab -e` and add lines like the following (adapt the paths). Each program starts in
a detached `screen` session at every reboot:

```cron
# rtl_433: receive sensors and publish to MQTT
@reboot sleep 20 && /usr/bin/screen -dmS rtl433 bash -c '/home/pi/rtl_433/src/rtl_433 -f 868M -C si -M time:unix:usec:utc -F mqtt'

# Weather dashboard on port 8501
@reboot sleep 30 && /usr/bin/screen -dmS dashboard bash -c 'cd /home/pi/ecowitt-mqtt-dashboard && .venv/bin/streamlit run app.py --server.port 8501'
```

Attach to a session with `screen -r rtl433` or `screen -r dashboard` (detach with
`Ctrl-A D`); list sessions with `screen -ls`.

## License

[MIT](LICENSE)

"""Start MQTT data collection immediately, then serve the Streamlit dashboard.

With plain `streamlit run app.py` the MQTT reader only starts when the first
browser opens the page. This launcher starts it right away, in the same
process, so data are collected and stored even if nobody uses the dashboard.

Usage:
    python run.py [--config config.yaml] [--port 8501] [other streamlit flags]

Any extra option (e.g. --server.address 0.0.0.0) is passed on to Streamlit.
"""

from __future__ import annotations

import argparse
import os
import sys

from streamlit.web import cli as stcli

import settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=os.environ.get("WEATHER_CONFIG", "config.yaml"),
                        help="configuration file (default: config.yaml)")
    parser.add_argument("--port", type=int, default=8501, help="HTTP port (default: 8501)")
    args, streamlit_flags = parser.parse_known_args()

    config = os.path.abspath(args.config)
    settings.start_hub(config)   # data collection starts here
    print(f"MQTT data collection started ({config})", flush=True)

    app = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
    sys.argv = [
        "streamlit", "run", app,
        "--server.port", str(args.port),
        # The file watcher could re-import modules on code changes and start a
        # second MQTT hub; it is not needed in production.
        "--server.fileWatcherType", "none",
        *streamlit_flags,
        "--", "--config", config,
    ]
    return stcli.main()


if __name__ == "__main__":
    sys.exit(main())

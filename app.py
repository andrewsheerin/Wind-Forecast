from flask import Flask, render_template, request, jsonify, send_from_directory
from open_meteo import OpenMeteo
from open_meteo.models import HourlyParameters
from datetime import datetime, timedelta
import asyncio
import threading
import numpy as np
import os

# ---- Matplotlib (PNG output only)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

app = Flask(__name__)

# Ensure a static path for the rendered figure
STATIC_DIR = os.path.join(app.root_path, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
PLOT_PATH = os.path.join(STATIC_DIR, "figure.png")

# Open-Meteo client
open_meteo = OpenMeteo()

async def fetch_openmeteo(lat: float, lon: float, hours: int = 120):
    forecast = await open_meteo.forecast(
        latitude=lat,
        longitude=lon,
        current_weather=False,
        wind_speed_unit='kn',
        hourly=[
            HourlyParameters.TEMPERATURE_2M,
            HourlyParameters.WIND_DIRECTION_10M,
            HourlyParameters.WIND_SPEED_10M,
            HourlyParameters.WIND_GUSTS_10M
        ],
    )

    nhours = max(1, int(hours))
    hourly_time = forecast.hourly.time[0:nhours]
    wind_dir = forecast.hourly.wind_direction_10m[0:nhours]
    wind_speed = forecast.hourly.wind_speed_10m[0:nhours]
    wind_gusts = forecast.hourly.wind_gusts_10m[0:nhours]

    # Normalize timestamps to datetimes for Matplotlib
    times_dt = []
    for t in hourly_time:
        if isinstance(t, datetime):
            times_dt.append(t)
        else:
            try:
                times_dt.append(datetime.fromisoformat(str(t).replace("Z", "+00:00")))
            except Exception:
                times_dt.append(datetime.fromtimestamp(0))

    return {
        "time_dt": times_dt,
        "wind_dir": list(wind_dir),
        "wind_speed": list(wind_speed),
        "wind_gust": list(wind_gusts),
    }

# Background event loop runner for async client
class _LoopRunner:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coro, timeout=None):
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)

loop_runner = _LoopRunner()

def render_png(series, out_path: str):
    wind_speed = np.array(series["wind_speed"])
    wind_gusts = np.array(series["wind_gust"])
    wind_dir = series["wind_dir"]
    hourly_time = series["time_dt"]

    # A little taller overall, but we give the chart *less* of that height
    fig = plt.figure(figsize=(16, 4.2), constrained_layout=True)

    # change background to transparent
    fig.patch.set_alpha(0.0)

    # Two rows: tall(ish) chart on top, dedicated table axis on bottom
    gs = fig.add_gridspec(nrows=2, ncols=1, height_ratios=[3.7, 0.5])
    ax = fig.add_subplot(gs[0])
    ax_table = fig.add_subplot(gs[1])
    ax_table.axis("off")  # table only

    cmap = plt.get_cmap('viridis_r')
    normalize = plt.Normalize(vmin=float(np.min(wind_speed)), vmax=float(np.max(wind_gusts)))

    ax.grid(color='lightgrey', linestyle='-')
    ax.set_facecolor('whitesmoke')

    # Bars + gust range
    gust_nerr = [0] * len(wind_speed)
    gust_perr = np.abs(wind_gusts - wind_speed)
    ax.bar(
        hourly_time,
        wind_speed,
        yerr=(gust_nerr, gust_perr),
        ecolor=cmap(normalize(wind_gusts)),
        width=0.02,  # a bit slimmer = less visual height
        color=cmap(normalize(wind_speed)),
        edgecolor=cmap(normalize(wind_speed)),
        linewidth=0
    )

    ax.set_ylim(0, float(np.max(wind_gusts)) + 3)
    ax.set_ylabel('Knots', labelpad=10)
    ax.tick_params(axis='x', length=4, labelsize=8, colors='black', rotation=35)
    ax.set_xlim(hourly_time[0] - timedelta(hours=0.5), hourly_time[-1] + timedelta(hours=0.5))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %H"))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))

    # Colorbar that plays nicely with constrained_layout
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=normalize)
    sm.set_array([])
    fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.02, label='Wind Speed')

    # --- Table in its own axis (no clipping, easy to size) ---
    table = ax_table.table(
        cellText=[wind_dir],
        rowLabels=['Wind Dir (°)'],
        cellLoc='center',
        loc='center',
        bbox=[0, 0, 1, 1]  # full table axis
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)

    # Make cells taller & a bit wider so contents fit
    table.scale(1.05, 1.05)  # (x_scale, y_scale) -> increase y to make rows taller

    # Save
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


@app.route("/")
def index():
    return render_template("windapp.html")

@app.route("/api/forecast", methods=["POST"])
def api_forecast():
    try:
        payload = request.get_json(force=True)
        lat = float(payload["lat"])
        lon = float(payload["lon"])
        hours = 120 # 5 days
    except Exception:
        return jsonify({"error": "Invalid payload. Provide lat, lon, optional hours."}), 400

    try:
        series = loop_runner.run(fetch_openmeteo(lat, lon, hours), timeout=30)
        # render_png(series, PLOT_PATH)
        times_iso = [t.isoformat() for t in series["time_dt"]]
        return jsonify({
            "time": times_iso,
            "wind_dir": series["wind_dir"],
            "wind_speed": series["wind_speed"],
            "wind_gust": series["wind_gust"],
            "meta": {"lat": lat, "lon": lon, "hours": hours, "unit": "knots"}
        })
    except Exception as e:
        return jsonify({"error": f"Forecast fetch failed: {e}"}), 500


# @app.route("/plot.png")
# def plot_png():
#     # Served from /static/figure.png with no caching by the browser (we’ll also add a ts query param client-side)
#     return send_from_directory(STATIC_DIR, "figure.png", max_age=0)


if __name__ == "__main__":
    app.run(debug=True)

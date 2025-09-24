let map, marker = null;

function initMap() {
  map = L.map('map').setView([39.5, -98.35], 4);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: 'abcd',
      maxZoom: 15,
      minZoom: 3,
      center: [42.356559, -71.085752]       // center map on starting point
    }).addTo(map);
  map.on('click', (e) => {
    const { lat, lng } = e.latlng;
    setPoint(lat, lng);
  });

  // Default point (MIT)
  setPoint(42.356559, -71.085752);

}

function setPoint(lat, lon) {
  document.getElementById('lat').value = lat.toFixed(5);
  document.getElementById('lon').value = lon.toFixed(5);
  if (marker) {
    marker.setLatLng([lat, lon]);
  } else {
    marker = L.marker([lat, lon]).addTo(map);
  }
}

async function getForecast() {
  const lat = parseFloat(document.getElementById('lat').value);
  const lon = parseFloat(document.getElementById('lon').value);
  const hours = 120;
  if (Number.isNaN(lat) || Number.isNaN(lon)) {
    alert('Click the map to select a point first.');
    return;
  }

  const btn = document.getElementById('go');
  btn.disabled = true; btn.textContent = 'Fetching...';

  try {
    const res = await fetch('/api/forecast', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat, lon, hours })
    });
    if (!res.ok) {
      const e = await res.json().catch(() => ({}));
      throw new Error(e.error || `Request failed (${res.status})`);
    }

    const { time, wind_dir, wind_speed, wind_gust } = await res.json();

    // --- default 36-hour view over full series ---
    const overallStart = new Date(time[0]);
    const overallEnd   = new Date(time[time.length - 1]);
    const fixedSpan = 36 * 3600 * 1000;
    const rangeStart = new Date(overallStart.getTime());
    const rangeEndDefault = new Date(overallStart.getTime() + fixedSpan);

    // --- error lengths (gust - speed) ---
    const err = wind_speed.map((v, i) => Math.max(0, (wind_gust[i] ?? v) - v));

    // --- bars ---
    const bar = {
      type: 'bar',
      x: time,
      y: wind_speed,
      name: 'Wind speed (kt)',
      marker: {
        color: wind_speed,
        colorscale: 'Viridis',
        cmin: Math.min(...wind_speed),
        cmax: Math.max(...wind_gust)
      },
      error_y: {
        type: 'data',
        symmetric: false,
        array: err,
        arrayminus: new Array(err.length).fill(0),
        visible: true,
        capthickness: 0,
        layer: 'below'
      },
      hovertemplate: '%{x}<br>Speed: %{y:.1f} kt<br>Gust: %{customdata:.1f} kt<extra></extra>',
      customdata: wind_gust,
      xaxis: 'x',
      yaxis: 'y'
    };

    // --- wind direction row as text trace (scrolls with xaxis) ---
    const dirText = wind_dir.map(v => (v == null ? '' : `${Math.round(v)}°`));
    const dirRow = {
      type: 'scatter',
      mode: 'text',
      x: time,
      y: new Array(time.length).fill(-0.8),  // a flat row
      text: dirText,
      textposition: 'middle center',
      hoverinfo: 'skip',
      xaxis: 'x',
      yaxis: 'y2'
    };

    const layout = {
      margin: { l: 60, r: 20, t: 20, b: 40 },
      paper_bgcolor: 'rgb(245, 245, 245)',
      plot_bgcolor: 'rgb(245, 245, 245)',
      showlegend: false,

      // X axis: default 2-day view + slider to scroll through all
        xaxis: {
          domain: [0.0, 1],
          type: 'date',
          range: [rangeStart, rangeEndDefault],
          rangeslider: { visible: false },   // 👈 turn off the bottom slider
          fixedrange: false,                 // 👈 allow panning
          tickformat: '%a %H',
          tickangle: 0,
          anchor: 'y'
        },

      // main chart above
      yaxis: {
        title: 'Knots',
        domain: [0.30, 1.0],
        fixedrange: true
      },

      // wind dir row below (just space to render text)
      yaxis2: {
        domain: [0.00, 0.15],
        visible: false,
        fixedrange: true
      }
    };

    Plotly.newPlot('plot', [bar, dirRow], layout, { responsive: true });
    Plotly.relayout('plot', { 'dragmode': 'pan' });

    const plot = document.getElementById('plot');

    plot.on('plotly_relayout', ev => {
      if (ev['xaxis.range[0]']) {
        const start = new Date(ev['xaxis.range[0]']); // pad a bit
        const fixedSpan = 36.5 * 60 * 60 * 1000; // 36 hours
        const newEnd = new Date(start.getTime() + fixedSpan);

        Plotly.relayout(plot, {
          'xaxis.range': [start, newEnd]
        });
      }
    });


  } catch (err) {
    console.error(err);
    alert(err.message || 'Failed to fetch forecast.');
  } finally {
    btn.disabled = false; btn.textContent = 'Generate Forecast';
  }
}


document.addEventListener('DOMContentLoaded', () => {
  initMap();
  document.getElementById('go').addEventListener('click', getForecast);
});

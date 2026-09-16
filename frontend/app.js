const API_BASE = window.MNLCC_CONFIG.API_BASE;

let layerMetadata = {};
let activeLayerId = null;
let activeGeeLayer = null;
let legendControl = null;

const geeLayers = {};
const layerIdByLeafletId = new Map();

let userLocationMarker = null;
let userAccuracyCircle = null;

// -----------------------------
// Base layers
// -----------------------------

const osm = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors"
});

const esriImagery = L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  {
    maxZoom: 19,
    attribution:
      "Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community"
  }
);

const map = L.map("map", {
  center: [46.5, -93.5],
  zoom: 6,
  layers: [osm]
});

const baseMaps = {
  "OpenStreetMap": osm,
  "Satellite imagery": esriImagery
};

const overlayMaps = {};

const layerControl = L.control.layers(baseMaps, overlayMaps, {
  collapsed: false
}).addTo(map);

// -----------------------------
// Layer loading
// -----------------------------

async function loadLayers() {
  const response = await fetch(`${API_BASE}/layers`);
  layerMetadata = await response.json();

  const layerIds = Object.keys(layerMetadata);

  for (const layerId of layerIds) {
    await registerGeeLayer(layerId);
  }

  let defaultLayerIds = layerIds.filter(
    (layerId) => layerMetadata[layerId].default_visible && geeLayers[layerId]
  );

  if (defaultLayerIds.length === 0) {
    const firstRegisteredId = layerIds.find((layerId) => geeLayers[layerId]);
    if (firstRegisteredId) {
      defaultLayerIds = [firstRegisteredId];
    }
  }

  for (const layerId of defaultLayerIds) {
    geeLayers[layerId].addTo(map);
  }

  if (defaultLayerIds.length > 0) {
    setActiveLayer(defaultLayerIds[defaultLayerIds.length - 1]);
  }
}

async function registerGeeLayer(layerId) {
  const layer = layerMetadata[layerId];

  let response;
  try {
    response = await fetch(`${API_BASE}/tiles/${layerId}`);
  } catch (error) {
    console.error(`Could not load layer: ${layerId}`, error);
    return;
  }

  if (!response.ok) {
    console.error(`Could not load layer: ${layerId}`);
    return;
  }

  const data = await response.json();

  const opacity = layer.opacity ?? 0.75;

  const geeLayer = L.tileLayer(data.tile_url, {
    opacity: opacity,
    attribution: "Google Earth Engine"
  });

  geeLayers[layerId] = geeLayer;

  const leafletId = L.stamp(geeLayer);
  layerIdByLeafletId.set(leafletId, layerId);

  layerControl.addOverlay(geeLayer, layer.name || layerId);
}

function setActiveLayer(layerId) {
  if (!layerId || !geeLayers[layerId]) {
    return;
  }

  activeLayerId = layerId;
  activeGeeLayer = geeLayers[layerId];

  addLegend(layerId);

  const slider = document.getElementById("opacity-slider");
  if (slider && activeGeeLayer) {
    slider.value = activeGeeLayer.options.opacity ?? 0.75;
  }
}

map.on("overlayadd", function (e) {
  const layerId = layerIdByLeafletId.get(L.stamp(e.layer));

  if (layerId) {
    setActiveLayer(layerId);
  }
});

map.on("overlayremove", function (e) {
  const removedLayerId = layerIdByLeafletId.get(L.stamp(e.layer));

  if (removedLayerId === activeLayerId) {
    const stillVisibleLayerId = Object.keys(geeLayers).find((layerId) =>
      map.hasLayer(geeLayers[layerId])
    );

    if (stillVisibleLayerId) {
      setActiveLayer(stillVisibleLayerId);
    } else {
      activeLayerId = null;
      activeGeeLayer = null;

      if (legendControl) {
        map.removeControl(legendControl);
        legendControl = null;
      }
    }
  }
});

// -----------------------------
// Legend
// -----------------------------

function addLegend(layerId) {
  if (legendControl) {
    map.removeControl(legendControl);
  }

  const layer = layerMetadata[layerId];

  if (!layer) {
    return;
  }

  legendControl = L.control({ position: "bottomright" });

  legendControl.onAdd = function () {
    const div = L.DomUtil.create("div", "legend");

    if (layer.legend_type === "categorical" && layer.classes?.length > 0) {
      const rows = layer.classes
        .map((cls) => {
          return `
            <div class="legend-row">
              <span class="legend-swatch" style="background:#${cls.color};"></span>
              <span>${cls.label}</span>
            </div>
          `;
        })
        .join("");

      div.innerHTML = `
        <div class="legend-title">${layer.name}</div>
        ${rows}
      `;

      return div;
    }

    const vis = layer.vis;
    const palette = vis.palette;
    const min = vis.min;
    const max = vis.max;
    const unit = layer.unit || "";

    const gradient = palette
      .map((color, index) => {
        const pct = (index / (palette.length - 1)) * 100;
        return `#${color} ${pct}%`;
      })
      .join(", ");

    const maxLabel = layer.clamp_max ? `${max}+` : `${max}`;

    div.innerHTML = `
      <div class="legend-title">${layer.name}</div>
      <div class="legend-gradient" style="background: linear-gradient(to right, ${gradient});"></div>
      <div class="legend-labels">
        <span>${min}${unit}</span>
        <span>${maxLabel}${unit}</span>
      </div>
    `;

    return div;
  };

  legendControl.addTo(map);
}

// -----------------------------
// Opacity control
// -----------------------------

const OpacityControl = L.Control.extend({
  options: {
    position: "topright"
  },

  onAdd: function () {
    const container = L.DomUtil.create("div", "opacity-control");

    container.innerHTML = `
      <label>
        Active layer opacity<br>
        <input id="opacity-slider" type="range" min="0" max="1" step="0.05" value="0.75">
      </label>
    `;

    L.DomEvent.disableClickPropagation(container);

    setTimeout(() => {
      const slider = document.getElementById("opacity-slider");

      slider.addEventListener("input", function () {
        if (activeGeeLayer) {
          activeGeeLayer.setOpacity(Number(this.value));
        }
      });
    }, 0);

    return container;
  }
});

map.addControl(new OpacityControl());

// -----------------------------
// Locate me control
// -----------------------------

function locateMe() {
  map.locate({
    setView: true,
    maxZoom: 14,
    enableHighAccuracy: true
  });
}

const LocateControl = L.Control.extend({
  options: {
    position: "topleft"
  },

  onAdd: function () {
    const button = L.DomUtil.create("button", "locate-button");
    button.innerHTML = "📍 Locate me";
    button.title = "Zoom to my current location";

    L.DomEvent.on(button, "click", function (e) {
      L.DomEvent.stopPropagation(e);
      locateMe();
    });

    return button;
  }
});

map.addControl(new LocateControl());

map.on("locationfound", function (e) {
  if (userLocationMarker) {
    map.removeLayer(userLocationMarker);
  }

  if (userAccuracyCircle) {
    map.removeLayer(userAccuracyCircle);
  }

  userLocationMarker = L.marker(e.latlng)
    .addTo(map)
    .bindPopup(
      `You are here<br>
       Lat: ${e.latlng.lat.toFixed(5)}<br>
       Lon: ${e.latlng.lng.toFixed(5)}<br>
       Accuracy: ${Math.round(e.accuracy)} m`
    )
    .openPopup();

  userAccuracyCircle = L.circle(e.latlng, {
    radius: e.accuracy
  }).addTo(map);
});

map.on("locationerror", function (e) {
  alert("Location unavailable: " + e.message);
});

// -----------------------------
// Click-to-query
// -----------------------------

function formatQueriedValue(rawValue, layer, unit) {
  if (rawValue === null || rawValue === undefined) {
    return "No data";
  }

  const numericValue = Number(rawValue);

  if (layer.legend_type === "categorical") {
    const match = layer.classes?.find(
      (cls) => Number(cls.value) === numericValue
    );

    if (match) {
      return `${numericValue}: ${match.label}`;
    }

    return `${numericValue}`;
  }

  if (Number.isFinite(numericValue)) {
    return `${numericValue.toFixed(1)}${unit}`;
  }

  return `${rawValue}${unit}`;
}

map.on("click", async function (e) {
  const lat = e.latlng.lat;
  const lon = e.latlng.lng;

  if (!activeLayerId) {
    L.popup()
      .setLatLng(e.latlng)
      .setContent("No active model layer selected.")
      .openOn(map);
    return;
  }

  const layer = layerMetadata[activeLayerId];

  const popup = L.popup()
    .setLatLng(e.latlng)
    .setContent("Querying model value...")
    .openOn(map);

  try {
    const response = await fetch(
      `${API_BASE}/value/${activeLayerId}?lat=${lat}&lon=${lon}`
    );

    const data = await response.json();

    const valueObj = data.value || {};
    const bandNames = Object.keys(valueObj);

    let valueText = "No data";

    if (bandNames.length > 0) {
      const rawValue = valueObj[bandNames[0]];
      const unit = data.unit || layer.unit || "";
      valueText = formatQueriedValue(rawValue, layer, unit);
    }

    popup.setContent(`
      <strong>${layer.name}</strong><br>
      Value: ${valueText}<br>
      Lat: ${lat.toFixed(5)}<br>
      Lon: ${lon.toFixed(5)}
    `);

  } catch (error) {
    popup.setContent(`
      <strong>Error querying value</strong><br>
      ${error}
    `);
  }
});

// -----------------------------
// Initialize app
// -----------------------------

loadLayers();

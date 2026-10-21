# MNLCC Viewer Architecture

## Overview

MNLCC Viewer uses a three-part architecture:

```text
Browser
  ↓
Leaflet frontend
  ↓
FastAPI backend
  ↓
Google Earth Engine
```

The frontend never talks directly to Earth Engine. All Earth Engine access is handled by the backend.

## Design Goals

1. Keep the frontend independent of Earth Engine asset details.
2. Keep all layer definitions centralized in `layers.json`.
3. Make new spatial products easy to add — usually just a new entry in `layers.json`.
4. Build toward future validation and observation workflows.

## Frontend

The frontend is a static Leaflet application.

Responsibilities:

- render the map
- switch basemaps
- request available layers
- display Earth Engine tiles
- manage layer visibility
- show legends
- control opacity
- locate the user
- query raster values on click

Current frontend files:

```text
frontend/index.html
frontend/app.js
frontend/style.css
frontend/config.js
```

The frontend starts by calling:

```text
GET /layers
```

It then registers every layer returned by the backend as a Leaflet overlay.

## Backend

The backend is a FastAPI application.

Responsibilities:

- authenticate with Google Earth Engine
- load layer metadata from `layers.json`
- construct Earth Engine images
- generate tile URLs
- query pixel values
- expose a REST API for the frontend

Current backend files:

```text
backend/app.py
backend/layers.py
backend/layers.json
backend/config.py
```

## API

### `GET /health`

Returns simple backend health status.

### `GET /layers`

Returns public metadata for every configured map layer.

### `GET /outlines`

Returns tile URLs for silent outline overlays (currently `tribal_outline`). Drawn by the frontend
above the data layers, but not part of `/layers`: no legend, layer-control entry, or click query.

### `GET /tiles/{layer_id}`

Returns an XYZ tile URL for a given layer. The backend constructs the Earth Engine image, applies
transformations, applies visualization parameters, and returns the tile URL.

### `GET /value/{layer_id}?lat={lat}&lon={lon}`

Returns the raster value at a clicked coordinate. Used for map popups.

## Layer Catalog

The layer catalog is stored in `backend/layers.json`. Each entry is `layer_id: {config}`, with a
unique ID, display name, type, visualization parameters, legend metadata, and optional
transformation rules.

Example:

```json
{
  "prob_lgbm": {
    "name": "Lowland Conifer Probability (LGBM)",
    "type": "gee_image",
    "asset": "projects/ee-jeli0026/assets/mn_lowland_conifer_v20260916/prob_lgbm",
    "scale": 30,
    "unit": "%",
    "nodata_value": 255,
    "value_multiplier": 0.5,
    "legend_type": "continuous",
    "vis": {
      "min": 0,
      "max": 100,
      "palette": ["440154", "..."]
    }
  }
}
```

### `gee_image`

A direct Earth Engine image asset. The seven raw MNLCC layers (probability, four compositional
percentages, depth, carbon stock) are single-band ingested assets under
`projects/ee-jeli0026/assets/mn_lowland_conifer_v20260916/`, all using this type.

Every `gee_image` layer is **automatically masked** to exclude USGS NLCD 2021 open water (class
11), developed/impervious land (classes 21-24, Open Space through High Intensity), and barren
land (class 31 — includes strip mines, gravel pits, and quarries, e.g. the Mesabi Iron Range open
pits) — `_apply_common_transforms()` in `backend/layers.py` applies `_nlcd_exclusion_mask()`
unconditionally, before any other transform. Masked pixels render fully transparent (not a solid
color), so basemap/imagery shows through. This is unconditional for every `gee_image` layer; there
is currently no per-layer opt-out. Note class 31 also covers non-mining barren land (natural rock
outcrops, beaches); NLCD has no separate "extractive" class, so this is the standard tradeoff for
masking mining areas.

Supported transformations (`_apply_common_transforms` in `backend/layers.py`):

- NLCD water + developed + barren/extractive exclusion (see above; always applied)
- `nodata_value` — exact-value mask (255 for the uint8 layers, 65535 for the uint16 layers)
- `valid_min` / `valid_max` — inequality mask
- `value_multiplier` / `value_offset` — rescale raw stored values to public units
- `self_mask` — mask out zero-valued pixels (not used by any current MNLCC raw layer, since 0 is
  a real value for all seven)
- `band` — select a single band (not currently needed; all assets are single-band)

### `threshold_binary`

Binarizes another *configured* layer (via `source_layer` + `threshold`, compared post-transform,
i.e. in the same units as the source layer's public values — e.g. percent, not raw 0-200).
Ported from askdb-viewer's pattern; the one current use is `peat_extent_mask` (see below).

Optional `exclude_nlcd_water: true` additionally applies `_nlcd_exclusion_mask()` directly (on
top of whatever the source layer already applied). Redundant for any `threshold_binary` whose
source is a `gee_image` layer (already auto-masked — see above), but kept as an explicit option
for robustness if a future source layer type isn't auto-masked.

The askdb-viewer sibling project additionally supports `peat_pf_combo` and `soil_extent_mask`
derived layer types. Neither is wired up here since no current MNLCC layer needs them.

### `nlcd_water`

A standalone categorical layer showing USGS NLCD 2021 open-water pixels only (class 11),
independent of any other layer or of the water+developed exclusion above —
`landcover.eq(11).selfMask()`. Does **not** go through `_apply_common_transforms`, so it is
unaffected by the auto-masking. The one current use is `water_mask` (see below). Shares the
`_nlcd_landcover()` helper in `backend/layers.py` with the exclusion mask.

### Tribal lands mask and `tribal_outline`

`TRIBAL_MASK_ASSET` in `backend/layers.py` (dissolved tribal-lands polygons) is rasterized with
`.paint()` and applied unconditionally in `_apply_common_transforms()` (and to `nlcd_water`), so no
layer shows data inside the polygons. The `tribal_outline` layer type draws the same polygons via
`FeatureCollection.style()` (dark grey, 1px, transparent fill). It is excluded from
`public_layer_metadata()` and exposed only through `/outlines`.

### Prediction domain mask

`DOMAIN_MASK_ASSET` in `backend/layers.py` (prediction-domain polygons) is rasterized with
`.paint()` by `_domain_mask()` and applied unconditionally in `_apply_common_transforms()` (and to
`nlcd_water`), so every layer shows data only inside the polygons. There is no outline overlay.

### `mask_layer`

A `gee_image` layer with `"mask_layer": "<layer_id>"` is masked by that layer's image after its own
transforms. `depth` and `carbon_belowground_fullstock` use `"mask_layer": "peat_extent_mask"`.
Because Earth Engine evaluates the threshold at the tile's zoom-level scale (on the mean-pyramided
`prob_lgbm`), this keeps both layers' footprint identical to the extent layer at every zoom. Without
it, their own mean pyramids show any coarse pixel containing a single valid 30 m pixel, so they look
far more extensive than the extent layer when zoomed out.

`prob_lgbm` also uses `"mask_layer": "peat_extent_mask"`, plus `"mask_layer_min_pixel_m": 45`, which
applies the mask only when the output pixel is coarser than 45 m (tested via `ee.Image.pixelArea()`,
which is evaluated in the tile's projection). In Minnesota that switch falls between web-map zoom 11
(~53 m pixels, masked) and zoom 12 (~26 m, unmasked), so full-resolution views and `/value` clicks
still show every probability. Since `peat_extent_mask` is derived from `prob_lgbm`,
`threshold_binary` fetches its source with `apply_mask_layer=False` to avoid recursion.

### Reference overlay layers

Two standalone, opt-in overlays, both `default_visible: false`:

- `peat_extent_mask` — `threshold_binary` on `prob_lgbm` at 36.2%, the ≥0.362 probability cutoff
  from Nic's trial GEE scripts. (No longer needs its own `exclude_nlcd_water` — inherited from
  `prob_lgbm`'s auto-mask.)
- `water_mask` — `nlcd_water`, shown as a black reference layer, matching the "NLCD Open Water"
  toggle in Nic's trial scripts.

These exist for users who want to see predicted peat extent or open water as an explicit
reference boundary on the map, distinct from the automatic water/developed exclusion that now
applies to every raw layer regardless of whether either toggle is on.

## Legends

### Continuous

Used for all seven current MNLCC layers (probability and compositional percentages, depth,
carbon stock). Requires `"legend_type": "continuous"` and a `vis` ramp (`min`, `max`, `palette`).

### Categorical

Used for class layers (not currently present in the MNLCC catalog, but supported by the frontend
for future derived/classified products). Requires `"legend_type": "categorical"` and a `classes`
array of `{value, label, color}`.

## Current Local Development Flow

Run backend:

```bash
cd backend
source .venv/bin/activate
uvicorn app:app --reload
```

Run frontend:

```bash
cd frontend
python3 -m http.server 5500
```

Open `http://127.0.0.1:5500`.

## Future Features

Planned additions (mirroring the askdb-viewer roadmap):

- Cloud Run + Cloudflare Pages production deployment (see `docs/deployment.md`)
- observation/comment submission
- Postgres/PostGIS support
- authentication for expert validation
- downloadable query results

import json
from pathlib import Path

import ee


LAYER_FILE = Path(__file__).parent / "layers.json"

# Project landcover mask (also shown as the "landcover_mask" layer). Classes:
# 0 none, 1 water, 2 urban/developed, 3 mining/extraction, 4 agriculture.
# Every gee_image layer is auto-masked where it is 1-3; agriculture (4) is
# deliberately left visible.
LANDCOVER_MASK_ASSET = (
    "projects/ee-jeli0026/assets/mn_lowland_conifer_v20260916/"
    "landcover-mask-v1-09NOV2026"
)
LANDCOVER_EXCLUDED_CLASSES = [1, 2, 3]

# Only used by the (disabled) "nlcd_water" reference layer type.
NLCD_COLLECTION = "USGS/NLCD_RELEASES/2021_REL/NLCD"
NLCD_YEAR = "2021"
NLCD_WATER_CLASS = 11

# Polygons (dissolved tribal lands) that are masked out of every data layer and
# drawn as a silent outline overlay (see "tribal_outline" layer type).
TRIBAL_MASK_ASSET = "projects/ee-jeli0026/assets/tribal-lands-mask-dissolved-23SEP2026"

# Prediction domain polygons: every data layer is masked to show data only
# inside these polygons.
DOMAIN_MASK_ASSET = "projects/ee-jeli0026/assets/mn-lowland-conifer-lta-mask-21OCT2026"


def load_layers():
    with open(LAYER_FILE, "r") as f:
        return json.load(f)


LAYERS = load_layers()


def get_layer_config(layer_id: str):
    return LAYERS.get(layer_id)


def _apply_common_transforms(img, cfg):
    """Apply common masking and scaling operations to a GEE image."""

    # Layers that themselves depict water/developed/mining (e.g. the
    # landcover mask) must not have those classes masked out.
    if not cfg.get("skip_landcover_mask", False):
        img = img.updateMask(_landcover_exclusion_mask())

    img = img.updateMask(_tribal_mask())
    img = img.updateMask(_domain_mask())

    if "nodata_value" in cfg:
        nodata = cfg["nodata_value"]
        img = img.updateMask(img.neq(nodata))

    if "valid_max" in cfg:
        valid_max = cfg["valid_max"]
        img = img.updateMask(img.lte(valid_max))

    if "valid_min" in cfg:
        valid_min = cfg["valid_min"]
        img = img.updateMask(img.gte(valid_min))

    multiplier = cfg.get("value_multiplier", 1)
    offset = cfg.get("value_offset", 0)

    if multiplier != 1 or offset != 0:
        img = img.multiply(multiplier).add(offset)

    if cfg.get("self_mask", False):
        img = img.selfMask()

    return img


def _nlcd_landcover():
    return (
        ee.ImageCollection(NLCD_COLLECTION)
        .filter(ee.Filter.eq("system:index", NLCD_YEAR))
        .first()
        .select("landcover")
    )


def _landcover_exclusion_mask():
    """Mask out water, urban/developed and mining/extraction pixels of the
    project landcover mask (agriculture stays visible). Pixels where the
    asset has no data count as class 0, i.e. are kept."""

    landcover = ee.Image(LANDCOVER_MASK_ASSET).unmask(0)
    mask = landcover.neq(LANDCOVER_EXCLUDED_CLASSES[0])

    for cls in LANDCOVER_EXCLUDED_CLASSES[1:]:
        mask = mask.And(landcover.neq(cls))

    return mask


def _tribal_features():
    return ee.FeatureCollection(TRIBAL_MASK_ASSET)


def _tribal_mask():
    """Mask that is 0 inside tribal-land polygons and 1 everywhere else."""

    return ee.Image(0).byte().paint(_tribal_features(), 1).eq(0)


def _domain_mask():
    """Mask that is 1 inside the prediction-domain polygons and 0 everywhere else."""

    return ee.Image(0).byte().paint(ee.FeatureCollection(DOMAIN_MASK_ASSET), 1)


def get_layer_image(cfg, apply_mask_layer=True, classify=True):
    """classify=False returns raw values for binned layers (used by
    click-to-query, so the popup shows e.g. the actual depth)."""

    layer_type = cfg["type"]

    if layer_type == "gee_image":
        img = ee.Image(cfg["asset"])

        if "band" in cfg:
            img = img.select(cfg["band"])

        img = _apply_common_transforms(img, cfg)

        # Clip to another layer's footprint (e.g. peat_extent_mask). Evaluated
        # at the map's zoom-level scale, so this layer appears and disappears
        # exactly where the mask layer does when zoomed out.
        if apply_mask_layer and "mask_layer" in cfg:
            mask_cfg = get_layer_config(cfg["mask_layer"])

            if mask_cfg is None:
                raise ValueError(f"Mask layer not found: {cfg['mask_layer']}")

            mask = get_layer_image(mask_cfg).unmask(0)

            # Optionally apply the mask only when zoomed out: pixelArea() is
            # evaluated in the output projection, so it grows with the tile's
            # pixel size. Below the threshold the mask is all ones.
            if "mask_layer_min_pixel_m" in cfg:
                min_px = cfg["mask_layer_min_pixel_m"]
                mask = mask.Or(ee.Image.pixelArea().lt(min_px * min_px))

            img = img.updateMask(mask)

        # Bin continuous values into classes 1..N: values below the first
        # edge are hidden; class k covers [bins[k-1], bins[k]).
        if "bins" in cfg:
            bins = cfg["bins"]
            img = img.updateMask(img.gte(bins[0]))

            if classify:
                classes = img.gte(bins[0])
                for edge in bins[1:]:
                    classes = classes.add(img.gte(edge))
                img = classes

        return img

    if layer_type == "threshold_binary":
        source_layer_id = cfg["source_layer"]
        source_cfg = get_layer_config(source_layer_id)

        if source_cfg is None:
            raise ValueError(f"Source layer not found: {source_layer_id}")

        # Skip the source's own mask_layer: a source masked by this layer
        # (prob_lgbm by peat_extent_mask) would otherwise recurse forever.
        source_img = get_layer_image(source_cfg, apply_mask_layer=False)

        threshold = cfg["threshold"]
        img = source_img.gte(threshold).selfMask()

        if cfg.get("exclude_landcover_mask", False):
            img = img.updateMask(_landcover_exclusion_mask())

        return img

    if layer_type == "nlcd_water":
        return (
            _nlcd_landcover()
            .eq(NLCD_WATER_CLASS)
            .selfMask()
            .updateMask(_tribal_mask())
            .updateMask(_domain_mask())
        )

    if layer_type == "tribal_outline":
        return _tribal_features().style(
            color=cfg.get("color", "555555"),
            width=cfg.get("width", 1),
            fillColor="00000000",
        )

    raise ValueError(f"Unsupported layer type: {layer_type}")


def public_layer_metadata():
    return {
        layer_id: {
            "name": cfg["name"],
            "type": cfg["type"],
            "unit": cfg.get("unit", ""),
            "vis": cfg["vis"],
            "legend_type": cfg.get("legend_type", "continuous"),
            "classes": cfg.get("classes", []),
            "clamp_max": cfg.get("clamp_max", False),
            "default_visible": cfg.get("default_visible", False),
            "opacity": cfg.get("opacity", 0.75),
            "pane": cfg.get("pane"),
        }
        for layer_id, cfg in LAYERS.items()
        if cfg.get("enabled", True) and cfg["type"] != "tribal_outline"
    }


def outline_layer_ids():
    """IDs of silent outline overlays: served to the frontend via /outlines,
    not listed in /layers (no legend, layer control entry, or click query)."""

    return [
        layer_id
        for layer_id, cfg in LAYERS.items()
        if cfg["type"] == "tribal_outline" and cfg.get("enabled", True)
    ]

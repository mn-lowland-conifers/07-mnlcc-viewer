import json
from pathlib import Path

import ee


LAYER_FILE = Path(__file__).parent / "layers.json"

# Used to auto-mask every gee_image layer (open water + developed/impervious +
# barren/extractive), by threshold_binary layers with "exclude_nlcd_water":
# true, and by the "nlcd_water" layer type.
NLCD_COLLECTION = "USGS/NLCD_RELEASES/2021_REL/NLCD"
NLCD_YEAR = "2021"
NLCD_WATER_CLASS = 11
# Developed, Open Space / Low / Medium / High Intensity.
NLCD_DEVELOPED_CLASSES = [21, 22, 23, 24]
# Barren Land (Rock/Sand/Clay) - includes strip mines, gravel pits, quarries.
NLCD_BARREN_CLASS = 31
NLCD_EXCLUDED_CLASSES = (
    [NLCD_WATER_CLASS] + NLCD_DEVELOPED_CLASSES + [NLCD_BARREN_CLASS]
)


def load_layers():
    with open(LAYER_FILE, "r") as f:
        return json.load(f)


LAYERS = load_layers()


def get_layer_config(layer_id: str):
    return LAYERS.get(layer_id)


def _apply_common_transforms(img, cfg):
    """Apply common masking and scaling operations to a GEE image."""

    img = img.updateMask(_nlcd_exclusion_mask())

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


def _nlcd_exclusion_mask():
    """Mask out USGS NLCD open water + developed/impervious pixels."""

    landcover = _nlcd_landcover()
    mask = landcover.neq(NLCD_EXCLUDED_CLASSES[0])

    for cls in NLCD_EXCLUDED_CLASSES[1:]:
        mask = mask.And(landcover.neq(cls))

    return mask


def get_layer_image(cfg):
    layer_type = cfg["type"]

    if layer_type == "gee_image":
        img = ee.Image(cfg["asset"])

        if "band" in cfg:
            img = img.select(cfg["band"])

        return _apply_common_transforms(img, cfg)

    if layer_type == "threshold_binary":
        source_layer_id = cfg["source_layer"]
        source_cfg = get_layer_config(source_layer_id)

        if source_cfg is None:
            raise ValueError(f"Source layer not found: {source_layer_id}")

        source_img = get_layer_image(source_cfg)

        threshold = cfg["threshold"]
        img = source_img.gte(threshold).selfMask()

        if cfg.get("exclude_nlcd_water", False):
            img = img.updateMask(_nlcd_exclusion_mask())

        return img

    if layer_type == "nlcd_water":
        return _nlcd_landcover().eq(NLCD_WATER_CLASS).selfMask()

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
        }
        for layer_id, cfg in LAYERS.items()
        if cfg.get("enabled", True)
    }

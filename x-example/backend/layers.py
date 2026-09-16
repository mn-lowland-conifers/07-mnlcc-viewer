import json
from pathlib import Path

import ee


LAYER_FILE = Path(__file__).parent / "layers.json"


def load_layers():
    with open(LAYER_FILE, "r") as f:
        return json.load(f)


LAYERS = load_layers()


def get_layer_config(layer_id: str):
    return LAYERS.get(layer_id)


def _apply_common_transforms(img, cfg):
    """Apply common masking and scaling operations to a GEE image."""

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

        return img

    if layer_type == "peat_pf_combo":
        peat_layer_id = cfg["peat_binary_layer"]
        pf_layer_id = cfg["pf_binary_layer"]

        peat_cfg = get_layer_config(peat_layer_id)
        pf_cfg = get_layer_config(pf_layer_id)

        if peat_cfg is None:
            raise ValueError(f"Peat binary layer not found: {peat_layer_id}")

        if pf_cfg is None:
            raise ValueError(f"PF binary layer not found: {pf_layer_id}")

        peat_binary = get_layer_image(peat_cfg)
        pf_binary = get_layer_image(pf_cfg)

        img = ee.Image(1).where(pf_binary.eq(1), 2)
        img = img.updateMask(peat_binary.eq(1))

        return img
        
    if layer_type == "soil_extent_mask":
        collection = ee.ImageCollection(cfg["collection"])

        granular_mask = (
            collection
            .filter(ee.Filter.eq("metric", cfg["mask_metric"]))
            .first()
        )

        dominant_soil_prob = (
            collection
            .filter(ee.Filter.eq("metric", cfg["probability_metric"]))
            .first()
        )

        img = (
            granular_mask
            .updateMask(dominant_soil_prob.gt(0))
            .selfMask()
        )

        return img

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
            "default_visible": cfg.get("default_visible", False),
            "opacity": cfg.get("opacity", 0.75),
        }
        for layer_id, cfg in LAYERS.items()
        if cfg.get("enabled", True)
    }
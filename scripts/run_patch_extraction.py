#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
HEATWISE LCZ pipeline glue for patch extraction.

Adapts the output STAC catalog produced by heatwise-hsi-lst-prep to the
STAC interface expected by heatwise-patch-extraction, adds the original
Sentinel-2 product, injects the dynamically staged label shapefile into the
patch-extraction configuration, and runs the upstream processor.

No scientific processing is implemented here.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_href(item_path: Path, href: str) -> Path:
    path = Path(href)

    if path.is_absolute():
        return path

    return (item_path.parent / path).resolve()


def find_prep_item(prep_dir: str | Path, city: str) -> tuple[Path, dict]:
    """
    Find the city Item in the STAC catalog produced by
    heatwise-hsi-lst-prep.
    """
    prep_dir = Path(prep_dir).resolve()
    catalog_path = prep_dir / "catalog.json"

    if not catalog_path.exists():
        raise SystemExit(
            f"[run_patch_extraction] Preprocessing STAC catalog not found: "
            f"{catalog_path}"
        )

    catalog = read_json(catalog_path)
    candidates = []

    for link in catalog.get("links", []):
        if link.get("rel") != "item" or not link.get("href"):
            continue

        item_path = Path(link["href"])

        if not item_path.is_absolute():
            item_path = (catalog_path.parent / item_path).resolve()

        item = read_json(item_path)
        assets = item.get("assets", {})

        if "hsi_bs" not in assets:
            continue

        candidates.append((item_path, item))

    if not candidates:
        raise SystemExit(
            "[run_patch_extraction] No preprocessing STAC Item contains "
            "the required `hsi_bs` asset."
        )

    city_lower = city.lower()

    for item_path, item in candidates:
        if str(item.get("id", "")).lower() == city_lower:
            return item_path, item

    if len(candidates) == 1:
        return candidates[0]

    raise SystemExit(
        f"[run_patch_extraction] Could not uniquely identify preprocessing "
        f"STAC Item for city {city!r}."
    )


def write_patch_input_catalog(
    prep_dir: str | Path,
    sentinel2: str | Path,
    city: str,
    catalog_dir: str | Path,
) -> Path:
    """
    Create the STAC adapter expected by heatwise-patch-extraction.

    heatwise-hsi-lst-prep exposes `hsi_bs` and optional `lst`, while
    heatwise-patch-extraction expects `hsi`, `sentinel2`, and optional `lst`.
    """
    item_path, item = find_prep_item(prep_dir, city)
    prep_assets = item.get("assets", {})

    hsi_path = resolve_href(
        item_path,
        prep_assets["hsi_bs"]["href"],
    )

    lst_path = None
    if "lst" in prep_assets:
        lst_path = resolve_href(
            item_path,
            prep_assets["lst"]["href"],
        )

    sentinel2 = Path(sentinel2).resolve()

    if not hsi_path.exists():
        raise SystemExit(
            f"[run_patch_extraction] HSI asset not found: {hsi_path}"
        )

    if not sentinel2.exists():
        raise SystemExit(
            f"[run_patch_extraction] Sentinel-2 asset not found: {sentinel2}"
        )

    if lst_path is not None and not lst_path.exists():
        raise SystemExit(
            f"[run_patch_extraction] LST asset not found: {lst_path}"
        )

    catalog_dir = Path(catalog_dir).resolve()
    catalog_dir.mkdir(parents=True, exist_ok=True)

    adapter_item_filename = f"{city}_pipeline_input_item.json"
    adapter_item_path = catalog_dir / adapter_item_filename
    catalog_path = catalog_dir / "catalog.json"

    assets = {
        "hsi": {
            "href": str(hsi_path),
            "type": "image/tiff; application=geotiff",
            "roles": ["data"],
        },
        "sentinel2": {
            "href": str(sentinel2),
            "type": "image/tiff; application=geotiff",
            "roles": ["data"],
        },
    }

    if lst_path is not None:
        assets["lst"] = {
            "href": str(lst_path),
            "type": "image/tiff; application=geotiff",
            "roles": ["data"],
        }

    adapter_item = {
        "type": "Feature",
        "stac_version": "1.0.0",
        "id": city,
        "properties": item.get("properties", {}),
        "geometry": item.get("geometry"),
        "links": [],
        "assets": assets,
    }

    adapter_catalog = {
        "type": "Catalog",
        "stac_version": "1.0.0",
        "id": "heatwise-patch-extraction-pipeline-input",
        "description": (
            "Adapted preprocessing products for HEATWISE patch extraction."
        ),
        "links": [
            {
                "rel": "item",
                "href": adapter_item_filename,
                "type": "application/geo+json",
            }
        ],
    }

    with adapter_item_path.open("w", encoding="utf-8") as f:
        json.dump(adapter_item, f, indent=2)

    with catalog_path.open("w", encoding="utf-8") as f:
        json.dump(adapter_catalog, f, indent=2)

    print(f"[run_patch_extraction] hsi={hsi_path}")
    print(f"[run_patch_extraction] sentinel2={sentinel2}")
    print(f"[run_patch_extraction] lst={lst_path}")
    print(f"[run_patch_extraction] Adapter STAC={catalog_path}")

    return catalog_path


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Adapt preprocessing STAC + labels and run "
            "heatwise-patch-extraction."
        )
    )

    parser.add_argument("--template", required=True)
    parser.add_argument("--prep-dir", required=True)
    parser.add_argument("--sentinel2", required=True)
    parser.add_argument("--labels-dir", required=True)
    parser.add_argument("--labels-basename", required=True)
    parser.add_argument("--output-h5", required=True)

    parser.add_argument(
        "--rendered-config",
        default="/tmp/patch_config_rendered.yaml",
    )
    parser.add_argument(
        "--input-catalog-dir",
        default="/tmp/patch_input_catalog",
    )
    parser.add_argument(
        "--processor",
        default="/app/processor.py",
    )

    args = parser.parse_args()

    with open(args.template, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    city = cfg["city"]

    labels_shp = Path(args.labels_dir) / f"{args.labels_basename}.shp"

    if not labels_shp.exists():
        raise SystemExit(
            f"[run_patch_extraction] Labels shapefile not found: "
            f"{labels_shp}"
        )

    cfg.setdefault("labels", {})["shp"] = str(labels_shp.resolve())

    os.makedirs(
        os.path.dirname(args.rendered_config) or ".",
        exist_ok=True,
    )

    with open(args.rendered_config, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)

    catalog_path = write_patch_input_catalog(
        prep_dir=args.prep_dir,
        sentinel2=args.sentinel2,
        city=city,
        catalog_dir=args.input_catalog_dir,
    )

    print(f"[run_patch_extraction] labels.shp={labels_shp}")
    print(
        f"[run_patch_extraction] Rendered config -> "
        f"{args.rendered_config}"
    )

    cmd = [
        "python",
        args.processor,
        "--config",
        args.rendered_config,
        "--input-catalog",
        str(catalog_path),
        "--output-h5",
        args.output_h5,
    ]

    print(f"[run_patch_extraction] Running: {' '.join(cmd)}")

    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()

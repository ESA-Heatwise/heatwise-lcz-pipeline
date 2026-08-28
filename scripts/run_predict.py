#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
HEATWISE LCZ pipeline glue for prediction.

Adapts the output STAC catalog produced by heatwise-hsi-lst-prep to the
STAC interface expected by heatwise-lcz-classification prediction, adds the
original Sentinel-2 product, selects the trained checkpoint corresponding to
the requested experiment, and runs the upstream prediction processor.

The upstream processor is responsible for generating the LCZ GeoTIFF,
optional preview PNG, and output STAC catalog.

No scientific processing is implemented here.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


LCZ_MAP_NAME = "lcz_map.tif"


def clean_name(value: str) -> str:
    """
    Match heatwise-lcz-classification training checkpoint naming.
    """
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_href(item_path: Path, href: str) -> Path:
    path = Path(href)

    if path.is_absolute():
        return path

    return (item_path.parent / path).resolve()


def find_prep_item(prep_dir: str | Path) -> tuple[Path, dict]:
    """
    Find the preprocessing STAC Item containing the `hsi_bs` product.

    The pipeline currently processes one city per run. Shared preprocessing
    Items without `hsi_bs` are ignored.
    """
    prep_dir = Path(prep_dir).resolve()
    catalog_path = prep_dir / "catalog.json"

    if not catalog_path.exists():
        raise SystemExit(
            f"[run_predict] Preprocessing STAC catalog not found: "
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

        if "hsi_bs" in assets:
            candidates.append((item_path, item))

    if not candidates:
        raise SystemExit(
            "[run_predict] No preprocessing STAC Item contains "
            "the required `hsi_bs` asset."
        )

    if len(candidates) > 1:
        ids = [str(item.get("id", path.stem)) for path, item in candidates]
        raise SystemExit(
            "[run_predict] Multiple preprocessing Items contain `hsi_bs`; "
            f"the pipeline expects one city per run. Candidates: {ids}"
        )

    return candidates[0]


def write_prediction_input_catalog(
    prep_dir: str | Path,
    sentinel2: str | Path,
    catalog_dir: str | Path,
) -> Path:
    """
    Create the STAC adapter expected by LCZ prediction.

    heatwise-hsi-lst-prep exposes `hsi_bs` and optional `lst`, while
    heatwise-lcz-classification prediction expects `hsi`, `sentinel2`,
    and optional `lst`.
    """
    item_path, item = find_prep_item(prep_dir)
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
            f"[run_predict] HSI asset not found: {hsi_path}"
        )

    if not sentinel2.exists():
        raise SystemExit(
            f"[run_predict] Sentinel-2 asset not found: {sentinel2}"
        )

    if lst_path is not None and not lst_path.exists():
        raise SystemExit(
            f"[run_predict] LST asset not found: {lst_path}"
        )

    catalog_dir = Path(catalog_dir).resolve()
    catalog_dir.mkdir(parents=True, exist_ok=True)

    item_id = str(item.get("id", "pipeline-prediction-input"))
    item_filename = f"{item_id}_prediction_input_item.json"
    adapter_item_path = catalog_dir / item_filename
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
        "id": item_id,
        "properties": item.get("properties", {}),
        "geometry": item.get("geometry"),
        "links": [],
        "assets": assets,
    }

    adapter_catalog = {
        "type": "Catalog",
        "stac_version": "1.0.0",
        "id": "heatwise-lcz-prediction-pipeline-input",
        "description": (
            "Adapted preprocessing products for HEATWISE LCZ prediction."
        ),
        "links": [
            {
                "rel": "item",
                "href": item_filename,
                "type": "application/geo+json",
            }
        ],
    }

    with adapter_item_path.open("w", encoding="utf-8") as f:
        json.dump(adapter_item, f, indent=2)

    with catalog_path.open("w", encoding="utf-8") as f:
        json.dump(adapter_catalog, f, indent=2)

    print(f"[run_predict] hsi={hsi_path}")
    print(f"[run_predict] sentinel2={sentinel2}")
    print(f"[run_predict] lst={lst_path}")
    print(f"[run_predict] Adapter STAC={catalog_path}")

    return catalog_path


def find_checkpoint(
    train_dir: str | Path,
    experiment_name: str,
) -> Path:
    """
    Locate best_model_<experiment>.pth in the training output directory.
    """
    train_dir = Path(train_dir).resolve()
    experiment = clean_name(experiment_name)

    matches = sorted(
        train_dir.rglob(f"best_model_{experiment}.pth")
    )

    if not matches:
        raise SystemExit(
            f"[run_predict] No checkpoint found for experiment "
            f"{experiment_name!r} under {train_dir}"
        )

    if len(matches) > 1:
        print(
            "[run_predict] Warning: multiple matching checkpoints found; "
            f"using {matches[0]}"
        )

    return matches[0]


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Adapt preprocessing STAC, select trained checkpoint, "
            "and run HEATWISE LCZ prediction."
        )
    )

    parser.add_argument(
        "--template",
        required=True,
        help="Prediction configuration containing inference/model parameters.",
    )

    parser.add_argument(
        "--prep-dir",
        required=True,
        help="heatwise-hsi-lst-prep output directory.",
    )

    parser.add_argument(
        "--sentinel2",
        required=True,
        help="Original Sentinel-2 raster.",
    )

    parser.add_argument(
        "--train-dir",
        required=True,
        help="heatwise-lcz-classification training output directory.",
    )

    parser.add_argument(
        "--experiment-name",
        required=True,
        help="Training experiment whose best_model checkpoint should be used.",
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory receiving the LCZ prediction products.",
    )

    parser.add_argument(
        "--input-catalog-dir",
        default="/tmp/predict_input_catalog",
    )

    parser.add_argument(
        "--processor",
        default="/app/processor.py",
    )

    args = parser.parse_args()

    catalog_path = write_prediction_input_catalog(
        prep_dir=args.prep_dir,
        sentinel2=args.sentinel2,
        catalog_dir=args.input_catalog_dir,
    )

    checkpoint = find_checkpoint(
        train_dir=args.train_dir,
        experiment_name=args.experiment_name,
    )

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    lcz_map_path = output_dir / LCZ_MAP_NAME

    print(f"[run_predict] weights={checkpoint}")
    print(f"[run_predict] output={lcz_map_path}")

    cmd = [
        "python",
        args.processor,
        "predict",
        "--config",
        args.template,
        "--input-catalog",
        str(catalog_path),
        "--weights",
        str(checkpoint),
        "--output",
        str(lcz_map_path),
    ]

    print(f"[run_predict] Running: {' '.join(cmd)}")

    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()

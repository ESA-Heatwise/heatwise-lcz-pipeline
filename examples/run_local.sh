#!/usr/bin/env bash
# Local (no Docker/CWL) smoke test of the full HEATWISE LCZ pipeline.
#
# This exercises the same EOAP-oriented processor interfaces used by the
# CWL workflow, but runs the Python processors directly from local checkouts.
#
# Prerequisites:
#   - the three processor repos checked out with their environments installed
#     (override their locations via PREP_REPO / PATCH_REPO / LCZ_REPO);
#   - Python dependencies required by the processors;
#   - pyyaml for the pipeline glue scripts.
#
# Usage (from the repo root):
#   bash examples/run_local.sh
#
# Everything is written under output/ (gitignored).
# For the full containerized CWL integration test, run:
#
#   cwltool --outdir cwl-output heatwise_pipeline.cwl examples/job.yaml

set -euo pipefail

cd "$(dirname "$0")/.."

PREP_REPO="${PREP_REPO:-../heatwise-hsi-lst-prep}"
PATCH_REPO="${PATCH_REPO:-../heatwise-patch-extraction}"
LCZ_REPO="${LCZ_REPO:-../heatwise-lcz-classification}"

EXPERIMENT="${EXPERIMENT:-HSI-BS}"
OUT="${OUT:-output}"

for repo in "$PREP_REPO" "$PATCH_REPO" "$LCZ_REPO"; do
    if [ ! -f "$repo/processor.py" ]; then
        echo "ERROR: processor repo not found at '$repo'" >&2
        echo "Set PREP_REPO, PATCH_REPO, and LCZ_REPO as needed." >&2
        exit 1
    fi
done

mkdir -p "$OUT"

echo "== 1/4 prep: heatwise-hsi-lst-prep =="

python "$PREP_REPO/processor.py" run-all \
    --config "$PREP_REPO/examples/run_all_config.yaml" \
    --input-catalog data/Berlin_prep/catalog.json \
    --output-dir "$OUT/prep"


echo "== 2/4 extract patches: STAC adapter + processor =="

python scripts/run_patch_extraction.py \
    --template examples/patch_config_template.yaml \
    --prep-dir "$OUT/prep" \
    --sentinel2 data/Berlin_prep/Berlin_S2.tif \
    --labels-dir data/Berlin_labels \
    --labels-basename Berlin_labels \
    --output-h5 "$OUT/patches.h5" \
    --rendered-config "$OUT/patch_config_rendered.yaml" \
    --processor "$PATCH_REPO/processor.py"


echo "== 3/4 train: heatwise-lcz-classification =="

python "$LCZ_REPO/processor.py" train \
    --input-catalog "$OUT/catalog.json" \
    --config examples/train_config_sample.yaml \
    --output-dir "$OUT/train"


echo "== 4/4 predict: STAC adapter + processor =="

python scripts/run_predict.py \
    --template examples/predict_config_template.yaml \
    --prep-dir "$OUT/prep" \
    --sentinel2 data/Berlin_prep/Berlin_S2.tif \
    --train-dir "$OUT/train" \
    --experiment-name "$EXPERIMENT" \
    --output-dir "$OUT/predict" \
    --rendered-config "$OUT/predict_config_rendered.yaml" \
    --processor "$LCZ_REPO/processor.py"


echo
echo "Done."
echo
echo "Patch product:"
echo "  $OUT/patches.h5"
echo
echo "Training products:"
echo "  $OUT/train/"
echo
echo "Final prediction products:"
echo "  $OUT/predict/"

ls -la "$OUT/predict"

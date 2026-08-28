cwlVersion: v1.2

$namespaces:
  s: https://schema.org/

s:softwareVersion: 0.1.1
s:version: 0.1.1

schemas:
  - http://schema.org/version/9.0/schemaorg-current-http.rdf

class: Workflow
id: main

label: HEATWISE LCZ Full Pipeline
doc: |
  EOAP-compatible end-to-end HEATWISE LCZ workflow.

  The workflow chains the HEATWISE processors for hyperspectral/LST
  preprocessing, geographically isolated patch extraction, LCZ model
  training, and whole-scene LCZ prediction:

      heatwise-hsi-lst-prep
              ↓
      heatwise-patch-extraction
              ↓
      heatwise-lcz-classification train
              ↓
      heatwise-lcz-classification predict

  EO products are exchanged between processing stages through STAC-enabled
  directories. Internal pipeline adapters are used only where interface
  adaptation is required, such as adding the original Sentinel-2 product,
  injecting dynamically staged LCZ labels, or selecting a trained model
  checkpoint.

  The scientific processing logic remains implemented by the upstream
  HEATWISE processor images.

requirements: []

inputs:

  - id: prep_config
    type: File
    label: preprocessing configuration
    doc: |
      Run-level YAML configuration controlling the HSI/LST preprocessing
      stage.

  - id: prep_input_catalog
    type: Directory
    label: preprocessing input STAC catalog
    doc: |
      Directory containing catalog.json, STAC Items, and the staged EO
      products required by heatwise-hsi-lst-prep.

  - id: sentinel2
    type: File
    label: Sentinel-2 raster
    doc: |
      Original Sentinel-2 raster. The preprocessing stage uses the copy
      referenced by the input STAC catalog, while this explicit File input
      is also supplied to the patch-extraction and prediction adapters.

  - id: patch_config_template
    type: File
    label: patch extraction configuration
    doc: |
      Patch-extraction YAML configuration containing the scientific
      processing parameters. The dynamically staged labels.shp path is
      injected by the pipeline adapter.

  - id: labels_dir
    type: Directory
    label: LCZ labels directory
    doc: |
      Directory containing the LCZ label shapefile and its associated
      sidecar files.

  - id: labels_basename
    type: string
    label: labels basename
    doc: |
      Basename of the label shapefile without the .shp extension.

  - id: train_config
    type: File
    label: LCZ training configuration
    doc: |
      YAML configuration defining LCZ_HMSSNet training parameters and
      modality experiments.

  - id: predict_config_template
    type: File
    label: LCZ prediction configuration
    doc: |
      Prediction YAML configuration containing inference and model
      parameters. EO raster paths and model weights are supplied separately
      by the pipeline adapter.

  - id: experiment_name
    type: string
    label: experiment name
    default: HSI-BS
    doc: |
      Name of the training experiment whose best_model_<experiment>.pth
      checkpoint is used for whole-scene prediction.

steps:

  prep:
    run: tools/hsi_lst_prep.cwl

    in:
      config: prep_config
      input_catalog: prep_input_catalog
      output_dir:
        default: "."

    out:
      - output

  extract_patches:
    run: tools/extract_patches_pipeline.cwl

    in:
      template: patch_config_template
      prep_dir: prep/output
      sentinel2: sentinel2
      labels_dir: labels_dir
      labels_basename: labels_basename
      output_h5_name:
        default: patches.h5

    out:
      - output

  train:
    run: tools/lcz_train.cwl

    in:
      input_catalog: extract_patches/output
      config: train_config
      output_dir:
        default: "."

    out:
      - output

  predict:
    run: tools/predict_pipeline.cwl

    in:
      template: predict_config_template
      prep_dir: prep/output
      sentinel2: sentinel2
      train_dir: train/output
      experiment_name: experiment_name
      output_dir_name:
        default: "."

    out:
      - output

outputs:

  - id: prep_output
    type: Directory
    label: preprocessing output
    doc: |
      Complete STAC-enabled output directory produced by the preprocessing
      stage.
    outputSource: prep/output

  - id: patch_output
    type: Directory
    label: patch extraction output
    doc: |
      Complete patch-extraction output directory containing the HDF5 patch
      dataset and its STAC catalog.
    outputSource: extract_patches/output

  - id: train_output
    type: Directory
    label: training output
    doc: |
      Complete LCZ training output directory containing model checkpoints,
      evaluation artifacts, and the training STAC catalog.
    outputSource: train/output

  - id: output
    type: Directory
    label: final LCZ prediction output
    doc: |
      Final pipeline output directory containing the LCZ classification
      GeoTIFF, optional preview PNG, and the prediction STAC catalog.
    outputSource: predict/output

cwlVersion: v1.2
class: CommandLineTool

label: HEATWISE HSI/LST Preprocessing
doc: |
  Vendored HEATWISE HSI/LST preprocessing tool used by the LCZ pipeline.

  EO inputs are supplied through a staged STAC Directory containing
  catalog.json, STAC Items, and their referenced assets.

  The processor writes the preprocessing products and an output STAC catalog
  to the CWL working directory.

requirements:

  DockerRequirement:
    dockerPull: ghcr.io/esa-heatwise/heatwise-hsi-lst-prep:eoap-compliance

  InlineJavascriptRequirement: {}

baseCommand: python

arguments:
  - /app/processor.py
  - run-all

inputs:

  config:
    type: File
    label: processing configuration
    doc: |
      Run-level YAML configuration controlling HSI/LST preprocessing.
    inputBinding:
      prefix: --config

  input_catalog:
    type: Directory
    label: input STAC catalog
    doc: |
      Directory containing catalog.json and the associated STAC Items and
      EO assets required by the preprocessing workflow.
    inputBinding:
      prefix: --input-catalog
      valueFrom: $(self.path + "/catalog.json")

  output_dir:
    type: string
    label: output directory
    default: "."
    doc: |
      Output directory path relative to the CWL working directory.
    inputBinding:
      prefix: --output-dir

outputs:

  output:
    type: Directory
    doc: |
      Complete preprocessing working directory, including the generated
      raster products, STAC Items, and catalog.json.
    outputBinding:
      glob: "."

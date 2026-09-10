# Thin pipeline adapter image for heatwise-patch-extraction.
#
# The scientific processor is provided by the EOAP-compliant upstream image.
# This derived image only adds the pipeline glue script that adapts the
# preprocessing STAC output, Sentinel-2 input, and dynamically staged labels
# to the patch-extraction interface.
#
# The upstream EOAP image uses CMD rather than ENTRYPOINT, so CWL can invoke
# /app/run_patch_extraction.py explicitly without clearing an ENTRYPOINT.
#
# This eoap-compliance base tag is temporary for integration testing. Once
# the upstream EOAP changes are merged and a stable image is published, this
# reference can be switched back to the corresponding versioned release tag.

FROM ghcr.io/esa-heatwise/heatwise-patch-extraction:eoap-compliance

COPY scripts/run_patch_extraction.py /app/run_patch_extraction.py

CMD ["python", "/app/run_patch_extraction.py", "--help"]

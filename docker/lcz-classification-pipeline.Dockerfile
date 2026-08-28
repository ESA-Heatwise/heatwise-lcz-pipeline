# Thin pipeline adapter image for heatwise-lcz-classification prediction.
#
# The scientific processor is provided by the EOAP-compliant upstream image.
# This derived image only adds the pipeline glue script that adapts the
# preprocessing STAC output, selects the requested trained checkpoint, and
# invokes the prediction interface.
#
# The upstream EOAP image uses CMD rather than ENTRYPOINT, so CWL can invoke
# /app/run_predict.py explicitly without clearing an ENTRYPOINT.
#
# This eoap-compliance base tag is temporary for integration testing. Once
# the upstream EOAP changes are merged and a stable image is published, this
# reference can be switched back to the corresponding versioned release tag.

FROM ghcr.io/esa-heatwise/heatwise-lcz-classification:eoap-compliance

COPY scripts/run_predict.py /app/run_predict.py

CMD ["python", "/app/run_predict.py", "--help"]

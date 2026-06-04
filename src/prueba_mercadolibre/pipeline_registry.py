"""Project pipelines."""

from kedro.framework.project import find_pipelines
from kedro.pipeline import Pipeline


def register_pipelines() -> dict[str, Pipeline]:
    """Register the project's pipelines.

    - ``__default__`` (kedro run): proceso COMPLETO SIN la ingesta
      (data_processing + risk_scoring). Lee los raw que ya están en BigQuery.
    - ``ingest`` (kedro run --pipeline=ingest): sube los CSV locales a BigQuery.
    - ``full`` (kedro run --pipeline=full): ingesta + proceso completo.
    """
    pipelines = find_pipelines(raise_errors=True)

    # Sacar la ingesta del default → kedro run NO la ejecuta
    ingest = pipelines.pop("ingest", Pipeline([]))
    default = sum(pipelines.values())  # data_processing + risk_scoring

    return {
        **pipelines,
        "ingest": ingest,
        "__default__": default,
        "full": ingest + default,
    }

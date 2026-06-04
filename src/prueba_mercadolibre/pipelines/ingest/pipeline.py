from kedro.pipeline import Pipeline, node

from .nodes import passthrough


def create_pipeline(**kwargs) -> Pipeline:
    """Sube los 3 raw locales (CSV) a BigQuery.

    Input:  *_local (CSVDataset, data/01_raw/)
    Output: user_inventory / permission_inventory / access_logs (GBQTableDataset → l1_*)
    """
    return Pipeline(
        [
            node(
                func=passthrough,
                inputs="user_inventory_local",
                outputs="user_inventory",
                name="ingest_user_inventory_node",
                tags=["ingest"],
            ),
            node(
                func=passthrough,
                inputs="permission_inventory_local",
                outputs="permission_inventory",
                name="ingest_permission_inventory_node",
                tags=["ingest"],
            ),
            node(
                func=passthrough,
                inputs="access_logs_local",
                outputs="access_logs",
                name="ingest_access_logs_node",
                tags=["ingest"],
            ),
        ]
    )

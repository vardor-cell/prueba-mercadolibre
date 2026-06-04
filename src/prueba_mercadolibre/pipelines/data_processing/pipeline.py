"""Definición del pipeline data_processing (limpieza de los 3 datasets raw)."""
from kedro.pipeline import Pipeline, node

from .nodes import clean_access_logs, clean_permission_inventory, clean_user_inventory


def create_pipeline(**kwargs) -> Pipeline:
    """Arma el pipeline de limpieza: un nodo por dataset raw (users, perms, logs),
    cada uno con el tag ``preprocess``. Lee de l1 y escribe l2 en BigQuery."""
    return Pipeline(
        [
            node(
                func=clean_user_inventory,
                inputs="user_inventory",
                outputs="users_clean",
                name="clean_user_inventory_node",
                tags=["preprocess"],
            ),
            node(
                func=clean_permission_inventory,
                inputs="permission_inventory",
                outputs="perms_clean",
                name="clean_permission_inventory_node",
                tags=["preprocess"],
            ),
            node(
                func=clean_access_logs,
                inputs="access_logs",
                outputs="logs_clean",
                name="clean_access_logs_node",
                tags=["preprocess"],
            ),
        ]
    )

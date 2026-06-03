from kedro.pipeline import Pipeline, node

from .nodes import clean_access_logs, clean_permission_inventory, clean_user_inventory


def create_pipeline(**kwargs) -> Pipeline:
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

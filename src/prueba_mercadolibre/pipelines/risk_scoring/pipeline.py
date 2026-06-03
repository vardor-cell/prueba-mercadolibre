from kedro.pipeline import Pipeline, node

from .nodes import (
    build_feature_matrix,
    combine_and_categorize,
    compute_hard_rule_scores,
    compute_impact_factor,
    score_anomaly_ensemble,
    train_anomaly_ensemble,
)


def create_pipeline(**kwargs) -> Pipeline:
    return Pipeline(
        [
            node(
                func=build_feature_matrix,
                inputs=["users_clean", "perms_clean", "logs_clean"],
                outputs="user_features",
                name="build_feature_matrix_node",
                tags=["train", "score"],
            ),
            node(
                func=compute_hard_rule_scores,
                inputs=[
                    "users_clean",
                    "perms_clean",
                    "logs_clean",
                    "params:risk_scoring",
                ],
                outputs="hard_rule_scores",
                name="compute_hard_rule_scores_node",
                tags=["train", "score"],
            ),
            node(
                func=train_anomaly_ensemble,
                inputs=["user_features", "params:risk_scoring"],
                outputs="anomaly_model",
                name="train_anomaly_ensemble_node",
                tags=["train"],
            ),
            node(
                func=score_anomaly_ensemble,
                inputs=["user_features", "anomaly_model", "params:risk_scoring"],
                outputs="anomaly_scores",
                name="score_anomaly_ensemble_node",
                tags=["score"],
            ),
            node(
                func=compute_impact_factor,
                inputs=["user_features", "perms_clean", "params:risk_scoring"],
                outputs="impact_scores",
                name="compute_impact_factor_node",
                tags=["score"],
            ),
            node(
                func=combine_and_categorize,
                inputs=[
                    "users_clean",
                    "user_features",
                    "hard_rule_scores",
                    "anomaly_scores",
                    "impact_scores",
                    "params:risk_scoring",
                ],
                outputs="risk_scores",
                name="combine_and_categorize_node",
                tags=["score"],
            ),
        ]
    )

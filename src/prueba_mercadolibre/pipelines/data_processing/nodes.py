"""Data processing pipeline nodes.

Cleans the three raw datasets and writes them to 02_intermediate.
Rules:
- Parse and standardize all date columns.
- Strip whitespace from categorical string fields.
- Validate domain values; drop rows with unrecognized values and log the count.
- Cap session_duration_sec outliers at p99 to prevent IF feature distortion.
- Add lightweight quality flags used later by scoring rules.
"""
import logging

import pandas as pd

log = logging.getLogger(__name__)

_VALID_USER_TYPES = {"Internal", "External"}
_VALID_STATUSES   = {"Active", "Inactive"}
_VALID_CRITICALITIES = {"LOW", "MEDIUM", "HIGH", "VERY_HIGH"}
_VALID_ACTIONS = {"READ", "WRITE", "DELETE", "EXPORT", "LOGIN", "QUERY"}
_VALID_RESOURCE_TYPES = {
    "admin_panel", "payment_portal", "vdi", "database",
    "api_internal", "drive", "email_system", "reporting_tool",
}

CRIT_ORDER = pd.CategoricalDtype(
    categories=["LOW", "MEDIUM", "HIGH", "VERY_HIGH"], ordered=True
)


def _strip_str_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Quita espacios en blanco de todas las columnas de texto (in place)."""
    str_cols = df.select_dtypes("object").columns
    df[str_cols] = df[str_cols].apply(lambda s: s.str.strip())
    return df


def clean_user_inventory(user_inventory: pd.DataFrame) -> pd.DataFrame:
    """Clean user_inventory → 02_intermediate/users_clean.csv"""
    df = _strip_str_columns(user_inventory.copy())
    original_len = len(df)

    # Parse dates
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")

    # Drop rows with invalid domain values
    bad_type   = ~df["user_type"].isin(_VALID_USER_TYPES)
    bad_status = ~df["status"].isin(_VALID_STATUSES)
    bad_rows   = bad_type | bad_status
    if bad_rows.any():
        log.warning(
            "user_inventory: dropping %d rows with invalid user_type/status",
            bad_rows.sum(),
        )
        df = df[~bad_rows].copy()

    # Flag accounts without a manager (used for governance analysis)
    df["has_manager"] = df["manager_id"].notna().astype(int)

    log.info(
        "users_clean: %d → %d rows (dropped %d invalid)",
        original_len, len(df), original_len - len(df),
    )
    return df.reset_index(drop=True)


def clean_permission_inventory(permission_inventory: pd.DataFrame) -> pd.DataFrame:
    """Clean permission_inventory → 02_intermediate/perms_clean.csv"""
    df = _strip_str_columns(permission_inventory.copy())
    original_len = len(df)

    # Parse dates
    df["assigned_at"] = pd.to_datetime(df["assigned_at"], errors="coerce")
    df["expires_at"]  = pd.to_datetime(df["expires_at"],  errors="coerce")

    # Drop rows with invalid criticality
    bad_crit = ~df["criticality"].isin(_VALID_CRITICALITIES)
    if bad_crit.any():
        log.warning(
            "permission_inventory: dropping %d rows with invalid criticality",
            bad_crit.sum(),
        )
        df = df[~bad_crit].copy()

    # Drop rows where expiry precedes assignment (data inconsistency)
    bad_dates = (
        df["expires_at"].notna()
        & df["assigned_at"].notna()
        & (df["expires_at"] < df["assigned_at"])
    )
    if bad_dates.any():
        log.warning(
            "permission_inventory: dropping %d rows where expires_at < assigned_at",
            bad_dates.sum(),
        )
        df = df[~bad_dates].copy()

    # Ordered categorical for criticality
    df["criticality"] = df["criticality"].astype(CRIT_ORDER)

    # Quality flags used downstream
    df["has_expiry"]   = df["expires_at"].notna().astype(int)

    log.info(
        "perms_clean: %d → %d rows (dropped %d invalid)",
        original_len, len(df), original_len - len(df),
    )
    return df.reset_index(drop=True)


def clean_access_logs(access_logs: pd.DataFrame) -> pd.DataFrame:
    """Clean access_logs → 02_intermediate/logs_clean.csv"""
    df = _strip_str_columns(access_logs.copy())
    original_len = len(df)

    # Parse timestamp
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    # Drop rows with unparseable timestamps
    bad_ts = df["timestamp"].isna()
    if bad_ts.any():
        log.warning("access_logs: dropping %d rows with invalid timestamp", bad_ts.sum())
        df = df[~bad_ts].copy()

    # Drop rows with invalid action or resource_type
    bad_action = ~df["action"].isin(_VALID_ACTIONS)
    bad_rtype  = ~df["resource_type"].isin(_VALID_RESOURCE_TYPES)
    bad_rows   = bad_action | bad_rtype
    if bad_rows.any():
        log.warning(
            "access_logs: dropping %d rows with invalid action/resource_type",
            bad_rows.sum(),
        )
        df = df[~bad_rows].copy()

    # Cap session_duration_sec at p99 to prevent outlier distortion in IF features
    p99 = df["session_duration_sec"].quantile(0.99)
    outliers = (df["session_duration_sec"] > p99).sum()
    if outliers > 0:
        log.info(
            "access_logs: capping %d session_duration_sec outliers at p99=%.0fs",
            outliers, p99,
        )
        df["session_duration_sec"] = df["session_duration_sec"].clip(upper=p99)

    log.info(
        "logs_clean: %d → %d rows (dropped %d invalid, capped %d outliers)",
        original_len, len(df), original_len - len(df), outliers,
    )
    return df.reset_index(drop=True)

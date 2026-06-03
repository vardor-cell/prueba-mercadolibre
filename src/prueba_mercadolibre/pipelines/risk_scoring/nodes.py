"""Risk scoring pipeline nodes — two-layer UEBA model.

Layer 1: Hard rules (deterministic, 0-60 pts)
Layer 2: Unsupervised anomaly ENSEMBLE (0-40 pts) — three independent detectors:
         - Isolation Forest (partition-based)
         - Local Outlier Factor (density-based)
         - Z-score sum (parametric distance)
         Final anomaly score = weighted average of the three, scaled to [0, anomaly_max].
Final score: clip(rule_score + anomaly_score, 0, 100)
"""
import json
import math
from collections import Counter

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

CRITICALITY_NUM = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "VERY_HIGH": 4}

FEATURE_COLS = [
    "total_accesses",
    "z_volume_peers",
    "distinct_resources",
    "z_distinct_peers",
    "exfil_ratio",
    "z_exfil_peers",
    "action_entropy",
    "after_hours_ratio",
    "weekend_ratio",
    "avg_session_sec",
    "perm_count",
    "z_perms_peers",
    "max_crit_accessed",
    "very_high_access_ratio",
    "high_plus_access_ratio",
    "delete_ratio",
    "is_external",
]

FEATURE_SIGNAL_LABELS = {
    "total_accesses":         "ML: anomalously high access volume",
    "z_volume_peers":         "ML: access volume anomalous vs peer group",
    "distinct_resources":     "ML: accesses unusually many distinct resources",
    "z_distinct_peers":       "ML: distinct resource count anomalous vs peers (lateral movement signal)",
    "exfil_ratio":            "ML: elevated exfiltration action ratio (EXPORT/QUERY)",
    "z_exfil_peers":          "ML: exfil ratio anomalous vs peer group",
    "action_entropy":         "ML: anomalous action diversity pattern",
    "after_hours_ratio":      "ML: elevated after-hours access ratio (00-05h)",
    "weekend_ratio":          "ML: elevated weekend access ratio",
    "avg_session_sec":        "ML: anomalous session duration",
    "perm_count":             "ML: anomalous number of permissions assigned",
    "z_perms_peers":          "ML: permission count anomalous vs peers (privilege bloat)",
    "max_crit_accessed":      "ML: accessing very high-criticality resources",
    "very_high_access_ratio": "ML: high proportion of VERY_HIGH resource accesses",
    "high_plus_access_ratio": "ML: high proportion of HIGH+ criticality resource accesses",
    "delete_ratio":           "ML: elevated delete action ratio",
    "is_external":            "ML: external user with anomalous overall profile",
}


def _minmax(v: np.ndarray) -> np.ndarray:
    """Min-max normalize to [0, 1]; returns zeros if the range is degenerate."""
    rng = v.max() - v.min()
    return np.zeros_like(v) if rng == 0 else (v - v.min()) / rng


def _z_score_within_group(
    df: pd.DataFrame, value_col: str, group_cols: list
) -> pd.Series:
    """Z-score of value_col relative to peers in group_cols. Uses ddof=0 to avoid
    NaN for single-member or two-member groups."""
    def _z(grp):
        std = grp[value_col].std(ddof=0)
        if std == 0 or pd.isna(std):
            return pd.Series(0.0, index=grp.index)
        return (grp[value_col] - grp[value_col].mean()) / std

    return df.groupby(group_cols, group_keys=False).apply(_z)


def _shannon_entropy(actions: list) -> float:
    """Shannon entropy (base 2) of a list of action labels."""
    if not actions:
        return 0.0
    cnt = Counter(actions)
    total = len(actions)
    return -sum((c / total) * math.log2(c / total) for c in cnt.values())


# ── Node 1 ────────────────────────────────────────────────────────────────────

def build_feature_matrix(
    user_inventory: pd.DataFrame,
    permission_inventory: pd.DataFrame,
    access_logs: pd.DataFrame,
) -> pd.DataFrame:
    """Build per-user numeric feature matrix for the Isolation Forest."""
    users = user_inventory.copy()
    perms = permission_inventory.copy()
    logs = access_logs.copy()

    logs["timestamp"] = pd.to_datetime(logs["timestamp"])
    logs["hour"] = logs["timestamp"].dt.hour
    logs["dayofweek"] = logs["timestamp"].dt.dayofweek  # 0=Mon, 6=Sun

    # Resource → criticality_num lookup (take max criticality if a resource
    # appears with different criticality levels across permissions)
    res_crit = (
        perms.assign(crit_num=perms["criticality"].astype(str).map(CRITICALITY_NUM))
        .groupby("resource_id")["crit_num"]
        .max()
    )
    logs["crit_num"] = logs["resource_id"].map(res_crit).fillna(0)

    # ── Access-log aggregates per user ────────────────────────────────────────
    grp = logs.groupby("user_id")

    total_acc = grp.size().rename("total_accesses")
    distinct_res = grp["resource_id"].nunique().rename("distinct_resources")
    avg_session = grp["session_duration_sec"].mean().rename("avg_session_sec")

    # Ratio features (safe division: users with 0 accesses get 0)
    exfil = (
        grp["action"].apply(lambda s: (s.isin(["EXPORT", "QUERY"])).sum())
        / total_acc
    ).rename("exfil_ratio").fillna(0)

    after_hours = (
        grp["hour"].apply(lambda s: (s < 6).sum()) / total_acc
    ).rename("after_hours_ratio").fillna(0)

    weekend = (
        grp["dayofweek"].apply(lambda s: (s >= 5).sum()) / total_acc
    ).rename("weekend_ratio").fillna(0)

    delete_r = (
        grp["action"].apply(lambda s: (s == "DELETE").sum()) / total_acc
    ).rename("delete_ratio").fillna(0)

    max_crit = grp["crit_num"].max().rename("max_crit_accessed").fillna(0)

    vh_ratio = (
        grp["crit_num"].apply(lambda s: (s == 4).sum()) / total_acc
    ).rename("very_high_access_ratio").fillna(0)

    hp_ratio = (
        grp["crit_num"].apply(lambda s: (s >= 3).sum()) / total_acc
    ).rename("high_plus_access_ratio").fillna(0)

    entropy = (
        grp["action"].apply(lambda s: _shannon_entropy(s.tolist()))
        .rename("action_entropy")
    )

    # ── Permission aggregates ─────────────────────────────────────────────────
    perm_count = perms.groupby("user_id").size().rename("perm_count")

    # ── Assemble per-user frame ───────────────────────────────────────────────
    feat = users[["user_id", "department", "role", "user_type"]].copy()
    feat["is_external"] = (feat["user_type"] == "External").astype(int)

    for series in [
        total_acc, distinct_res, avg_session, exfil, after_hours,
        weekend, delete_r, max_crit, vh_ratio, hp_ratio, entropy, perm_count,
    ]:
        feat = feat.merge(series.reset_index(), on="user_id", how="left")

    feat = feat.fillna(0)

    # ── Peer-group z-scores ───────────────────────────────────────────────────
    group_cols = ["department", "role"]
    for src, dst in [
        ("total_accesses",   "z_volume_peers"),
        ("distinct_resources", "z_distinct_peers"),
        ("exfil_ratio",      "z_exfil_peers"),
        ("perm_count",       "z_perms_peers"),
    ]:
        feat[dst] = _z_score_within_group(feat, src, group_cols).values

    return feat[["user_id"] + FEATURE_COLS]


# ── Node 2 ────────────────────────────────────────────────────────────────────

def compute_hard_rule_scores(
    user_inventory: pd.DataFrame,
    permission_inventory: pd.DataFrame,
    access_logs: pd.DataFrame,
    params: dict,
) -> pd.DataFrame:
    """Evaluate seven deterministic rules and produce a rule score per user."""
    weights = params["rule_weights"]

    users = user_inventory.copy()
    perms = permission_inventory.copy()
    logs = access_logs.copy()

    perms["expires_at_dt"] = pd.to_datetime(perms["expires_at"], errors="coerce")
    logs["timestamp_dt"] = pd.to_datetime(logs["timestamp"])

    user_status = users.set_index("user_id")["status"].to_dict()
    user_type   = users.set_index("user_id")["user_type"].to_dict()
    user_dept   = users.set_index("user_id")["department"].to_dict()

    # Resource criticality num
    res_crit_num = (
        perms.assign(crit_num=perms["criticality"].astype(str).map(CRITICALITY_NUM))
        .groupby("resource_id")["crit_num"]
        .max()
        .to_dict()
    )

    # Pre-built lookup structures
    user_perm_resources = (
        perms.groupby("user_id")["resource_id"].apply(set).to_dict()
    )
    user_max_perm_crit = (
        perms.assign(crit_num=perms["criticality"].astype(str).map(CRITICALITY_NUM))
        .groupby("user_id")["crit_num"]
        .max()
        .to_dict()
    )

    # (user_id, resource_id) → list of expires_at_dt values
    perm_expires: dict = {}
    for row in perms[["user_id", "resource_id", "expires_at_dt"]].itertuples(index=False):
        key = (row.user_id, row.resource_id)
        perm_expires.setdefault(key, []).append(row.expires_at_dt)

    # department → set of permitted resource_types
    dept_res_types = (
        perms.merge(users[["user_id", "department"]], on="user_id")
        .groupby("department")["resource_type"]
        .apply(set)
        .to_dict()
    )

    # Per-user log lookups
    log_res_by_user = logs.groupby("user_id")["resource_id"].apply(set).to_dict()
    log_rtype_by_user = logs.groupby("user_id")["resource_type"].apply(set).to_dict()
    log_rows_by_user = {
        uid: grp for uid, grp in logs.groupby("user_id")
    }

    # R7: accesses_per_perm ratio — fire if > p90 of ALL users
    total_acc_series = logs.groupby("user_id").size()
    perm_cnt_series  = perms.groupby("user_id").size()
    acc_per_perm = (total_acc_series / perm_cnt_series.reindex(total_acc_series.index).fillna(1))
    r7_threshold = acc_per_perm.quantile(0.90)

    records = []
    for uid in users["user_id"]:
        rule_score = 0
        signals = []
        force_very_high = False

        # R1 — access without any permission
        accessed = log_res_by_user.get(uid, set())
        permitted = user_perm_resources.get(uid, set())
        if accessed - permitted:
            rule_score += weights["access_without_perm"]
            signals.append("R1: accessed resource(s) without any assigned permission")

        # R2 — inactive user with accesses
        if user_status.get(uid) == "Inactive" and uid in log_res_by_user:
            rule_score += weights["inactive_with_access"]
            signals.append("R2: inactive user has active access logs")
            force_very_high = True

        # R3 — access with expired permission (fire once per user)
        user_logs = log_rows_by_user.get(uid)
        if user_logs is not None:
            fired_r3 = False
            for row in user_logs[["timestamp_dt", "resource_id"]].itertuples(index=False):
                key = (uid, row.resource_id)
                if key in perm_expires:
                    exps = perm_expires[key]
                    # All permissions for this resource are expired at access time
                    # NaT means no expiry → not expired (NaT > timestamp == False)
                    if exps and all(
                        (exp is not pd.NaT and not pd.isna(exp) and row.timestamp_dt > exp)
                        for exp in exps
                    ):
                        rule_score += weights["expired_perm_access"]
                        signals.append("R3: accessed resource using an expired permission")
                        fired_r3 = True
                        break
            _ = fired_r3  # suppress unused warning

        # R4 — privilege escalation
        max_perm_crit = user_max_perm_crit.get(uid, 0)
        max_acc_crit = max(
            (res_crit_num.get(rid, 0) for rid in accessed), default=0
        )
        if max_acc_crit > max_perm_crit:
            rule_score += weights["privilege_escalation"]
            signals.append(
                "R4: privilege escalation — accessed resource of higher "
                "criticality than any assigned permission"
            )

        # R5 — external user with VERY_HIGH non-expiring permission
        if user_type.get(uid) == "External":
            user_perms_df = perms[perms["user_id"] == uid]
            vh_no_exp = user_perms_df[
                (user_perms_df["criticality"].astype(str) == "VERY_HIGH")
                & user_perms_df["expires_at_dt"].isna()
            ]
            if len(vh_no_exp) > 0:
                rule_score += weights["external_very_high_no_exp"]
                signals.append(
                    "R5: external user holds non-expiring VERY_HIGH permission "
                    "(structural over-privilege)"
                )

        # R6 — cross-department resource type access
        dept = user_dept.get(uid)
        if dept:
            dept_allowed = dept_res_types.get(dept, set())
            accessed_types = log_rtype_by_user.get(uid, set())
            if accessed_types - dept_allowed:
                rule_score += weights["cross_dept_access"]
                signals.append(
                    "R6: cross-department resource access — accessed resource "
                    "type outside department permissions"
                )

        # R7 — external user with anomalous accesses-per-permission ratio
        if user_type.get(uid) == "External":
            ratio = acc_per_perm.get(uid, 0)
            if ratio > r7_threshold:
                rule_score += weights["external_insider"]
                signals.append(
                    "R7: external user with anomalous accesses-per-permission "
                    "ratio (potential insider-compromise pattern)"
                )

        records.append({
            "user_id": uid,
            "rule_score": min(rule_score, 60),
            "signals": json.dumps(signals),
            "force_very_high": int(force_very_high),
        })

    return pd.DataFrame(records)


# ── Node 3a ───────────────────────────────────────────────────────────────────

def train_anomaly_ensemble(
    user_features: pd.DataFrame,
    params: dict,
) -> dict:
    """Fit the only components that genuinely learn parameters: a StandardScaler
    and the Isolation Forest. LOF (density) and Z-score (parametric) are
    transductive and recomputed at scoring time from the persisted scaler.

    Returns a dict artifact so the score node can rebuild the full ensemble.
    """
    if_params = params["isolation_forest"]

    X = user_features[FEATURE_COLS].values.astype(float)

    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X)

    if_model = IsolationForest(
        n_estimators=if_params["n_estimators"],
        max_features=if_params["max_features"],
        max_samples=if_params["max_samples"],
        contamination=if_params["contamination"],
        random_state=if_params["random_state"],
    ).fit(Xs)

    return {
        "scaler": scaler,
        "isolation_forest": if_model,
        "feature_cols": FEATURE_COLS,
    }


# ── Node 3b ───────────────────────────────────────────────────────────────────

def score_anomaly_ensemble(
    user_features: pd.DataFrame,
    anomaly_model: dict,
    params: dict,
) -> pd.DataFrame:
    """Ensemble three independent unsupervised detectors into one anomaly score.

    All three are normalized to [0, 1] (higher = more anomalous), combined as a
    weighted average, and scaled to [0, anomaly_max]. The per-component columns
    are kept for transparency / explainability.
    """
    anomaly_max = params["anomaly_max_contribution"]
    ens = params["ensemble"]
    lof_neighbors = ens["lof_n_neighbors"]
    w_if  = ens["weight_isolation_forest"]
    w_lof = ens["weight_lof"]
    w_z   = ens["weight_zscore"]

    scaler   = anomaly_model["scaler"]
    if_model = anomaly_model["isolation_forest"]

    X = user_features[FEATURE_COLS].values.astype(float)
    Xs = scaler.transform(X)

    # 1) Isolation Forest (persisted): decision_function higher = normal
    if_comp = _minmax(-if_model.decision_function(Xs))

    # 2) Local Outlier Factor (recomputed, transductive): negative_outlier_factor_
    #    is more negative for outliers, so we negate for "higher = anomalous".
    lof = LocalOutlierFactor(n_neighbors=lof_neighbors)
    lof.fit_predict(Xs)
    lof_comp = _minmax(-lof.negative_outlier_factor_)

    # 3) Z-score sum (parametric, via persisted scaler): aggregate deviation
    z_comp = _minmax(np.abs(Xs).sum(axis=1))

    # Weighted average (weights normalized so the result stays in [0, 1])
    w_total = w_if + w_lof + w_z
    ensemble = (w_if * if_comp + w_lof * lof_comp + w_z * z_comp) / w_total
    anomaly_score = ensemble * anomaly_max

    return pd.DataFrame({
        "user_id": user_features["user_id"].values,
        "anomaly_score": anomaly_score,
        "if_component":  if_comp * anomaly_max,
        "lof_component": lof_comp * anomaly_max,
        "zscore_component": z_comp * anomaly_max,
    })


# ── Node 3c ───────────────────────────────────────────────────────────────────

def compute_impact_factor(
    user_features: pd.DataFrame,
    permission_inventory: pd.DataFrame,
    params: dict,
) -> pd.DataFrame:
    """Compute a per-user IMPACT factor (blast radius) in [0, 1].

    Impact reflects how damaging it would be if the user were compromised — the
    criticality of what they can touch (permissions) and do touch (accesses),
    plus the breadth of HIGH+ resources. This is the static counterpart to the
    behavioral anomaly score; it modulates the additive base score in
    combine_and_categorize (NIST 800-30: risk ~ likelihood × impact).
    """
    imp = params["impact"]
    cmap = imp["criticality_map"]
    num_to_unit = {
        0: 0.0,
        1: cmap["LOW"], 2: cmap["MEDIUM"], 3: cmap["HIGH"], 4: cmap["VERY_HIGH"],
    }

    perms = permission_inventory.copy()
    perms["cn"] = perms["criticality"].astype(str).map(CRITICALITY_NUM)
    max_perm = perms.groupby("user_id")["cn"].max()
    hp_perm = perms[perms["cn"] >= 3].groupby("user_id").size()  # count HIGH+

    df = user_features[["user_id", "max_crit_accessed"]].copy()
    df["max_crit_perm"] = df["user_id"].map(max_perm).fillna(0)
    df["hp_perm_count"] = df["user_id"].map(hp_perm).fillna(0)

    df["i_access"] = df["max_crit_accessed"].astype(int).map(num_to_unit).fillna(0.0)
    df["i_perm"]   = df["max_crit_perm"].astype(int).map(num_to_unit).fillna(0.0)
    df["i_max"]    = df[["i_access", "i_perm"]].max(axis=1)

    mx = df["hp_perm_count"].max()
    df["i_breadth"] = df["hp_perm_count"] / mx if mx > 0 else 0.0

    df["impact"] = (
        imp["max_weight"] * df["i_max"] + imp["breadth_weight"] * df["i_breadth"]
    ).clip(0, 1).round(4)

    return df[["user_id", "impact", "i_max", "i_breadth"]]


# ── Node 4 ────────────────────────────────────────────────────────────────────

def combine_and_categorize(
    user_inventory: pd.DataFrame,
    user_features: pd.DataFrame,
    hard_rule_scores: pd.DataFrame,
    anomaly_scores: pd.DataFrame,
    impact_scores: pd.DataFrame,
    params: dict,
) -> pd.DataFrame:
    """Combine rule + ensemble anomaly scores into an additive base, modulate it
    softly by the impact factor, assign risk categories, and generate signals."""
    thresholds = params["score_thresholds"]
    low_max  = thresholds["low_max"]
    med_max  = thresholds["medium_max"]
    high_max = thresholds["high_max"]

    # Merge all signals onto a user-level frame
    df = user_inventory[["user_id", "department", "role", "user_type", "status"]].copy()
    df = df.merge(
        hard_rule_scores[["user_id", "rule_score", "signals", "force_very_high"]],
        on="user_id", how="left",
    )
    df = df.merge(anomaly_scores[["user_id", "anomaly_score"]], on="user_id", how="left")
    df = df.merge(impact_scores[["user_id", "impact", "i_max"]], on="user_id", how="left")
    df["rule_score"]     = df["rule_score"].fillna(0)
    df["anomaly_score"]  = df["anomaly_score"].fillna(0)
    df["impact"]         = df["impact"].fillna(0)
    df["i_max"]          = df["i_max"].fillna(0)
    df["force_very_high"] = df["force_very_high"].fillna(0).astype(bool)
    df["signals"]        = df["signals"].fillna("[]")

    # Additive base (Layer 1 + Layer 2), then soft impact modulation
    # final = base × (floor + (1 - floor) · impact)   — impact dampens, never below floor
    floor = params["impact"]["multiplier_floor"]
    df["base_score"]   = (df["rule_score"] + df["anomaly_score"]).clip(0, 100)
    df["impact_mult"]  = (floor + (1 - floor) * df["impact"]).round(4)
    df["score"]        = (df["base_score"] * df["impact_mult"]).clip(0, 100).round(2)

    # Base category
    def _category(score):
        if score <= low_max:  return "LOW"
        if score <= med_max:  return "MEDIUM"
        if score <= high_max: return "HIGH"
        return "VERY_HIGH"

    df["category"] = df["score"].apply(_category)

    # R2 override: inactive users always VERY_HIGH, score floor at 85
    mask_r2 = df["force_very_high"]
    df.loc[mask_r2, "category"] = "VERY_HIGH"
    df.loc[mask_r2, "score"]    = df.loc[mask_r2, "score"].clip(lower=85)

    # ML feature signals: top-2 features with population z > 1.0
    feat_means = user_features[FEATURE_COLS].mean()
    feat_stds  = user_features[FEATURE_COLS].std(ddof=0).replace(0, 1)

    feat_lookup = user_features.set_index("user_id")

    def _if_signals(uid: str) -> list:
        if uid not in feat_lookup.index:
            return []
        row_vals = feat_lookup.loc[uid, FEATURE_COLS].values.astype(float)
        z_abs = np.abs((row_vals - feat_means.values) / feat_stds.values)
        top_idx = z_abs.argsort()[::-1][:2]
        return [
            FEATURE_SIGNAL_LABELS[FEATURE_COLS[i]]
            for i in top_idx if z_abs[i] > 1.0
        ]

    def _impact_signal(i_max: float) -> list:
        if i_max >= 1.0:
            return ["Impact: máximo blast radius (recursos VERY_HIGH)"]
        if i_max >= 0.75:
            return ["Impact: alto blast radius (recursos HIGH+)"]
        return []

    df["top_signals"] = df.apply(
        lambda row: json.dumps(
            json.loads(row["signals"])
            + _if_signals(row["user_id"])
            + _impact_signal(row["i_max"])
        ),
        axis=1,
    )

    return df[[
        "user_id", "score", "category", "top_signals",
        "base_score", "rule_score", "anomaly_score", "impact", "impact_mult",
        "department", "role", "user_type", "status",
    ]].sort_values("score", ascending=False).reset_index(drop=True)

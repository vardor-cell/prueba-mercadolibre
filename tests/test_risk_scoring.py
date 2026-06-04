"""Tests unitarios del modelo de scoring (reglas, impacto, categorización)."""
import json

import pandas as pd

from prueba_mercadolibre.pipelines.risk_scoring.nodes import (
    FEATURE_COLS,
    combine_and_categorize,
    compute_hard_rule_scores,
    compute_impact_factor,
)


def _fired(signals_json: str) -> set:
    """Devuelve el conjunto de reglas (R1, R2, …) presentes en las señales."""
    return {s.split(":")[0] for s in json.loads(signals_json) if s.startswith("R")}


# ── Reglas duras ──────────────────────────────────────────────────────────────

def _scenario():
    """3 usuarios: uno limpio, uno que accede sin permiso (R1), uno inactivo (R2)."""
    users = pd.DataFrame([
        {"user_id": "U_OK",       "status": "Active",   "user_type": "Internal", "department": "HR"},
        {"user_id": "U_NOPERM",   "status": "Active",   "user_type": "Internal", "department": "HR"},
        {"user_id": "U_INACTIVE", "status": "Inactive", "user_type": "Internal", "department": "HR"},
    ])
    perms = pd.DataFrame([
        {"user_id": "U_OK",       "resource_id": "R1", "resource_type": "database", "criticality": "HIGH", "expires_at": None},
        {"user_id": "U_NOPERM",   "resource_id": "R1", "resource_type": "database", "criticality": "HIGH", "expires_at": None},
        {"user_id": "U_INACTIVE", "resource_id": "R1", "resource_type": "database", "criticality": "HIGH", "expires_at": None},
    ])
    logs = pd.DataFrame([
        {"user_id": "U_OK",       "timestamp": "2026-01-01 10:00:00", "resource_id": "R1", "resource_type": "database", "action": "READ"},
        {"user_id": "U_NOPERM",   "timestamp": "2026-01-01 10:00:00", "resource_id": "R2", "resource_type": "database", "action": "READ"},
        {"user_id": "U_INACTIVE", "timestamp": "2026-01-01 10:00:00", "resource_id": "R1", "resource_type": "database", "action": "READ"},
    ])
    return users, perms, logs


def test_clean_user_fires_no_rule(params):
    users, perms, logs = _scenario()
    out = compute_hard_rule_scores(users, perms, logs, params).set_index("user_id")
    assert out.loc["U_OK", "rule_score"] == 0
    assert _fired(out.loc["U_OK", "signals"]) == set()


def test_access_without_permission_fires_r1(params):
    users, perms, logs = _scenario()
    out = compute_hard_rule_scores(users, perms, logs, params).set_index("user_id")
    assert "R1" in _fired(out.loc["U_NOPERM", "signals"])
    assert out.loc["U_NOPERM", "rule_score"] > 0


def test_inactive_with_access_fires_r2_and_forces_very_high(params):
    users, perms, logs = _scenario()
    out = compute_hard_rule_scores(users, perms, logs, params).set_index("user_id")
    assert "R2" in _fired(out.loc["U_INACTIVE", "signals"])
    assert out.loc["U_INACTIVE", "force_very_high"] == 1


# ── Factor de impacto ─────────────────────────────────────────────────────────

def test_impact_higher_for_critical_resources(params):
    feats = pd.DataFrame([
        {"user_id": "U_HIGH", "max_crit_accessed": 4},  # accede VERY_HIGH
        {"user_id": "U_LOW",  "max_crit_accessed": 1},  # accede LOW
    ])
    perms = pd.DataFrame([
        {"user_id": "U_HIGH", "resource_id": "R1", "criticality": "LOW"},
        {"user_id": "U_LOW",  "resource_id": "R2", "criticality": "LOW"},
    ])
    out = compute_impact_factor(feats, perms, params).set_index("user_id")
    assert out.loc["U_HIGH", "impact"] > out.loc["U_LOW", "impact"]
    assert 0 <= out["impact"].min() <= out["impact"].max() <= 1


# ── Combinación y categorías ──────────────────────────────────────────────────

def _combine_inputs():
    users = pd.DataFrame([
        {"user_id": u, "department": "HR", "role": "Analyst", "user_type": "Internal", "status": "Active"}
        for u in ["U_LOW", "U_MED", "U_R2"]
    ])
    features = pd.DataFrame([{"user_id": u, **{c: 0.0 for c in FEATURE_COLS}}
                             for u in ["U_LOW", "U_MED", "U_R2"]])
    rules = pd.DataFrame([
        {"user_id": "U_LOW", "rule_score": 0,  "signals": "[]", "force_very_high": 0},
        {"user_id": "U_MED", "rule_score": 30, "signals": "[]", "force_very_high": 0},
        {"user_id": "U_R2",  "rule_score": 45, "signals": "[]", "force_very_high": 1},
    ])
    anomaly = pd.DataFrame([
        {"user_id": "U_LOW", "anomaly_score": 0.0},
        {"user_id": "U_MED", "anomaly_score": 10.0},
        {"user_id": "U_R2",  "anomaly_score": 10.0},
    ])
    impact = pd.DataFrame([
        {"user_id": "U_LOW", "impact": 0.5, "i_max": 0.5},
        {"user_id": "U_MED", "impact": 1.0, "i_max": 1.0},
        {"user_id": "U_R2",  "impact": 0.5, "i_max": 0.5},
    ])
    return users, features, rules, anomaly, impact


def test_low_score_is_low_category(params):
    users, feats, rules, anomaly, impact = _combine_inputs()
    out = combine_and_categorize(users, feats, rules, anomaly, impact, params).set_index("user_id")
    assert out.loc["U_LOW", "category"] == "LOW"
    assert out.loc["U_LOW", "score"] == 0


def test_r2_override_forces_very_high(params):
    users, feats, rules, anomaly, impact = _combine_inputs()
    out = combine_and_categorize(users, feats, rules, anomaly, impact, params).set_index("user_id")
    assert out.loc["U_R2", "category"] == "VERY_HIGH"
    assert out.loc["U_R2", "score"] >= 85


def test_score_is_rule_plus_anomaly_times_impact(params):
    users, feats, rules, anomaly, impact = _combine_inputs()
    out = combine_and_categorize(users, feats, rules, anomaly, impact, params).set_index("user_id")
    # U_MED: base = 30 + 10 = 40 ; mult = floor + (1-floor)*1.0 = 1.0 ; score = 40
    k = params["impact"]["multiplier_floor"]
    expected = (30 + 10) * (k + (1 - k) * 1.0)
    assert abs(out.loc["U_MED", "score"] - round(expected, 2)) < 0.01

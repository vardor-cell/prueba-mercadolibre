"""Tests unitarios de la limpieza de datos (pipeline data_processing)."""
import pandas as pd

from prueba_mercadolibre.pipelines.data_processing.nodes import (
    clean_access_logs,
    clean_permission_inventory,
    clean_user_inventory,
)


def _user_row(user_id="U1", user_type="Internal", status="Active",
              created_at="2025-01-01", manager_id="M1"):
    return {"user_id": user_id, "user_type": user_type, "department": "HR",
            "role": "Analyst", "status": status, "created_at": created_at,
            "manager_id": manager_id}


def _log_row(user_id="U1", ts="2026-01-01 10:00:00", resource_id="R1",
             rtype="database", action="READ", dur=100):
    return {"user_id": user_id, "timestamp": ts, "resource_id": resource_id,
            "resource_type": rtype, "action": action, "source_system": "s",
            "session_duration_sec": dur}


# ── users ─────────────────────────────────────────────────────────────────────

def test_user_strip_whitespace():
    df = pd.DataFrame([_user_row(user_type="  Internal  ")])
    out = clean_user_inventory(df)
    assert out.loc[0, "user_type"] == "Internal"


def test_user_drops_duplicates():
    df = pd.DataFrame([_user_row(), _user_row()])  # fila repetida
    out = clean_user_inventory(df)
    assert len(out) == 1


def test_user_drops_invalid_status():
    df = pd.DataFrame([_user_row(status="Active"), _user_row(user_id="U2", status="ZOMBIE")])
    out = clean_user_inventory(df)
    assert set(out["user_id"]) == {"U1"}


def test_user_drops_null_key():
    df = pd.DataFrame([_user_row(), _user_row(user_id=None)])
    out = clean_user_inventory(df)
    assert len(out) == 1


def test_user_has_manager_flag():
    df = pd.DataFrame([_user_row(manager_id="M1"), _user_row(user_id="U2", manager_id=None)])
    out = clean_user_inventory(df).set_index("user_id")
    assert out.loc["U1", "has_manager"] == 1
    assert out.loc["U2", "has_manager"] == 0


# ── permissions ─────────────────────────────────────────────────────────────--

def _perm_row(user_id="U1", resource_id="R1", crit="HIGH",
              assigned="2025-01-01", expires="2026-01-01"):
    return {"user_id": user_id, "resource_id": resource_id, "resource_type": "database",
            "criticality": crit, "assigned_at": assigned, "expires_at": expires}


def test_perm_drops_invalid_criticality():
    df = pd.DataFrame([_perm_row(crit="HIGH"), _perm_row(resource_id="R2", crit="ULTRA")])
    out = clean_permission_inventory(df)
    assert set(out["resource_id"]) == {"R1"}


def test_perm_drops_expiry_before_assignment():
    df = pd.DataFrame([_perm_row(assigned="2026-01-01", expires="2025-01-01")])
    out = clean_permission_inventory(df)
    assert len(out) == 0


def test_perm_has_expiry_flag():
    df = pd.DataFrame([_perm_row(expires="2026-01-01"),
                       _perm_row(resource_id="R2", expires=None)])
    out = clean_permission_inventory(df).set_index("resource_id")
    assert out.loc["R1", "has_expiry"] == 1
    assert out.loc["R2", "has_expiry"] == 0


# ── access logs ─────────────────────────────────────────────────────────────--

def test_log_drops_invalid_action_and_resourcetype():
    df = pd.DataFrame([_log_row(action="READ"),
                       _log_row(user_id="U2", action="HACK"),
                       _log_row(user_id="U3", rtype="quantum")])
    out = clean_access_logs(df)
    assert set(out["user_id"]) == {"U1"}


def test_log_drops_unparseable_timestamp():
    df = pd.DataFrame([_log_row(ts="2026-01-01 10:00:00"),
                       _log_row(user_id="U2", ts="no-es-fecha")])
    out = clean_access_logs(df)
    assert set(out["user_id"]) == {"U1"}


def test_log_caps_session_duration():
    rows = [_log_row(dur=100) for _ in range(100)]
    rows.append(_log_row(user_id="U2", dur=10_000_000))  # outlier alto
    rows.append(_log_row(user_id="U3", dur=-50))         # negativo corrupto
    out = clean_access_logs(pd.DataFrame(rows))
    assert out["session_duration_sec"].min() >= 0
    assert out["session_duration_sec"].max() < 10_000_000

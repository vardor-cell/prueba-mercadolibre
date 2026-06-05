"""Dashboard de User Risk Profiling — lee EN VIVO desde BigQuery.

Cubre el bonus track del challenge:
  1. Distribución de usuarios por categoría de riesgo
  2. Top 10 usuarios más críticos con sus señales
  3. Comparativa de comportamiento vs. peer group (departamento + rol)

Se corre con un solo comando:  streamlit run dashboard/app.py
(requiere conf/local/gcp-key.json, igual que el resto del proyecto).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Garantiza que el módulo hermano `bq.py` se importe sin importar desde dónde se
# lance Streamlit (y evita que el directorio `data/` de la raíz interfiera).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bq  # noqa: E402

# Orden y paleta de categorías (de menor a mayor riesgo).
CATEGORY_ORDER = ["LOW", "MEDIUM", "HIGH", "VERY_HIGH"]
CATEGORY_COLORS = {
    "LOW": "#2ecc71",
    "MEDIUM": "#f1c40f",
    "HIGH": "#e67e22",
    "VERY_HIGH": "#e74c3c",
}

# Features de comportamiento que se comparan contra el peer group, con etiqueta legible.
PEER_FEATURES = {
    "total_accesses": "Accesos totales",
    "distinct_resources": "Recursos distintos",
    "perm_count": "Permisos asignados",
    "after_hours_ratio": "Ratio fuera de horario",
    "exfil_ratio": "Ratio de exfiltración",
}

st.set_page_config(page_title="User Risk Profiling", page_icon="🛡️", layout="wide")


# ── Carga de datos (cacheada 5 min para no golpear BQ en cada interacción) ──────

@st.cache_data(ttl=300, show_spinner="Consultando BigQuery…")
def _load():
    """Carga scores (l5) y features (l3) desde BigQuery. Cacheado por 5 minutos."""
    return bq.load_scores(), bq.load_features()


try:
    scores, features = _load()
except Exception as exc:  # credenciales ausentes, tabla vacía, etc.
    st.error(f"No se pudieron leer los datos de BigQuery: {exc}")
    st.info(
        "Verificá que el pipeline ya corrió (tabla `l5_risk_scores` poblada) y que "
        "exista `conf/local/gcp-key.json` o la env var `GCP_SA_KEY`."
    )
    st.stop()

if scores.empty:
    st.warning("La tabla `l5_risk_scores` está vacía. Corré el pipeline (`kedro run`) primero.")
    st.stop()


# ── Sidebar: filtros ────────────────────────────────────────────────────────────

st.sidebar.header("Filtros")
depts = sorted(scores["department"].dropna().unique())
types = sorted(scores["user_type"].dropna().unique())

sel_depts = st.sidebar.multiselect("Departamento", depts, default=depts)
sel_types = st.sidebar.multiselect("Tipo de usuario", types, default=types)

# El peer group SIEMPRE se calcula sobre la población completa (no sobre el filtro),
# para que la comparativa de un usuario no dependa de lo que esté mirando el analista.
view = scores[scores["department"].isin(sel_depts) & scores["user_type"].isin(sel_types)]

if view.empty:
    st.warning("Ningún usuario cae dentro de los filtros seleccionados.")
    st.stop()


# ── Encabezado + KPIs ───────────────────────────────────────────────────────────

st.title("🛡️ User Risk Profiling")
st.caption("Datos en vivo desde BigQuery · dataset `risk_profiling` · tabla `l5_risk_scores`")

n_total = len(view)
n_vh = int((view["category"] == "VERY_HIGH").sum())
n_high_plus = int(view["category"].isin(["HIGH", "VERY_HIGH"]).sum())

k1, k2, k3, k4 = st.columns(4)
k1.metric("Usuarios", f"{n_total:,}")
k2.metric("VERY_HIGH", n_vh, help="Usuarios en la categoría de máximo riesgo")
k3.metric("HIGH o superior", n_high_plus, f"{n_high_plus / n_total:.0%} del total")
k4.metric("Score máximo", f"{view['score'].max():.1f}")

st.divider()


# ── 1) Distribución por categoría ────────────────────────────────────────────────

col_dist, col_hist = st.columns([1, 1])

with col_dist:
    st.subheader("Distribución por categoría de riesgo")
    counts = (
        view["category"].value_counts()
        .reindex(CATEGORY_ORDER, fill_value=0)
        .reset_index()
    )
    counts.columns = ["category", "count"]
    fig = px.bar(
        counts, x="category", y="count", color="category",
        color_discrete_map=CATEGORY_COLORS, text="count",
        category_orders={"category": CATEGORY_ORDER},
    )
    fig.update_layout(showlegend=False, xaxis_title=None, yaxis_title="Usuarios")
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, width="stretch")

with col_hist:
    st.subheader("Distribución del score")
    fig_h = px.histogram(
        view, x="score", color="category", nbins=30,
        color_discrete_map=CATEGORY_COLORS,
        category_orders={"category": CATEGORY_ORDER},
    )
    fig_h.update_layout(xaxis_title="Score", yaxis_title="Usuarios", legend_title=None)
    st.plotly_chart(fig_h, width="stretch")

st.divider()


# ── 2) Top 10 usuarios más críticos con sus señales ──────────────────────────────

st.subheader("Top 10 usuarios más críticos")

top10 = view.sort_values("score", ascending=False).head(10).reset_index(drop=True)

table = top10[["user_id", "score", "category", "department", "role", "user_type", "status"]].copy()
table.insert(0, "#", range(1, len(table) + 1))
st.dataframe(
    table,
    hide_index=True,
    width="stretch",
    column_config={
        "score": st.column_config.NumberColumn("score", format="%.1f"),
    },
)

st.markdown("**Señales que explican cada score** (desplegá cada usuario):")
for _, row in top10.iterrows():
    label = f"{row['user_id']} · {row['score']:.1f} · {row['category']}"
    with st.expander(label):
        signals = row["top_signals"]
        if signals:
            for s in signals:
                st.markdown(f"- {s}")
        else:
            st.caption("Sin señales registradas.")
        # Desglose de ingredientes del score (reglas + ML × impacto).
        st.caption(
            f"base = reglas {row['rule_score']:.0f} + ML {row['anomaly_score']:.1f}  "
            f"·  impacto {row['impact']:.2f}  →  score {row['score']:.1f}"
        )

st.divider()


# ── 3) Comparativa de comportamiento vs. peer group ──────────────────────────────

st.subheader("Comparativa de comportamiento vs. peer group")
st.caption(
    "El peer group es el conjunto de usuarios del **mismo departamento y rol**. "
    "Se compara el comportamiento del usuario seleccionado contra el promedio de sus pares."
)

# Unimos scores (para dept/role) con las features de comportamiento.
merged = view.merge(features, on="user_id", how="left")

# Por defecto, el usuario de mayor riesgo dentro del filtro.
user_ids = merged.sort_values("score", ascending=False)["user_id"].tolist()
sel_user = st.selectbox("Usuario a analizar", user_ids)

urow = merged[merged["user_id"] == sel_user].iloc[0]
dept, role = urow["department"], urow["role"]

# Peer group sobre la población COMPLETA (scores ⨝ features), no sobre el filtro.
pop = scores.merge(features, on="user_id", how="left")
peers = pop[(pop["department"] == dept) & (pop["role"] == role)]

st.markdown(
    f"**{sel_user}** — {dept} / {role} · score **{urow['score']:.1f}** "
    f"({urow['category']}) · peer group: {len(peers)} usuario(s)"
)

if len(peers) <= 1 or peers[list(PEER_FEATURES)].isna().all().all():
    st.info("Peer group insuficiente (1 solo usuario o sin features) para comparar.")
else:
    rows = []
    for col, label in PEER_FEATURES.items():
        peer_mean = peers[col].mean()
        user_val = urow[col]
        if pd.isna(user_val):
            continue
        ratio = user_val / peer_mean if peer_mean else float("nan")
        rows.append({
            "Feature": label,
            "Usuario": round(float(user_val), 2),
            "Promedio peers": round(float(peer_mean), 2),
            "× vs peers": round(float(ratio), 2) if pd.notna(ratio) else None,
        })
    comp = pd.DataFrame(rows)

    col_tbl, col_chart = st.columns([1, 1])
    with col_tbl:
        st.dataframe(comp, hide_index=True, width="stretch")
    with col_chart:
        # Barras agrupadas usuario vs promedio de pares.
        long = comp.melt(
            id_vars="Feature", value_vars=["Usuario", "Promedio peers"],
            var_name="Serie", value_name="Valor",
        )
        fig_c = px.bar(
            long, x="Feature", y="Valor", color="Serie", barmode="group",
            color_discrete_map={"Usuario": "#e74c3c", "Promedio peers": "#7f8c8d"},
        )
        fig_c.update_layout(xaxis_title=None, legend_title=None)
        st.plotly_chart(fig_c, width="stretch")

st.divider()
st.caption(
    "Pipeline Kedro → BigQuery → este dashboard. Para refrescar los datos, volvé a "
    "correr el pipeline (`kedro run`) y recargá (la caché expira a los 5 min)."
)

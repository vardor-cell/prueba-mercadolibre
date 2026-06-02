# User Risk Profiling Challenge

## Contexto

Trabajás en el equipo de seguridad de datos de una empresa con miles de usuarios internos y externos. Tu objetivo es construir un sistema que detecte comportamientos anómalos y calcule un perfil de riesgo por usuario, usando datos de accesos a sistemas y los permisos asignados.

No necesitás conocimiento previo de ninguna plataforma interna. Todo lo que necesitás está en los datos.

---

## Datasets

Encontrás tres archivos CSV en la carpeta `data/`:

### `user_inventory.csv`
Inventario de usuarios del sistema.

| Campo | Descripción |
|---|---|
| `user_id` | Identificador único |
| `user_type` | `Internal` o `External` |
| `department` | Departamento al que pertenece |
| `role` | Rol dentro de la empresa |
| `status` | `Active` o `Inactive` |
| `created_at` | Fecha de creación de la cuenta |
| `manager_id` | user_id de su manager (puede ser null) |

### `permission_inventory.csv`
Permisos asignados a cada usuario sobre recursos del sistema.

| Campo | Descripción |
|---|---|
| `user_id` | Usuario al que se le asignó el permiso |
| `resource_id` | Identificador del recurso |
| `resource_type` | Tipo: `admin_panel`, `payment_portal`, `vdi`, `database`, `api_internal`, `drive`, `email_system`, `reporting_tool` |
| `criticality` | `VERY_HIGH`, `HIGH`, `MEDIUM`, `LOW` |
| `assigned_at` | Fecha de asignación |
| `expires_at` | Fecha de expiración (puede ser null = sin vencimiento) |

### `access_logs.csv`
Registro de todos los accesos realizados por usuarios a recursos del sistema.

| Campo | Descripción |
|---|---|
| `user_id` | Usuario que realizó el acceso |
| `timestamp` | Fecha y hora del acceso |
| `resource_id` | Recurso al que accedió |
| `resource_type` | Tipo de recurso |
| `action` | Acción realizada: `READ`, `WRITE`, `DELETE`, `EXPORT`, `LOGIN`, `QUERY` |
| `source_system` | Sistema de origen del evento |
| `session_duration_sec` | Duración de la sesión en segundos |

---

## Tareas

### Parte 1 — Exploración y calidad de datos

- Hacé un análisis exploratorio (EDA) completo de los tres datasets
- Identificá inconsistencias, missings, outliers y relaciones entre tablas
- Antes de modelar, escribí tus hipótesis: ¿qué tipos de anomalías esperás encontrar?

**Entregable:** notebook o script con el EDA y tus hipótesis documentadas.

---

### Parte 2 — Modelo de scoring de riesgo

Construí un **risk score por usuario**. El approach es libre: podés usar reglas heurísticas, clustering (K-means, DBSCAN), modelos de detección de anomalías (Isolation Forest, LOF), o una combinación.

El score debe tener en cuenta al menos:

- Volumen de accesos vs. pares del mismo departamento/rol
- Criticidad y confidencialidad de los recursos a los que accede
- Coherencia entre permisos asignados y accesos reales
- Tipo de usuario (interno vs. externo) y su comportamiento relativo
- Patrones temporales (horarios, frecuencia, tendencias)

Requisitos del scoring:

- Debe producir una **categoría de riesgo**: `VERY_HIGH`, `HIGH`, `MEDIUM`, `LOW`
- Debe identificar las **principales señales** que explican el score de cada usuario
- Debe poder ejecutarse sobre los tres archivos CSV sin dependencias externas de APIs

**Entregable:** código limpio, reproducible, con instrucciones para correrlo.

---

### Parte 3 — API REST

Exponer el modelo como una API REST con al menos estos dos endpoints:

```
GET /users/{user_id}/risk
```
Respuesta esperada:
```json
{
  "user_id": "USR0042",
  "score": 87.4,
  "category": "HIGH",
  "top_signals": [
    "Accede a recursos de criticidad VERY_HIGH no asignados",
    "Volumen de accesos 3x mayor que su peer group"
  ]
}
```

```
GET /users?category=HIGH&limit=10
```
Respuesta esperada: lista de usuarios ordenados por score descendente dentro de esa categoría.

**Lenguaje y framework:** libre (Python/FastAPI, Go, Node.js, etc.)
**Requisito:** debe correr localmente con un solo comando. Documentar en README.

---

### Parte 4 — Documento de análisis

Un documento (Markdown o PDF) con:

1. **Hallazgos principales** — ¿Quiénes son los usuarios más riesgosos y por qué?
2. **Decisiones de modelado** — ¿Por qué elegiste ese approach y no otro? ¿Qué trade-offs tiene?
3. **Limitaciones** — ¿Qué no puede ver tu modelo? ¿Qué datos adicionales mejorarían el resultado?
4. **Monitoreo en producción** — ¿Qué métricas o alertas configurarías si esto corriera en producción?

---

## Bonus track (opcional pero valorado)

Un dashboard o reporte visual que, al correr localmente, muestre:

- Distribución de usuarios por categoría de riesgo
- Top 10 usuarios más críticos con sus señales
- Comparativa de comportamiento vs. peer group

Puede ser Streamlit, Dash, Plotly, un notebook con visualizaciones o un HTML estático generado. El requisito es: `git clone → un comando → ver los resultados`.

---

## Criterio de evaluación

| Área | Peso | Qué se evalúa |
|---|---|---|
| Calidad del análisis | 30% | ¿Identificó las anomalías? ¿Separó señal de ruido? ¿Las hipótesis son coherentes? |
| Modelo / scoring | 25% | ¿El approach es justificable? ¿Las métricas son sensatas? ¿Entiende las limitaciones? |
| Código / API | 25% | ¿Corre sin errores? ¿Está limpio y documentado? ¿Hay tests? |
| Presentación | 20% | ¿Puede defender sus decisiones? ¿Sabe qué no sabe? ¿Comunica hallazgos con claridad? |

---

## Entregables

1. **Repositorio GitHub** público con todo el código, notebooks y README
2. **Documento de análisis** (Markdown en el repo o PDF adjunto)
3. **Presentación de 15 minutos** donde mostrás los hallazgos y defendés las decisiones

El repo debe tener instrucciones claras para reproducir todo localmente desde cero.

---

## Tiempo estimado

**7 días.** No esperamos perfección — esperamos criterio, claridad en las decisiones y código que funcione.

---

## Stack sugerido (no obligatorio)

- **Análisis:** Python, pandas, scikit-learn, Jupyter
- **API:** FastAPI + uvicorn, o Go + chi/gin, o Node.js + express
- **Visualización:** Streamlit, Plotly, Seaborn

---

*Cualquier duda durante el challenge es bienvenida — 
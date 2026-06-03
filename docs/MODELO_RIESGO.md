# Modelo de Risk Scoring — Decisiones de Diseño

Este documento detalla **cómo se define cada componente** del modelo de riesgo por usuario: la fórmula final, los puntajes, los pesos, los dos modelos de anomalía, el factor de impacto y los umbrales — con la justificación de cada número y las decisiones tomadas.

> Audiencia: equipo de seguridad de datos. Toda la configuración vive en `conf/base/parameters/risk_scoring.yml` y es ajustable sin tocar código.

---

## 1. Visión general — arquitectura de dos capas + modulación

El modelo sigue el patrón **UEBA híbrido** (Gartner UEBA, NIST SP 800-53): una capa determinista de reglas duras + una capa de Machine Learning no supervisado. Sobre esa base aditiva se aplica una **modulación suave por impacto** (NIST SP 800-30: riesgo ~ probabilidad × impacto).

```
                    ┌─────────────────────────────────────────────┐
   Capa 1 (reglas)  │ rule_score   ∈ [0, 60]   (suma de 7 reglas)  │
                    ├─────────────────────────────────────────────┤
   Capa 2 (ML)      │ anomaly_score∈ [0, 40]   (ensemble 3 modelos)│
                    └─────────────────────────────────────────────┘
                                       │
                base_aditivo = clip(rule_score + anomaly_score, 0, 100)
                                       │
                   × (0.7 + 0.3 · impacto)      ← modulación de impacto
                                       │
                final_score ∈ [0, 100]  →  categoría (LOW/MEDIUM/HIGH/VERY_HIGH)
```

**Fórmula completa:**
```
base   = clip(rule_score + anomaly_score, 0, 100)
final  = clip(base × (0.7 + 0.3 × impacto), 0, 100)
si el usuario es Inactive con accesos (R2):  final = max(final, 85), categoría = VERY_HIGH
```

---

## 2. Capa 1 — Reglas duras (0–60 puntos)

Son violaciones **deterministas y binarias**: cualquier ocurrencia es una señal clara, independientemente del grado. Cada regla mapea a una técnica **MITRE ATT&CK** y suma puntos; la suma se topea en 60.

| Regla | Descripción | Peso | MITRE ATT&CK | Justificación del peso |
|---|---|---:|---|---|
| **R1** | Acceso a recurso **sin permiso** asignado | 30 | [T1078](https://attack.mitre.org/techniques/T1078/) Valid Accounts | Alta severidad, confianza media (puede ser lag de aprovisionamiento) |
| **R2** | Usuario **Inactive** con accesos en logs | 45 | [T1078.001](https://attack.mitre.org/techniques/T1078/001/) | **Máxima**: una cuenta inactiva usada no tiene explicación legítima. Fuerza VERY_HIGH |
| **R3** | Acceso con **permiso expirado** | 20 | [T1078](https://attack.mitre.org/techniques/T1078/) | Suspicioso pero con causas benignas plausibles (control de acceso deficiente) |
| **R4** | **Privilege escalation** (accede a criticidad > sus permisos) | 30 | [T1548](https://attack.mitre.org/techniques/T1548/) Abuse Elevation | Alta severidad: opera por encima de su nivel autorizado |
| **R5** | Externo con permiso **VERY_HIGH sin vencimiento** | 15 | [T1098](https://attack.mitre.org/techniques/T1098/) Account Manipulation | **Mínima**: riesgo estructural/configuración, no evento malicioso activo |
| **R6** | **Cross-department**: accede a tipo de recurso fuera del perfil de su depto | 20 | [T1021](https://attack.mitre.org/techniques/T1021/) Remote Services | Movimiento lateral; explicaciones benignas posibles |
| **R7** | Externo con ratio accesos/permisos anómalo (> p90) | 20 | [T1078.004](https://attack.mitre.org/techniques/T1078/004/) | Patrón insider-comprometido; confianza media |

### Cómo se definieron los pesos

Los valores exactos son **juicio experto calibrado**, no derivados de una fórmula (igual que los pesos base de CVSS). Lo que se justifica es el **orden relativo**, según una matriz de 2 ejes **severidad × confianza**:

- **R2 = 45** (máximo): severidad y confianza máximas → además fuerza categoría VERY_HIGH.
- **R1 = R4 = 30**: alta severidad, confianza algo menor.
- **R3 = R6 = R7 = 20**: sospechoso con explicaciones benignas más plausibles.
- **R5 = 15** (mínimo): exposición latente (configuración), no comportamiento activo.

> **Robustez (demostrada):** el ranking del top-K es estable ante perturbación de estos pesos — los usuarios riesgosos siguen siendo los mismos aunque un peso sea 38 en vez de 45. Ver `notebooks/03_weight_sensitivity.ipynb`: con perturbación aleatoria de **±50%** en todos los pesos (500 corridas), el ranking se mantiene casi idéntico (**Spearman 0.9998**) y el top-20 conserva el **81%**. Los números no son "load-bearing".
>
> Hallazgo adicional del análisis: los pesos de **máxima confianza** (R2=45, R4=30) **no afectan el top-20 en absoluto** (sus usuarios están saturados muy por encima del umbral). Solo los pesos chicos del borde (R5, R7) tienen efecto marginal. Esto refuerza que la calibración fina de los pesos altos es irrelevante.

### Override de R2
Si R2 dispara, el usuario se fuerza a `category = VERY_HIGH` y `score = max(score, 85)`. Razón: una cuenta inactiva en uso es la señal de máxima confianza posible y no debe poder caer por debajo de VERY_HIGH por efecto de otras capas.

---

## 3. Capa 2 — Ensemble de anomalía no supervisado (0–40 puntos)

El comportamiento anómalo **continuo** (cuestión de grado, no binario) lo detecta un **ensemble de tres detectores de familias distintas**. Razón de usar tres: si métodos independientes coinciden en quién es anómalo, la detección es robusta a la elección del algoritmo.

| Detector | Familia | Persistido | Rol |
|---|---|---|---|
| **Isolation Forest** | particiones (árboles) | ✅ sí (se entrena) | señal continua principal |
| **LOF** (Local Outlier Factor) | densidad (vecindario, k=20) | ❌ recalculado | detector de picos de densidad |
| **Z-score sum** | distancia paramétrica (vía scaler) | ❌ recalculado | señal continua |

**Cálculo:** cada detector produce un score crudo → se normaliza a [0,1] con min-max (mayor = más anómalo) → promedio ponderado (pesos 1/1/1) → se escala a [0, 40].

```
anomaly_score = mean(IF_norm, LOF_norm, Zscore_norm) × 40
```

### Por qué solo se persiste el Isolation Forest
- **IF** es inductivo: aprende una estructura de particiones que conviene congelar → se guarda en `data/06_models/anomaly_ensemble.pkl` junto al `StandardScaler`.
- **LOF y Z-score son transductivos**: no "aprenden" parámetros más allá del scaler. Se recalculan sobre el batch que se puntúa. Para LOF, recalcular (`novelty=False`) es de hecho lo *correcto* al puntuar la misma población — `novelty=True` daría scores sesgados sobre datos de entrenamiento.
- Esto preserva la separación de tags `--tags=train` / `--tags=score`.

### Features del modelo (17)
Volumetría (`total_accesses`, `distinct_resources`), z-scores vs peer group (`z_volume_peers`, `z_distinct_peers`, `z_exfil_peers`, `z_perms_peers`), comportamiento (`exfil_ratio`, `action_entropy`, `after_hours_ratio`, `weekend_ratio`, `delete_ratio`, `avg_session_sec`), criticidad (`max_crit_accessed`, `very_high_access_ratio`, `high_plus_access_ratio`), contexto (`perm_count`, `is_external`).

### Hiperparámetros (calibrados en `notebooks/02_model_tuning.ipynb`)

| Parámetro | Valor | Por qué |
|---|---|---|
| `n_estimators` | **500** | Máxima estabilidad del ranking (Stability full 0.99) |
| `max_features` | **0.9** | Más diversidad entre árboles → mejora estabilidad |
| `contamination` | 0.05 | **No afecta el ranking** — solo mueve el umbral de `predict()`; se cancela en la normalización min-max. Documental |
| `lof_n_neighbors` | 20 | Estándar para LOF |

---

## 4. Modelo X vs Modelo Y — la decisión clave de combinación

Se evaluaron dos formas de combinar las capas. **La decisión se tomó con evidencia, no por preferencia teórica.**

### Modelo X — Aditivo puro (punto de partida)
```
final = clip(rule_score + anomaly_score, 0, 100)
```
- ➕ Simple, transparente, robusto (ninguna señal anula el score).
- ➖ **Ciego a la criticidad**: acceder sin permiso a una intranet trivial puntúa igual que a la base de datos de pagos.

### Modelo Y — Probabilidad × Impacto puro (NIST 800-30 / FAIR)
```
final = P × I × 100   (con P = noisy-OR de anomalía + reglas, I = criticidad con piso 0.2)
```
- ➕ Canónico, defendible, separa "qué tan sospechoso" de "qué tan grave".
- ➖ **Fragilidad multiplicativa**: enterraba a usuarios genuinamente anómalos de bajo impacto (caso real USR0030: P=0.75 muy sospechoso, pero impacto 0.35 → caía a riesgo bajo).
- ➖ "Probabilidad" es un nombre engañoso: los scores IF/LOF **no son probabilidades calibradas**.

### Evidencia de la comparación
| Medida | Valor |
|---|---|
| Spearman (ranking aditivo vs P×I) | 0.857 |
| Conjunto elevado (no-LOW) en común | 17/21 (81%) |
| Diferencia | 4 swaps en el borde: P×I cambia "alta sospecha/bajo impacto" por "moderada sospecha/alto impacto" |

**Conclusión:** el cambio era pequeño en práctica (81% igual) y su valor estaba en el *framing*, no en mejor detección. P×I puro tenía fragilidad real.

### Decisión final — Modelo híbrido (multiplicador de impacto suave)
```
final = base_aditivo × (k + (1-k) × impacto)     con k = 0.7
```
Hereda el framing defendible "riesgo ~ probabilidad × impacto" **sin la fragilidad multiplicativa**. El impacto solo amortigua (hasta 30%) a usuarios de baja criticidad; nunca colapsa el score a cero.

**Por qué k = 0.7:**
- k < 0.7 → entierra comportamiento anómalo de bajo impacto (USR0030 caería a LOW).
- k > 0.7 → casi no modula.
- k = 0.7 → punto de equilibrio: Spearman ~0.99 con el aditivo, retiene USR0030 como MEDIUM.

---

## 5. Factor de Impacto (blast radius)

`impacto ∈ [0, 1]` mide **qué tan dañino sería si el usuario estuviera comprometido**.

```
crit_map = {LOW:0.25, MEDIUM:0.5, HIGH:0.75, VERY_HIGH:1.0}
i_max     = max(criticidad del recurso más crítico ACCEDIDO, criticidad del permiso más crítico ASIGNADO)
i_breadth = recuento normalizado de recursos HIGH+ (permisos ∪ accesos)
impacto   = 0.7 × i_max + 0.3 × i_breadth
```

- **0.7 a la criticidad máxima**: el peor activo alcanzable domina el daño potencial.
- **0.3 a la amplitud**: un usuario con muchos recursos HIGH+ tiene mayor superficie que uno con uno solo.
- Combina **permisos (daño potencial) + accesos (exposición observada)** — decisión tomada para capturar el blast radius completo.

---

## 6. Umbrales de categoría

```
LOW:        score ≤ 28
MEDIUM:  28 < score ≤ 46
HIGH:    46 < score ≤ 64
VERY_HIGH:  score > 64
```

**Recalibrados** tras la modulación de impacto (el multiplicador ≤1 baja todos los scores). Los cortes se ubicaron en **gaps naturales** de la distribución:
- **64** cae en el gap grande 73→50 que aísla el top claro de 6 usuarios.
- **28** cae bajo el cluster denso ~31→27.

Precedente: bandas de severidad de **CVSS v3.1** y escala semicuantitativa 0–100 de **NIST SP 800-30**.

**Funnel resultante:** 6 VERY_HIGH / 2 HIGH / 16 MEDIUM / 476 LOW.

---

## 7. Señales explicativas (`top_signals`)

Cada usuario recibe señales legibles de **dos ejes**:
- **Probabilidad**: reglas disparadas (R1–R7) + top-2 features ML más desviadas de la media poblacional (z > 1).
- **Impacto**: marca de blast radius si `i_max ≥ 0.75` ("alto/máximo blast radius").

Ejemplo (USR0010):
```json
["R2: inactive user has active access logs",
 "ML: elevated after-hours access ratio (00-05h)",
 "ML: anomalous action diversity pattern",
 "Impact: máximo blast radius (recursos VERY_HIGH)"]
```

---

## 8. Validación del modelo (notebook 02)

Como es **no supervisado**, no hay ground truth. Se validó con métricas que no requieren etiquetas reales:

| Métrica | IF-solo | Ensemble | Lectura |
|---|---|---|---|
| Stability top-20 (Jaccard entre seeds) | 0.67 | **0.88** | El ensemble es más reproducible (LOF/Z deterministas anclan 2/3) |
| Stability full (Spearman entre seeds) | 0.99 | 1.00 | Ranking casi determinista |
| Lift@5% (concentración de rule-flagged vs azar) | 3.70x | 3.70x | Sigue concentrando casos conocidos 3.7× sobre el azar |
| Consenso multi-método (IF/LOF/Zscore en top-25) | — | 13/25 | Detecciones robustas a la elección de algoritmo |

> Métricas descartadas en el camino: **Precision@K** (penalizaba la independencia entre capas), **Score Gap** (tautológico — datos aleatorios dan el mismo valor), **Complementarity** (estaba al revés: un modelo aleatorio puntuaba mejor).

---

## 9. Análisis de sensibilidad — los pesos no son "load-bearing" (notebook 03)

Como los pesos (R1–R7) y los umbrales son juicio experto, se probó empíricamente que el ranking **no depende de los valores exactos**. Ver `notebooks/03_weight_sensitivity.ipynb`.

### 9.1 Monte Carlo — perturbar TODOS los pesos a la vez
Cada peso se multiplica por un factor aleatorio en [1−p, 1+p], 500 corridas:

| Perturbación | Spearman ranking | Jaccard top-20 (media) |
|---|---|---|
| ±30% | 0.9999 | 0.86 |
| **±50%** | **0.9998** | **0.81** |

Aun moviendo todos los pesos ±50% simultáneamente, el ranking completo es casi idéntico y el top-20 conserva el 81% → los números no son *load-bearing*.

### 9.2 One-at-a-time — qué peso individual importa
Variando cada peso de 0.5× a 1.5× (resto fijo), menor Jaccard top-20:

| Peso variado | Jaccard mín top-20 |
|---|---|
| external_insider (R7) | 0.74 |
| external_very_high_no_exp (R5) | 0.74 |
| expired_perm_access (R3) | 0.82 |
| access_without_perm (R1) | 0.91 |
| **inactive_with_access (R2)** | **1.00** |
| **privilege_escalation (R4)** | **1.00** |
| **cross_dept_access (R6)** | **1.00** |

**Hallazgo clave:** los pesos de **máxima confianza** (R2=45, R4=30) **no afectan el top-20 en absoluto** — sus usuarios están saturados muy por encima del umbral. Solo los pesos chicos del borde (R5, R7) tienen efecto marginal. Calibrar finamente los pesos altos es irrelevante.

### 9.3 Sensibilidad de umbrales
Perturbando los cortes ±20%, el conjunto elevado (no-LOW) varía de forma **suave y monótona**:

| Δ umbrales | VERY_HIGH | HIGH | MEDIUM | Elevados |
|---|---:|---:|---:|---:|
| −20% | 6 | 9 | 35 | 50 |
| baseline | 6 | 2 | 16 | 24 |
| +20% | 4 | 2 | 10 | 16 |

Sin saltos bruscos → la calibración no está parada sobre un precipicio.

**Conclusión:** la heurística de pesos se justifica no por la precisión de cada número, sino por la robustez de las conclusiones. Con MITRE (qué detectar) + NIST/CVSS/RBA (cómo combinar y cortar) + esta sensibilidad (robustez), el modelo es defendible end-to-end.

---

## 10. Limitaciones (ordenadas por importancia)

1. **No existe ground truth real** (la más importante). Ningún usuario está etiquetado como atacante confirmado. Todas las métricas miden *"¿concuerda con las reglas?"*, no *"¿atrapa atacantes reales?"*. Precisión y recall verdaderos son imposibles de conocer.
2. **Evaluación in-sample** (menor, cuantificada). El modelo se entrena y evalúa sobre los mismos 500 usuarios → optimismo leve (lift 3.70x in-sample → 3.11x held-out, ~16%). No se usó train/test split por inestabilidad con dataset chico. Las conclusiones *relativas* (ensemble > IF) no se ven afectadas.
3. **"Impacto" usa criticidad coarse** (4 niveles) y el ML no está calibrado como probabilidad real.

**Mejora futura:** validación con **split temporal** (entrenar baseline con los primeros ~5 meses, detectar sobre los últimos ~2) — simula producción real de un UEBA. Requiere reconstruir features por ventana temporal.

---

## 11. Resumen de parámetros (`conf/base/parameters/risk_scoring.yml`)

| Grupo | Parámetro | Valor |
|---|---|---|
| Isolation Forest | n_estimators / max_features / contamination | 500 / 0.9 / 0.05 |
| Ensemble | lof_n_neighbors / pesos | 20 / 1·1·1 |
| Reglas (pesos) | R1–R7 | 30/45/20/30/15/20/20 |
| Anomaly | anomaly_max_contribution | 40 |
| Impacto | max_weight / breadth_weight / multiplier_floor (k) | 0.7 / 0.3 / 0.7 |
| Umbrales | low / medium / high | 28 / 46 / 64 |

---

## Referencias

- **MITRE ATT&CK for Enterprise** — categorización de técnicas (T1078, T1548, T1098, T1021, T1083, T1119).
- **NIST SP 800-30** — riesgo ~ probabilidad × impacto; escala semicuantitativa 0–100.
- **NIST SP 800-53** — controles AC-2/AC-3/AC-6 (gestión de cuentas y least privilege).
- **FAIR** — Factor Analysis of Information Risk (descomposición cuantitativa).
- **CVSS v3.1** — precedente de bandas de severidad y combinación de sub-scores.
- **Gartner UEBA** — arquitectura de ingesta → features → scoring dinámico.

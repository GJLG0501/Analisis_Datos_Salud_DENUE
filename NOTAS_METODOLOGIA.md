# Notas de metodología — respuestas a las correcciones de Hugo

> Documento de trabajo. Las secciones marcadas ✅ están listas para integrarse al `reporte.tex`.

---

## Punto 4 — Justificación del filtrado de la base ✅

**Base origen:** DENUE 2025 (INEGI), CDMX completo → 88,187 unidades económicas en Iztapalapa, 719 giros.

**Filtro geográfico:** `cve_ent == 9` (CDMX) y `cve_mun == 7` (Iztapalapa).
*(Nota: el reporte dice `cve_mun=10` por error; el código usa 7, que es el correcto.)*

**Filtro temático:** se conservan **6 códigos SCIAN de atención médica general**, tanto pública como privada:

| SCIAN | Descripción | n | Sector |
|---|---|---|---|
| 621111 | Consultorios de medicina general | 448 | Privado |
| 621112 | Consultorios de medicina general | 16 | Público |
| 621115 | Clínicas de consultorios médicos | 28 | Privado |
| 621116 | Clínicas de consultorios médicos | 37 | Público |
| 622111 | Hospitales generales | 16 | Privado |
| 622112 | Hospitales generales | 18 | Público |
| | **Total** | **563** | |

**Criterio de inclusión:** sólo establecimientos que ofrecen **atención médica general sustituible** — un paciente con un padecimiento común puede acudir a cualquiera de ellos. Esto hace que los nodos de la red sean **comparables entre sí**, requisito para que la persistencia homológica mida "vacíos de cobertura" reales.

**Qué se excluyó y por qué** (los giros más grandes que se quitaron de Iztapalapa):

- **Especialidades médicas** (no son sustituibles por atención general):
  - 621211 Consultorios dentales (1,269) — el giro más grande, pero atención dental ≠ médica general.
  - 621113 Medicina especializada (98), 621320 Optometría (147), 621331 Psicología (109), 621311 Quiropráctica (85), 621341 Audiología (68), 621391 Nutrición (23), 622311/622312 Hospitales de otras especialidades.
- **Servicios de apoyo** (no son punto de atención primaria):
  - 621511 Laboratorios médicos y de diagnóstico (86), 621910 Ambulancias (2).
- **Asistencia social** (no son atención médica):
  - 624191 Grupos de autoayuda (276), 624112/624199 Trabajo social, 624411/624412 Guarderías, 623311/623221 Asilos y residencias, 624211/624212 Comedores comunitarios.

> Si se incluyeran estos giros, la red mezclaría servicios no comparables (un dentista no "cubre" la demanda de un hospital general) y los huecos H₁ perderían interpretación.

---

## Punto 3 — Cómo se construyó la malla urbana y con base en qué ✅

Tu intuición era correcta: la malla se basa en **actividad económica**, no solo comercial.

**Definición:** una "máscara de actividad urbana" sobre una grilla de 250×250 celdas en el bounding box de Iztapalapa. Una celda es **zona urbana activa** si su distancia al establecimiento DENUE **más cercano de cualquier giro** (los 88,187, no solo salud) es ≤ `r_hab`.

**Justificación de la base:** el DENUE completo (719 giros: tiendas, talleres, servicios, oficinas…) es un **proxy de presencia humana/residencial**. Donde hay actividad económica densa, hay población que demanda servicios. Donde no la hay (Sierra de Santa Catarina, parques, Central de Abastos) no hay demanda residencial, aunque geométricamente parezca un "hueco".

**Justificación del umbral `r_hab = 300 m`:** equivale a ~4 min caminando; es la distancia típica a la que un habitante urbano tiene algún comercio/servicio a la mano. Se reporta sensibilidad a 500 m como cota superior.

**Para qué sirve:** distinguir un hueco H₁ **real** (anillo de hospitales rodeando una zona habitada sin servicio) de un **falso positivo** (anillo rodeando un cerro o un mercado mayorista sin demanda residencial).

---

## Punto 2 — Dónde hay más dispersión: público vs privado ✅ (CORRIGE EL REPORTE)

⚠️ **La tabla "Estadísticas por sector" del reporte tiene números inventados** (dice Público mediana ~800 m; el dato real es 562 m). Reemplazar por esta tabla calculada:

| Métrica | Privado (n=492) | Público (n=71) | Interpretación |
|---|---|---|---|
| Distancia al vecino más cercano (media) | **199 m** | **608 m** | Los públicos están ~3× más separados |
| Distancia al vecino más cercano (mediana) | 170 m | 562 m | |
| **NNI** (índice del vecino más cercano) | **0.831** | **0.964** | Privado más **agrupado**; público casi **aleatorio/uniforme** |
| Distancia media al centroide | 4,226 m | 4,467 m | Cobertura territorial similar |
| CV de la distancia NN | 0.712 | 0.781 | |

> NNI < 1 ⇒ patrón agrupado; NNI ≈ 1 ⇒ aleatorio; NNI > 1 ⇒ disperso/regular.
> Área de Iztapalapa: 113.1 km².

**Hallazgo (matiz importante para defender ante Hugo):** "dispersión" tiene dos lecturas y conviene ser explícitos:

1. **Por separación absoluta entre unidades** → el sector **público** está más disperso (608 m vs 199 m): pocas unidades muy repartidas.
2. **Por irregularidad/heterogeneidad del patrón (NNI)** → el sector **privado** se aleja más del azar hacia el **agrupamiento** (NNI 0.831): forma **conglomerados densos** en ciertas colonias y deja otras vacías. Es decir, el privado genera la **mayor heterogeneidad espacial** (zonas saturadas vs zonas sin cobertura privada).

**Recomendación de narrativa:** decir que *"el sector privado presenta una distribución más **agrupada y heterogénea** (NNI 0.83): se concentra donde hay poder adquisitivo y deja huecos; el público está más **espaciado pero uniforme** (NNI 0.96), repartido por el territorio aunque con baja densidad"*. Así tu intuición de "más dispersión en privados" es defendible si la enmarcas como **agrupamiento/heterogeneidad**, no como separación.

---

## Correcciones puntuales al reporte.tex (Fase 0)

1. `cve_mun=10` → **`cve_mun=7`** (sección Metodología).
2. Tabla "Estadísticas por sector" → reemplazar por la tabla de arriba (números reales).
3. Frase "La red pública, más dispersa, genera ciclos H₁ de mayor persistencia" → matizar con la doble lectura de dispersión.
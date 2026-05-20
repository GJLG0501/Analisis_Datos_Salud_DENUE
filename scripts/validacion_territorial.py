"""Validacion territorial: mascara de actividad urbana basada en DENUE completo.

Reglas:
  r_hab = 300 m  -> zona urbana activa si dist al DENUE mas cercano <= r_hab
  Clasificacion del candidato/ciclo por % de su disco interior dentro de zona activa:
    >= 60%  -> accionable
    <= 40%  -> falso positivo territorial
    40-60%  -> mixto / requiere revision manual
"""
import pandas as pd
import numpy as np
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from sklearn.neighbors import BallTree
from scipy.ndimage import maximum_filter
from shapely.geometry import Point
from pathlib import Path

figures_dir = Path("outputs/figures")
out_dir     = Path("outputs")

# ---------- Datos medicos (los 563) ----------
df_med = pd.read_csv("outputs/salud_general_iztapalapa_enriquecida.csv", encoding="latin1")
df_med = df_med.dropna(subset=["latitud", "longitud"]).copy()
gdf_med   = gpd.GeoDataFrame(df_med, geometry=gpd.points_from_xy(df_med["longitud"], df_med["latitud"]), crs="EPSG:4326")
gdf_med_m = gdf_med.to_crs("EPSG:32614")
coords_med_m = np.array([(g.x, g.y) for g in gdf_med_m.geometry])

# ---------- DENUE completo CDMX -> filtro Iztapalapa ----------
print("Cargando DENUE completo CDMX...")
df_all = pd.read_csv("data/denue_full/conjunto_de_datos/denue_inegi_09_.csv",
                    encoding="latin1", low_memory=False)
print("Total CDMX: {:,}".format(len(df_all)))

izt_all = df_all[(df_all["cve_ent"] == 9) & (df_all["cve_mun"] == 7)].copy()
izt_all["latitud"]  = pd.to_numeric(izt_all["latitud"],  errors="coerce")
izt_all["longitud"] = pd.to_numeric(izt_all["longitud"], errors="coerce")
izt_all = izt_all.dropna(subset=["latitud", "longitud"])
print("DENUE Iztapalapa (cualquier giro): {:,}".format(len(izt_all)))
print("Giros unicos Iztapalapa: {:,}".format(izt_all["codigo_act"].nunique()))

gdf_all   = gpd.GeoDataFrame(izt_all, geometry=gpd.points_from_xy(izt_all["longitud"], izt_all["latitud"]), crs="EPSG:4326")
gdf_all_m = gdf_all.to_crs("EPSG:32614")
coords_all_m = np.array([(g.x, g.y) for g in gdf_all_m.geometry])

# ---------- Polígono Iztapalapa ----------
alc = gpd.read_file("data/limite-de-las-alcaldas.json", encoding="utf-8").to_crs("EPSG:4326")
izt_poly = alc[alc["NOMGEO"] == "Iztapalapa"].to_crs("EPSG:32614")
boundary_m = izt_poly.union_all() if hasattr(izt_poly, "union_all") else izt_poly.unary_union

# ---------- Grid 250x250 ----------
minx, miny, maxx, maxy = boundary_m.bounds
nx, ny = 250, 250
xs = np.linspace(minx, maxx, nx)
ys = np.linspace(miny, maxy, ny)
xx, yy = np.meshgrid(xs, ys)
grid = np.column_stack([xx.ravel(), yy.ravel()])
inside_mask = np.array([boundary_m.contains(Point(p)) for p in grid])

# ---------- Mascara de actividad urbana ----------
tree_all = BallTree(coords_all_m)
dist_to_any, _ = tree_all.query(grid, k=1)
dist_to_any = dist_to_any.ravel()
dist_grid_any = dist_to_any.reshape(xx.shape).copy()
dist_grid_any.ravel()[~inside_mask] = np.nan

R_HAB_PRIM = 300.0
R_HAB_ALT  = 500.0

mask_urban_300 = (dist_to_any <= R_HAB_PRIM) & inside_mask
mask_urban_500 = (dist_to_any <= R_HAB_ALT)  & inside_mask

print("\n=== Cobertura de la mascara ===")
n_inside = int(inside_mask.sum())
print("Celdas dentro de Iztapalapa: {:,}".format(n_inside))
print("Zona urbana activa @ r_hab=300m: {:,} ({:.1f}%)".format(
    int(mask_urban_300.sum()), 100*mask_urban_300.sum()/n_inside))
print("Zona urbana activa @ r_hab=500m: {:,} ({:.1f}%)".format(
    int(mask_urban_500.sum()), 100*mask_urban_500.sum()/n_inside))

# ---------- Cargar candidatos P1-P5 ----------
cand = pd.read_csv("outputs/propuesta_ubicaciones.csv")
print("\nCandidatos: {} ubicaciones".format(len(cand)))

# Convertir candidatos a UTM
cand_geo = gpd.GeoDataFrame(cand, geometry=gpd.points_from_xy(cand["lon"], cand["lat"]), crs="EPSG:4326").to_crs("EPSG:32614")
cand_xy  = np.array([(g.x, g.y) for g in cand_geo.geometry])

# ---------- Clasificacion: % del disco interior en zona urbana activa ----------
# Para cada candidato P, su "interior" es el disco de radio = dist_hueco_m / 2
# (radio del hueco topologico, aproximacion del ciclo H1 que cierra).
# Muestreamos puntos en el disco y vemos cuantos caen en zona urbana activa.

def clasifica(xy_center, r_disco_m, coords_all_m_for_tree, r_hab, n_samples=600, seed=0):
    rng = np.random.default_rng(seed)
    # Muestreo uniforme en disco
    r_smp = r_disco_m * np.sqrt(rng.uniform(0, 1, n_samples))
    th    = rng.uniform(0, 2*np.pi, n_samples)
    smp   = np.column_stack([xy_center[0] + r_smp*np.cos(th),
                              xy_center[1] + r_smp*np.sin(th)])
    # Solo puntos dentro de Iztapalapa
    inside_smp = np.array([boundary_m.contains(Point(p)) for p in smp])
    if inside_smp.sum() == 0:
        return 0.0, 0.0, 0
    smp_in = smp[inside_smp]
    tree = BallTree(coords_all_m_for_tree)
    d, _ = tree.query(smp_in, k=1)
    activ_frac = float((d.ravel() <= r_hab).mean())
    return activ_frac, float(inside_smp.mean()), int(inside_smp.sum())

zonas = ["Leyes de Reforma 3a Sec.", "Campestre Potrero",
         "Lomas de la Estancia", "Central de Abastos", "San Juan Xalpa"]

print("\n=== CLASIFICACION (r_hab=300m) ===")
results_300 = []
for i, row in cand.iterrows():
    r_disco = row["dist_hueco_m"] * 0.5
    pct, _, n_in = clasifica(cand_xy[i], r_disco, coords_all_m, R_HAB_PRIM)
    if pct >= 0.60:
        cls = "accionable"
    elif pct <= 0.40:
        cls = "falso_positivo"
    else:
        cls = "mixto"
    results_300.append({"id": row["id"], "zona": zonas[i], "persistencia_m": row["dist_hueco_m"],
                        "r_disco_m": r_disco, "pct_urbano": pct*100, "clase": cls,
                        "n_muestras_interior": n_in})
    print("  {}: {} | disco {:.0f}m | %urb={:.1f}% -> {}".format(
        row["id"], zonas[i], r_disco, pct*100, cls.upper()))

print("\n=== CLASIFICACION (r_hab=500m, sensibilidad) ===")
results_500 = []
for i, row in cand.iterrows():
    r_disco = row["dist_hueco_m"] * 0.5
    pct, _, n_in = clasifica(cand_xy[i], r_disco, coords_all_m, R_HAB_ALT)
    if pct >= 0.60:
        cls = "accionable"
    elif pct <= 0.40:
        cls = "falso_positivo"
    else:
        cls = "mixto"
    results_500.append({"id": row["id"], "zona": zonas[i], "pct_urbano_500": pct*100, "clase_500": cls})
    print("  {}: %urb={:.1f}% -> {}".format(row["id"], pct*100, cls.upper()))

# Guardar tabla
tab = pd.DataFrame(results_300)
tab_500 = pd.DataFrame(results_500)
tab = tab.merge(tab_500[["id", "pct_urbano_500", "clase_500"]], on="id")
tab["lat"] = cand["lat"].values
tab["lon"] = cand["lon"].values
tab["cp"]  = cand["cp_cercano"].values
tab.to_csv(out_dir / "validacion_territorial.csv", index=False, encoding="utf-8")
print("\nGuardado: outputs/validacion_territorial.csv")
print(tab.to_string(index=False))

# ============================================================
# FIGURA: Mapa con mascara urbana + candidatos clasificados
# ============================================================
COLOR = {"accionable": "#27AE60", "mixto": "#F39C12", "falso_positivo": "#C0392B"}
SYMBOL = {"accionable": "*", "mixto": "s", "falso_positivo": "X"}

# --- Panel A: mascara urbana ---
fig, axes = plt.subplots(1, 2, figsize=(16, 8))

ax = axes[0]
izt_poly.plot(ax=ax, facecolor="#FAFAFA", edgecolor="#2C3E50", linewidth=2)

# Pintar mascara
urban_grid = np.full(xx.shape, np.nan)
urban_grid.ravel()[mask_urban_300] = 1.0
ax.pcolormesh(xx, yy, urban_grid, cmap=ListedColormap(["#A8E6CF"]), shading="auto",
              alpha=0.7, zorder=1)
# Puntos DENUE en gris claro de fondo
ax.scatter(coords_all_m[:,0], coords_all_m[:,1], s=2, color="#7F8C8D", alpha=0.35, zorder=2)
# Puntos médicos
ax.scatter(coords_med_m[:,0], coords_med_m[:,1], s=12, color="#2980B9", alpha=0.85, zorder=3,
           label="Establecimientos médicos (n=563)")
# Candidatos clasificados
for i, r in enumerate(results_300):
    c = cand_xy[i]
    ax.scatter(c[0], c[1], s=380, marker=SYMBOL[r["clase"]],
               color=COLOR[r["clase"]], edgecolors="black", linewidths=1.6, zorder=5)
    ax.annotate(r["id"], (c[0], c[1]), xytext=(11, 11), textcoords="offset points",
                fontsize=11, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="black", lw=0.6))
ax.set_title("Máscara de actividad urbana (r_hab = 300 m)\n"
             "Verde claro: zona urbana activa según DENUE completo",
             fontsize=12, fontweight="bold")
ax.set_xlabel("X UTM (m)"); ax.set_ylabel("Y UTM (m)")
ax.set_aspect("equal")
ax.legend(loc="lower left", fontsize=9, framealpha=0.95)

# Leyenda de clasificación
from matplotlib.lines import Line2D
handles = [
    Line2D([0],[0], marker="*", color="w", markerfacecolor=COLOR["accionable"], markersize=15,
           markeredgecolor="black", label="Accionable (≥60% urbano)"),
    Line2D([0],[0], marker="s", color="w", markerfacecolor=COLOR["mixto"], markersize=12,
           markeredgecolor="black", label="Mixto (40-60%)"),
    Line2D([0],[0], marker="X", color="w", markerfacecolor=COLOR["falso_positivo"], markersize=12,
           markeredgecolor="black", label="Falso positivo (≤40%)"),
]
ax.legend(handles=[*ax.get_legend().legend_handles, *handles], loc="lower left",
          fontsize=8, framealpha=0.95)

# --- Panel B: distancia al DENUE mas cercano (gradiente) ---
ax = axes[1]
izt_poly.plot(ax=ax, facecolor="#FAFAFA", edgecolor="#2C3E50", linewidth=2)
cf = ax.contourf(xx, yy, dist_grid_any, levels=20, cmap="RdYlGn_r", alpha=0.8)
cbar = plt.colorbar(cf, ax=ax, shrink=0.7, label="Distancia al DENUE más cercano (m)")
# Línea de umbral 300m
ax.contour(xx, yy, dist_grid_any, levels=[R_HAB_PRIM], colors="black", linewidths=1.4, linestyles="--")

for i, r in enumerate(results_300):
    c = cand_xy[i]
    ax.scatter(c[0], c[1], s=380, marker=SYMBOL[r["clase"]],
               color=COLOR[r["clase"]], edgecolors="black", linewidths=1.6, zorder=5)
    ax.annotate(r["id"], (c[0], c[1]), xytext=(11, 11), textcoords="offset points",
                fontsize=11, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="black", lw=0.6))
ax.set_title("Distancia a cualquier giro DENUE\n"
             "(línea punteada = umbral r_hab = 300 m)",
             fontsize=12, fontweight="bold")
ax.set_xlabel("X UTM (m)"); ax.set_ylabel("Y UTM (m)")
ax.set_aspect("equal")

plt.suptitle("Validación territorial de candidatos P1–P5", fontsize=14, fontweight="bold", y=1.01)
plt.tight_layout()
plt.savefig(figures_dir / "22_validacion_territorial.png", dpi=200, bbox_inches="tight")
plt.close()
print("\nOK: 22_validacion_territorial.png")

# ============================================================
# FIGURA extra: comparacion 300m vs 500m
# ============================================================
fig, axes = plt.subplots(1, 2, figsize=(16, 8))
for ax, mask, rh in [(axes[0], mask_urban_300, 300), (axes[1], mask_urban_500, 500)]:
    izt_poly.plot(ax=ax, facecolor="#FAFAFA", edgecolor="#2C3E50", linewidth=2)
    ug = np.full(xx.shape, np.nan); ug.ravel()[mask] = 1.0
    ax.pcolormesh(xx, yy, ug, cmap=ListedColormap(["#A8E6CF"]), shading="auto",
                  alpha=0.75, zorder=1)
    ax.scatter(coords_all_m[:,0], coords_all_m[:,1], s=1.5, color="#7F8C8D", alpha=0.3, zorder=2)
    for i, r in enumerate(results_300):
        c = cand_xy[i]
        cls = r["clase"] if rh == 300 else results_500[i]["clase_500"]
        ax.scatter(c[0], c[1], s=380, marker=SYMBOL[cls],
                   color=COLOR[cls], edgecolors="black", linewidths=1.6, zorder=5)
        ax.annotate(r["id"], (c[0], c[1]), xytext=(10, 10), textcoords="offset points",
                    fontsize=10, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="black", lw=0.5))
    pct_cov = 100*mask.sum()/inside_mask.sum()
    ax.set_title("r_hab = {} m  —  cobertura {:.1f}% del territorio".format(rh, pct_cov),
                 fontsize=12, fontweight="bold")
    ax.set_xlabel("X UTM (m)"); ax.set_ylabel("Y UTM (m)")
    ax.set_aspect("equal")

plt.suptitle("Sensibilidad de la máscara urbana al umbral r_hab",
             fontsize=13, fontweight="bold", y=1.01)
plt.tight_layout()
plt.savefig(figures_dir / "23_sensibilidad_rhab.png", dpi=200, bbox_inches="tight")
plt.close()
print("OK: 23_sensibilidad_rhab.png")

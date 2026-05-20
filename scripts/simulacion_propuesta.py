"""Simulacion: ubicar nuevas unidades de salud en centros de huecos H1."""
import pandas as pd
import numpy as np
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.neighbors import BallTree
from scipy.ndimage import maximum_filter
from shapely.geometry import Point
from ripser import ripser
from pathlib import Path

figures_dir = Path("outputs/figures")

df = pd.read_csv("outputs/salud_general_iztapalapa_enriquecida.csv", encoding="latin1")
df["latitud"]  = pd.to_numeric(df["latitud"],  errors="coerce")
df["longitud"] = pd.to_numeric(df["longitud"], errors="coerce")
df = df.dropna(subset=["latitud", "longitud"]).copy()

gdf   = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["longitud"], df["latitud"]), crs="EPSG:4326")
gdf_m = gdf.to_crs("EPSG:32614")
coords_m = np.array([(g.x, g.y) for g in gdf_m.geometry])

alcaldias    = gpd.read_file("data/limite-de-las-alcaldas.json", encoding="utf-8").to_crs("EPSG:4326")
iztapalapa   = alcaldias[alcaldias["NOMGEO"] == "Iztapalapa"]
iztapalapa_m = iztapalapa.to_crs("EPSG:32614")
boundary_m   = iztapalapa_m.union_all() if hasattr(iztapalapa_m, "union_all") else iztapalapa_m.unary_union

# Grid + distancia
minx, miny, maxx, maxy = boundary_m.bounds
nx, ny = 250, 250
xs = np.linspace(minx, maxx, nx)
ys = np.linspace(miny, maxy, ny)
xx, yy = np.meshgrid(xs, ys)
grid = np.column_stack([xx.ravel(), yy.ravel()])

inside_mask = np.array([boundary_m.contains(Point(p)) for p in grid])
print("Grid total: {} | dentro: {}".format(len(grid), inside_mask.sum()))

tree = BallTree(coords_m)
dist_all, _ = tree.query(grid, k=1)
dist_grid = dist_all.ravel().reshape(xx.shape).copy()
out_idx = np.where(~inside_mask)[0]
dist_grid.ravel()[out_idx] = -np.inf

local_max = (dist_grid == maximum_filter(dist_grid, size=25)) & (dist_grid > 400)
cand_x = xx[local_max]; cand_y = yy[local_max]; cand_d = dist_grid[local_max]
order  = np.argsort(-cand_d); TOP_N = 5
cand_x, cand_y, cand_d = cand_x[order][:TOP_N], cand_y[order][:TOP_N], cand_d[order][:TOP_N]
candidates_m = np.column_stack([cand_x, cand_y])

cand_gdf = gpd.GeoDataFrame(geometry=gpd.points_from_xy(cand_x, cand_y), crs="EPSG:32614").to_crs("EPSG:4326")
cand_lat = cand_gdf.geometry.y.values
cand_lon = cand_gdf.geometry.x.values

_, idx_near = tree.query(candidates_m, k=5)

print("\n=== Top candidatos ===")
for i in range(TOP_N):
    nbr_rows = df.iloc[idx_near[i]]
    mode_col = nbr_rows["nomb_asent"].mode()
    colonia = mode_col.iloc[0] if len(mode_col) else nbr_rows["nomb_asent"].iloc[0]
    cp_mode = nbr_rows["cod_postal"].mode()
    cp = int(cp_mode.iloc[0]) if len(cp_mode) else 0
    print("  P{}: lat={:.5f}, lon={:.5f}, hueco={:.0f} m, col={}, CP={}".format(
        i+1, cand_lat[i], cand_lon[i], cand_d[i], colonia, cp))

# Persistencia antes/despues
coords_c   = coords_m - coords_m.mean(axis=0)
res_before = ripser(coords_c, maxdim=1, thresh=5000)
dgm_h1_b   = res_before["dgms"][1]; dgm_h0_b = res_before["dgms"][0]

coords_new   = np.vstack([coords_m, candidates_m])
coords_new_c = coords_new - coords_new.mean(axis=0)
res_after    = ripser(coords_new_c, maxdim=1, thresh=5000)
dgm_h1_a     = res_after["dgms"][1]; dgm_h0_a = res_after["dgms"][0]

pers_b = dgm_h1_b[:,1] - dgm_h1_b[:,0]
pers_a = dgm_h1_a[:,1] - dgm_h1_a[:,0]
umbral_b = pers_b.mean() + pers_b.std()
umbral_a = pers_a.mean() + pers_a.std()
n_sig_b  = int((pers_b >= umbral_b).sum())
n_sig_a  = int((pers_a >= umbral_a).sum())
max_b    = float(pers_b.max())
max_a    = float(pers_a.max())

print("\nH1 ANTES:   total={}, max={:.0f} m, signif={}".format(len(dgm_h1_b), max_b, n_sig_b))
print("H1 DESPUES: total={}, max={:.0f} m, signif={}".format(len(dgm_h1_a), max_a, n_sig_a))
print("Reduccion ciclos signif: {} -> {} ({:.0f}%)".format(n_sig_b, n_sig_a, 100*(n_sig_b-n_sig_a)/n_sig_b))
print("Reduccion persistencia max: {:.0f} -> {:.0f} ({:.0f}%)".format(max_b, max_a, 100*(max_b-max_a)/max_b))

# FIGURA 1: Mapa propuesta
fig, ax = plt.subplots(figsize=(11, 11))
iztapalapa_m.plot(ax=ax, facecolor="#F8F9FA", edgecolor="#2C3E50", linewidth=2)
dmax = float(dist_grid[np.isfinite(dist_grid)].max())
levels = np.linspace(0, dmax, 18)
mask_inf = np.where(np.isfinite(dist_grid), dist_grid, np.nan)
cf = ax.contourf(xx, yy, mask_inf, levels=levels, cmap="YlOrRd", alpha=0.55, zorder=1)
cbar = plt.colorbar(cf, ax=ax, shrink=0.7)
cbar.set_label("Distancia al establecimiento mas cercano (m)")
ax.scatter(coords_m[:,0], coords_m[:,1], s=8, color="#2C3E50", alpha=0.55, zorder=3,
           label="Establecimientos actuales (n={})".format(len(df)))
ax.scatter(candidates_m[:,0], candidates_m[:,1], s=420, marker="*",
           color="#27AE60", edgecolors="black", linewidths=1.6, zorder=5,
           label="Ubicaciones propuestas (n={})".format(TOP_N))
for i, (x, y) in enumerate(candidates_m, 1):
    ax.annotate("P{}".format(i), (x, y), xytext=(12, 12), textcoords="offset points",
                fontsize=12, fontweight="bold", color="#1E8449",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#1E8449", lw=1))
ax.set_title("Propuesta topologica de nuevas unidades de salud en Iztapalapa\n"
             "(centros de los huecos H1 mas persistentes)",
             fontsize=13, fontweight="bold", pad=12)
ax.set_xlabel("X UTM (m)"); ax.set_ylabel("Y UTM (m)")
ax.legend(loc="lower right", fontsize=10, framealpha=0.95)
ax.set_aspect("equal")
plt.tight_layout()
plt.savefig(figures_dir / "20_propuesta_ubicaciones.png", dpi=200, bbox_inches="tight")
plt.close()
print("OK: 20_propuesta_ubicaciones.png")

# FIGURA 2: antes/despues
fig, axes = plt.subplots(1, 2, figsize=(14, 6))
xy_max = max(dgm_h1_b[:,1].max(), dgm_h1_a[:,1].max()) * 1.05
for ax, dgm_h0, dgm_h1, label in [
    (axes[0], dgm_h0_b, dgm_h1_b, "ANTES (n=563)"),
    (axes[1], dgm_h0_a, dgm_h1_a, "DESPUES (n={})".format(563+TOP_N))
]:
    h0_f = dgm_h0[dgm_h0[:,1] < np.inf]
    h1_f = dgm_h1[dgm_h1[:,1] < np.inf]
    ax.plot([0, xy_max], [0, xy_max], "k--", lw=1, alpha=0.4)
    ax.scatter(h0_f[:,0], h0_f[:,1], s=18, color="#2980B9", alpha=0.45, label="H0 ({})".format(len(h0_f)))
    ax.scatter(h1_f[:,0], h1_f[:,1], s=55, color="#E67E22", alpha=0.85,
               marker="D", label="H1 ({})".format(len(h1_f)))
    ax.set_xlim(-50, xy_max); ax.set_ylim(-50, xy_max)
    ax.set_title(label, fontsize=12, fontweight="bold")
    ax.set_xlabel("Nacimiento (m)"); ax.set_ylabel("Muerte (m)")
    ax.legend(fontsize=10, loc="lower right")
    ax.grid(alpha=0.3)
plt.suptitle("Efecto de la propuesta: persistencia maxima H1 {:.0f} m -> {:.0f} m "
             "({:.0f}% reduccion)".format(max_b, max_a, 100*(max_b-max_a)/max_b),
             fontsize=13, fontweight="bold", y=1.02)
plt.tight_layout()
plt.savefig(figures_dir / "21_simulacion_antes_despues.png", dpi=200, bbox_inches="tight")
plt.close()
print("OK: 21_simulacion_antes_despues.png")

# Guardar CSV
colonias, cps = [], []
for i in range(TOP_N):
    nbr_rows = df.iloc[idx_near[i]]
    mode_col = nbr_rows["nomb_asent"].mode()
    col = mode_col.iloc[0] if len(mode_col) else nbr_rows["nomb_asent"].iloc[0]
    cp_mode = nbr_rows["cod_postal"].mode()
    cp = int(cp_mode.iloc[0]) if len(cp_mode) else 0
    colonias.append(col); cps.append(cp)

cand_df = pd.DataFrame({
    "id":  ["P{}".format(i) for i in range(1, TOP_N+1)],
    "lat": cand_lat,
    "lon": cand_lon,
    "dist_hueco_m": cand_d,
    "colonia_cercana": colonias,
    "cp_cercano": cps,
})
cand_df.to_csv("outputs/propuesta_ubicaciones.csv", index=False, encoding="utf-8")
print("\nGuardado: outputs/propuesta_ubicaciones.csv")
print(cand_df.to_string(index=False))

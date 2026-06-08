"""C2 - Acceso a servicios de salud por zona (AGEB) en Iztapalapa.

Para cada AGEB (con poblacion del Censo 2020) calcula la distancia y el
tiempo al establecimiento de salud mas cercano, distinguiendo:
  - HOSPITAL general (34 unidades: codigos 622111/622112)  <- metrica principal
  - cualquier SALUD GENERAL (563 unidades)                 <- atencion primaria

Supuestos acordados:
  - distancia = euclidiana (UTM 14N) x 1.3  (factor de rodeo urbano)
  - tiempo caminando: 4.5 km/h ; tiempo en auto: 20 km/h
  - poblacion: Censo 2020, POBTOT por AGEB (centroide desde DENUE)

Genera: outputs/acceso_por_ageb.csv, resumen en consola y figura.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree

BASE = Path(__file__).resolve().parent.parent
AGEBS = BASE / "outputs" / "agebs_iztapalapa_poblacion.csv"
SALUD = BASE / "outputs" / "salud_general_iztapalapa_enriquecida.csv"
ALCALDIAS = BASE / "data" / "limite-de-las-alcaldas.json"

CODIGOS_HOSPITAL = [622111, 622112]   # hospitales generales
FACTOR_RODEO = 1.3
VEL_CAMINANDO_M_MIN = 4.5 * 1000 / 60   # 75 m/min
VEL_AUTO_M_MIN = 20 * 1000 / 60         # 333.3 m/min


def cargar():
    agebs = pd.read_csv(AGEBS)
    salud = pd.read_csv(SALUD, encoding="latin1").dropna(subset=["latitud", "longitud"])
    g = gpd.GeoDataFrame(
        salud, geometry=gpd.points_from_xy(salud["longitud"], salud["latitud"]),
        crs="EPSG:4326").to_crs("EPSG:32614")
    salud = salud.copy()
    salud["x"] = g.geometry.x.values
    salud["y"] = g.geometry.y.values
    return agebs, salud


def dist_min(orig_xy, dest_xy):
    """Distancia (m, ya con factor de rodeo) de cada origen al destino mas
    cercano, via KDTree euclidiano en metros."""
    tree = cKDTree(dest_xy)
    d, _ = tree.query(orig_xy, k=1)
    return d * FACTOR_RODEO


def tiempos(dist_m):
    return dist_m / VEL_CAMINANDO_M_MIN, dist_m / VEL_AUTO_M_MIN


def pct_poblacion(dist_m, pob, umbral_m):
    """% de poblacion cuyo acceso supera 'umbral_m' metros."""
    return 100.0 * pob[dist_m > umbral_m].sum() / pob.sum()


def mediana_ponderada(valores, pesos):
    orden = np.argsort(valores)
    v, w = np.asarray(valores)[orden], np.asarray(pesos)[orden]
    cum = np.cumsum(w)
    return float(v[np.searchsorted(cum, 0.5 * w.sum())])


def calcular(agebs, salud):
    orig = agebs[["x", "y"]].values
    hosp = salud[salud["codigo_act"].isin(CODIGOS_HOSPITAL)][["x", "y"]].values
    todos = salud[["x", "y"]].values

    out = agebs.copy()
    out["dist_hosp_m"] = dist_min(orig, hosp)
    out["dist_salud_m"] = dist_min(orig, todos)
    out["hosp_caminando_min"], out["hosp_auto_min"] = tiempos(out["dist_hosp_m"])
    out["salud_caminando_min"], out["salud_auto_min"] = tiempos(out["dist_salud_m"])
    return out


def resumen(out):
    pob = out["POBTOT"].values
    total = pob.sum()
    print(f"\nPoblacion analizada: {int(total):,} hab en {len(out)} AGEBs\n")

    for etq, dcol, tcol in [("HOSPITAL general", "dist_hosp_m", "hosp_caminando_min"),
                            ("SALUD general", "dist_salud_m", "salud_caminando_min")]:
        d = out[dcol].values
        t_w = out[tcol].values
        print(f"=== Acceso al {etq} mas cercano ===")
        print(f"  Distancia mediana (pond. poblacion): {mediana_ponderada(d, pob):,.0f} m")
        print(f"  Distancia media   (pond. poblacion): {np.average(d, weights=pob):,.0f} m")
        print(f"  Tiempo caminando mediano: {mediana_ponderada(t_w, pob):.1f} min")
        print(f"  Poblacion a >15 min caminando: {pct_poblacion(t_w*VEL_CAMINANDO_M_MIN, pob, 15*VEL_CAMINANDO_M_MIN):.1f}%"
              f"  ({int(pob[t_w>15].sum()):,} hab)")
        print(f"  Poblacion a >30 min caminando: {pct_poblacion(t_w*VEL_CAMINANDO_M_MIN, pob, 30*VEL_CAMINANDO_M_MIN):.1f}%"
              f"  ({int(pob[t_w>30].sum()):,} hab)")
        print()


def figura(out, salud):
    alc = gpd.read_file(ALCALDIAS).to_crs("EPSG:32614")
    izt = alc[alc["NOMGEO"] == "Iztapalapa"]
    hosp = salud[salud["codigo_act"].isin(CODIGOS_HOSPITAL)]

    fig, ax = plt.subplots(figsize=(10, 9))
    izt.boundary.plot(ax=ax, color="0.4", linewidth=1.0, zorder=1)
    sc = ax.scatter(out["x"], out["y"], c=out["hosp_caminando_min"],
                    s=np.sqrt(out["POBTOT"]) * 1.1, cmap="YlOrRd",
                    edgecolors="0.3", linewidths=0.2, zorder=3, alpha=0.9)
    ax.scatter(hosp["x"], hosp["y"], marker="P", c="navy", s=90,
               edgecolors="white", linewidths=0.6, zorder=5, label="Hospital general (34)")
    cb = fig.colorbar(sc, ax=ax, shrink=0.7)
    cb.set_label("Tiempo caminando al hospital más cercano (min)")
    ax.set_title("Acceso al hospital general por AGEB en Iztapalapa\n"
                 "(tamaño = población; color = minutos caminando)")
    ax.set_aspect("equal"); ax.set_xlabel("X UTM (m)"); ax.set_ylabel("Y UTM (m)")
    ax.legend(loc="upper right", fontsize=9)
    out_png = BASE / "outputs" / "figures" / "25_acceso_hospital_por_ageb.png"
    fig.savefig(out_png, dpi=140, bbox_inches="tight")
    print("figura:", out_png)
    return out_png


def main():
    agebs, salud = cargar()
    out = calcular(agebs, salud)
    resumen(out)
    out.to_csv(BASE / "outputs" / "acceso_por_ageb.csv", index=False, encoding="utf-8")
    print("guardado: outputs/acceso_por_ageb.csv")
    figura(out, salud)


if __name__ == "__main__":
    main()

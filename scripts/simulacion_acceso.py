"""C4 - Antes vs despues: impacto de las unidades propuestas en el acceso.

Simula abrir las ubicaciones propuestas como nuevas unidades PUBLICAS y
mide cuanto mejora el acceso de la poblacion al hospital publico mas cercano.

Escenarios:
  - Conservador: solo accionables P1 + P4 (100% urbano en validacion territorial).
  - Completo:    los 5 candidatos (P1-P5).

Supuesto: cada unidad propuesta cuenta como un hospital/centro publico nuevo.
Reusa C2 (acceso_por_zona): distancia UTM x 1.3, caminando 4.5 km/h.
"""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("c2", BASE / "scripts" / "acceso_por_zona.py")
c2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c2)

HOSP_PUB = [622112]
ACCIONABLES = ["P1", "P4"]


def propuesta_xy(ids=None):
    p = pd.read_csv(BASE / "outputs" / "propuesta_ubicaciones.csv")
    if ids is not None:
        p = p[p["id"].isin(ids)]
    g = gpd.GeoDataFrame(p, geometry=gpd.points_from_xy(p["lon"], p["lat"]),
                         crs="EPSG:4326").to_crs("EPSG:32614")
    return np.column_stack([g.geometry.x.values, g.geometry.y.values]), p


def acceso_publico(orig, pub_xy):
    d = c2.dist_min(orig, pub_xy)
    tw = d / c2.VEL_CAMINANDO_M_MIN
    return d, tw


def stats(tw, pob, dist):
    return {
        "dist_mediana_m": c2.mediana_ponderada(dist, pob),
        "tiempo_mediano_min": c2.mediana_ponderada(tw, pob),
        "pob_mas15": int(pob[tw > 15].sum()),
        "pob_mas30": int(pob[tw > 30].sum()),
        "pct_mas15": 100 * pob[tw > 15].sum() / pob.sum(),
        "pct_mas30": 100 * pob[tw > 30].sum() / pob.sum(),
    }


def main():
    agebs, salud = c2.cargar()
    orig = agebs[["x", "y"]].values
    pob = agebs["POBTOT"].values
    pub = salud[salud["codigo_act"].isin(HOSP_PUB)][["x", "y"]].values

    # ANTES
    d0, tw0 = acceso_publico(orig, pub)
    s0 = stats(tw0, pob, d0)

    escenarios = {"Conservador (P1+P4)": ACCIONABLES, "Completo (P1-P5)": None}
    resultados = {"ANTES": s0}
    tws = {"ANTES": tw0}

    for nombre, ids in escenarios.items():
        prop_xy, _ = propuesta_xy(ids)
        pub_mas = np.vstack([pub, prop_xy])
        d1, tw1 = acceso_publico(orig, pub_mas)
        resultados[nombre] = stats(tw1, pob, d1)
        tws[nombre] = tw1

    # ---- reporte en consola ----
    print(f"\nPoblacion: {int(pob.sum()):,} hab | hospitales publicos actuales: {len(pub)}\n")
    print(f"{'Escenario':<22}{'dist med (m)':>13}{'t med (min)':>12}"
          f"{'>15 min':>16}{'>30 min':>16}")
    for k, s in resultados.items():
        print(f"{k:<22}{s['dist_mediana_m']:>13,.0f}{s['tiempo_mediano_min']:>12.1f}"
              f"{s['pob_mas15']:>10,} ({s['pct_mas15']:>4.1f}%)"
              f"{s['pob_mas30']:>10,} ({s['pct_mas30']:>4.1f}%)")

    print("\n=== Mejora respecto a ANTES ===")
    for k in escenarios:
        s = resultados[k]
        gana15 = s0["pob_mas15"] - s["pob_mas15"]
        gana30 = s0["pob_mas30"] - s["pob_mas30"]
        mejoran = int(pob[(tws[k] < tw0 - 1e-6)].sum())
        print(f"{k}:")
        print(f"  Salen de '>15 min': {gana15:,} personas")
        print(f"  Salen de '>30 min': {gana30:,} personas")
        print(f"  Mejoran su tiempo al publico (cualquier reduccion): {mejoran:,} personas")
        print(f"  Distancia mediana: {s0['dist_mediana_m']:,.0f} -> {s['dist_mediana_m']:,.0f} m")
        print()

    # ---- figura: mapa antes vs despues (escenario completo) ----
    alc = gpd.read_file(BASE / "data" / "limite-de-las-alcaldas.json").to_crs("EPSG:32614")
    izt = alc[alc["NOMGEO"] == "Iztapalapa"]
    prop_xy_all, p_all = propuesta_xy(None)
    acc_xy, _ = propuesta_xy(ACCIONABLES)

    fig, axes = plt.subplots(1, 2, figsize=(15, 7))
    vmax = np.percentile(tw0, 98)
    for ax, (titulo, tw) in zip(axes, [("(a) ANTES", tw0),
                                       ("(b) DESPUES (P1-P5)", tws["Completo (P1-P5)"])]):
        izt.boundary.plot(ax=ax, color="0.4", linewidth=1.0)
        sc = ax.scatter(orig[:, 0], orig[:, 1], c=tw, s=np.sqrt(pob) * 1.0,
                        cmap="YlOrRd", vmin=0, vmax=vmax, edgecolors="0.3",
                        linewidths=0.2, alpha=0.9)
        ax.scatter(pub[:, 0], pub[:, 1], marker="P", c="navy", s=70,
                   edgecolors="white", linewidths=0.5, label="Hospital publico actual")
        if "DESPUES" in titulo:
            ax.scatter(prop_xy_all[:, 0], prop_xy_all[:, 1], marker="*", c="lime",
                       s=320, edgecolors="black", linewidths=0.8, label="Unidad propuesta")
        ax.set_title(titulo); ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
        ax.legend(loc="upper right", fontsize=8)
    fig.colorbar(sc, ax=axes, shrink=0.7).set_label("min caminando al hospital publico")
    fig.suptitle("Impacto de las unidades propuestas en el acceso al hospital publico",
                 fontsize=13)
    out_png = BASE / "outputs" / "figures" / "27_simulacion_acceso_antes_despues.png"
    fig.savefig(out_png, dpi=140, bbox_inches="tight")
    print("figura:", out_png)

    # guardar tabla resumen
    pd.DataFrame(resultados).T.to_csv(BASE / "outputs" / "simulacion_acceso_resumen.csv")
    print("guardado: outputs/simulacion_acceso_resumen.csv")


if __name__ == "__main__":
    main()

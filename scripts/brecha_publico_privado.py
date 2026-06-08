"""C3 - Brecha de acceso publico vs privado por AGEB (eje precio/costo).

El sector publico es gratuito o de cuota social; el privado es de pago.
Donde el hospital PUBLICO mas cercano queda lejos, la poblacion debe
pagar un hospital privado o trasladarse mas lejos por atencion gratuita.
Este script cuantifica esa brecha.

Reusa la logica de C2 (acceso_por_zona): distancia euclidiana UTM x 1.3,
caminando 4.5 km/h y auto 20 km/h, poblacion Censo 2020 por AGEB.
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

# Reusar funciones de C2
_spec = importlib.util.spec_from_file_location("c2", BASE / "scripts" / "acceso_por_zona.py")
c2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c2)

HOSP_PUB = [622112]   # hospital general publico (18)
HOSP_PRIV = [622111]  # hospital general privado (16)


def calcular(agebs, salud):
    orig = agebs[["x", "y"]].values
    pub = salud[salud["codigo_act"].isin(HOSP_PUB)][["x", "y"]].values
    priv = salud[salud["codigo_act"].isin(HOSP_PRIV)][["x", "y"]].values

    out = agebs.copy()
    out["dist_hosp_pub_m"] = c2.dist_min(orig, pub)
    out["dist_hosp_priv_m"] = c2.dist_min(orig, priv)
    out["pub_caminando_min"], out["pub_auto_min"] = c2.tiempos(out["dist_hosp_pub_m"])
    out["priv_caminando_min"], _ = c2.tiempos(out["dist_hosp_priv_m"])
    # sector del hospital mas cercano y penalizacion por buscar el publico
    out["hosp_mas_cercano"] = np.where(
        out["dist_hosp_pub_m"] <= out["dist_hosp_priv_m"], "Publico", "Privado")
    out["penaliza_publico_m"] = (out["dist_hosp_pub_m"]
                                 - out[["dist_hosp_pub_m", "dist_hosp_priv_m"]].min(axis=1))
    return out


def resumen(out):
    pob = out["POBTOT"].values
    total = pob.sum()
    es_priv = out["hosp_mas_cercano"].values == "Privado"
    pob_priv = int(pob[es_priv].sum())

    print(f"\nPoblacion analizada: {int(total):,} hab\n")
    print("=== Hospital mas cercano: que sector ===")
    print(f"  Su hospital mas cercano es PRIVADO (de pago): "
          f"{100*pob_priv/total:.1f}%  ({pob_priv:,} hab)")
    print(f"  Su hospital mas cercano es PUBLICO: "
          f"{100*(total-pob_priv)/total:.1f}%  ({int(total-pob_priv):,} hab)\n")

    print("=== Distancia al hospital PUBLICO (opcion gratuita) ===")
    dpub = out["dist_hosp_pub_m"].values
    twpub = out["pub_caminando_min"].values
    print(f"  Distancia mediana al publico (pond.): {c2.mediana_ponderada(dpub, pob):,.0f} m")
    print(f"  Tiempo caminando mediano al publico: {c2.mediana_ponderada(twpub, pob):.1f} min")
    print(f"  Poblacion a >30 min caminando del hospital PUBLICO: "
          f"{100*pob[twpub>30].sum()/total:.1f}%  ({int(pob[twpub>30].sum()):,} hab)")
    print(f"  Poblacion a >45 min caminando del hospital PUBLICO: "
          f"{100*pob[twpub>45].sum()/total:.1f}%  ({int(pob[twpub>45].sum()):,} hab)\n")

    print("=== Penalizacion por elegir lo gratuito ===")
    # entre quienes tienen un privado mas cerca, cuanto extra caminan al publico
    pen = out.loc[es_priv, "penaliza_publico_m"].values
    pob_p = pob[es_priv]
    if len(pen):
        print(f"  De quienes tienen un privado mas cerca, ir al hospital publico")
        print(f"  cuesta en mediana {c2.mediana_ponderada(pen, pob_p):,.0f} m extra "
              f"(~{c2.mediana_ponderada(pen, pob_p)/c2.VEL_CAMINANDO_M_MIN:.0f} min caminando mas).")
    print()


def figura(out, salud):
    alc = gpd.read_file(BASE / "data" / "limite-de-las-alcaldas.json").to_crs("EPSG:32614")
    izt = alc[alc["NOMGEO"] == "Iztapalapa"]
    pub = salud[salud["codigo_act"].isin(HOSP_PUB)]
    priv = salud[salud["codigo_act"].isin(HOSP_PRIV)]

    fig, axes = plt.subplots(1, 2, figsize=(15, 7))

    # (a) tiempo caminando al hospital PUBLICO
    ax = axes[0]
    izt.boundary.plot(ax=ax, color="0.4", linewidth=1.0)
    sc = ax.scatter(out["x"], out["y"], c=out["pub_caminando_min"],
                    s=np.sqrt(out["POBTOT"]) * 1.0, cmap="YlOrRd",
                    edgecolors="0.3", linewidths=0.2, alpha=0.9)
    ax.scatter(pub["x"], pub["y"], marker="P", c="navy", s=90,
               edgecolors="white", linewidths=0.6, label="Hospital publico (18)")
    fig.colorbar(sc, ax=ax, shrink=0.7).set_label("min caminando al hospital publico")
    ax.set_title("(a) Acceso al hospital PUBLICO (gratuito)")
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    ax.legend(loc="upper right", fontsize=8)

    # (b) que sector es el mas cercano
    ax = axes[1]
    izt.boundary.plot(ax=ax, color="0.4", linewidth=1.0)
    colores = out["hosp_mas_cercano"].map({"Publico": "steelblue", "Privado": "crimson"})
    ax.scatter(out["x"], out["y"], c=colores, s=np.sqrt(out["POBTOT"]) * 1.0,
               edgecolors="0.3", linewidths=0.2, alpha=0.85)
    ax.scatter(pub["x"], pub["y"], marker="P", c="navy", s=70, edgecolors="white",
               linewidths=0.5, label="Hospital publico")
    ax.scatter(priv["x"], priv["y"], marker="X", c="black", s=55, edgecolors="white",
               linewidths=0.5, label="Hospital privado")
    from matplotlib.patches import Patch
    handles = [Patch(facecolor="steelblue", label="publico mas cerca"),
               Patch(facecolor="crimson", label="privado mas cerca (de pago)")]
    ax.legend(handles=handles, loc="upper right", fontsize=8)
    ax.set_title("(b) Hospital mas cercano por AGEB: sector")
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])

    fig.suptitle("Brecha de acceso publico vs privado a hospitales generales, Iztapalapa",
                 fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out_png = BASE / "outputs" / "figures" / "26_brecha_publico_privado.png"
    fig.savefig(out_png, dpi=140, bbox_inches="tight")
    print("figura:", out_png)


def main():
    agebs, salud = c2.cargar()
    out = calcular(agebs, salud)
    resumen(out)
    out.to_csv(BASE / "outputs" / "brecha_publico_privado_ageb.csv", index=False, encoding="utf-8")
    print("guardado: outputs/brecha_publico_privado_ageb.csv")
    figura(out, salud)


if __name__ == "__main__":
    main()

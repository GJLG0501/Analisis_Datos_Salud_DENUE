"""Regenera el diagrama de persistencia (figura 14) mas legible.

Arregla DOS problemas:
  1. Labels rotos: los subindices Unicode (H-cero, H-uno) salian como
     cuadritos. Se usa notacion matematica de matplotlib ($H_0$, $H_1$).
  2. Puntos amontonados: H0 con marcadores pequenos/transparentes, y H1
     coloreados por persistencia con banda de significancia mu+sigma.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ripser import ripser

BASE = Path(__file__).resolve().parent.parent
FIG = BASE / "outputs" / "figures"


def persistencia():
    df = pd.read_csv(BASE / "outputs" / "salud_general_iztapalapa_enriquecida.csv",
                     encoding="latin1").dropna(subset=["latitud", "longitud"])
    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.longitud, df.latitud),
                         crs="EPSG:4326").to_crs("EPSG:32614")
    xy = np.column_stack([g.geometry.x.values, g.geometry.y.values])
    xy = xy - xy.mean(0)
    res = ripser(xy, maxdim=1, thresh=5000)
    return res["dgms"][0], res["dgms"][1]


def main():
    dgm_h0, dgm_h1 = persistencia()
    h0_f = dgm_h0[dgm_h0[:, 1] < np.inf]
    h0_i = dgm_h0[dgm_h0[:, 1] == np.inf]
    h1_f = dgm_h1[dgm_h1[:, 1] < np.inf]
    pers1 = h1_f[:, 1] - h1_f[:, 0]
    mu, sigma = pers1.mean(), pers1.std()
    umbral = mu + sigma

    lim = max(h0_f[:, 1].max(), h1_f[:, 1].max()) * 1.05

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # ---------- panel izquierdo: diagrama de persistencia ----------
    ax = axes[0]
    ax.plot([0, lim], [0, lim], "k--", lw=1, alpha=0.6, zorder=1)
    ax.fill_between([0, lim], [0, lim], [umbral, lim + umbral],
                    color="0.85", alpha=0.6, zorder=0,
                    label=f"Zona de ruido (pers. < {umbral:.0f} m)")

    # H0 finitas: pequenas y transparentes (todas nacen en 0)
    ax.scatter(h0_f[:, 0], h0_f[:, 1], s=10, color="#2980B9", alpha=0.35,
               edgecolors="none", zorder=3, label=f"$H_0$  ({len(h0_f)} componentes)")
    # H0 infinita
    ax.scatter(h0_i[:, 0], [lim * 0.98] * len(h0_i), s=90, color="#C0392B",
               marker="^", zorder=5, label=r"$H_0$  ($\infty$, red conexa)")
    # H1: ruido vs significativo (color por persistencia)
    sig = pers1 >= umbral
    ax.scatter(h1_f[~sig, 0], h1_f[~sig, 1], s=28, color="#E8B796", marker="D",
               edgecolors="0.4", linewidths=0.3, alpha=0.8, zorder=4,
               label=f"$H_1$  ruido ({int((~sig).sum())})")
    sc = ax.scatter(h1_f[sig, 0], h1_f[sig, 1], s=70, c=pers1[sig], cmap="autumn_r",
                    marker="D", edgecolors="black", linewidths=0.6, zorder=6,
                    label=f"$H_1$  significativo ({int(sig.sum())})")
    cb = fig.colorbar(sc, ax=ax, shrink=0.8, pad=0.02)
    cb.set_label("Persistencia $H_1$ (m)", fontsize=9)

    top3 = np.argsort(-pers1)[:3]
    for rank, idx in enumerate(top3):
        b, d = h1_f[idx]
        ax.annotate(f"C{rank+1} ({d-b:.0f} m)", (b, d), xytext=(b + 80, d + 70),
                    fontsize=8.5, color="#A0340A", fontweight="bold",
                    arrowprops=dict(arrowstyle="->", color="#A0340A", lw=0.9))

    ax.set_xlabel("Nacimiento (radio de filtración, m)", fontsize=11)
    ax.set_ylabel("Muerte (radio de filtración, m)", fontsize=11)
    ax.set_title("Diagrama de persistencia  $H_0$ y $H_1$", fontsize=12, fontweight="bold")
    ax.legend(fontsize=8, loc="lower right", framealpha=0.92)
    ax.set_xlim(-50, lim)
    ax.set_ylim(-50, lim)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.25)

    # ---------- panel derecho: ranking de persistencias ----------
    ax2 = axes[1]
    ps = np.sort(pers1)[::-1]
    colores = ["#D35400" if p >= umbral else "#E8B796" for p in ps]
    ax2.bar(range(len(ps)), ps, color=colores, edgecolor="white", lw=0.3)
    ax2.axhline(umbral, color="red", ls="--", lw=1.5,
                label=fr"Umbral significancia ($\mu+\sigma$ = {umbral:.0f} m)")
    ax2.set_xlabel("Ciclo $H_1$ (ordenado por persistencia)", fontsize=11)
    ax2.set_ylabel("Persistencia (muerte $-$ nacimiento, m)", fontsize=11)
    ax2.set_title(f"Persistencia de ciclos $H_1$\n({int(sig.sum())} significativos de {len(pers1)})",
                  fontsize=12, fontweight="bold")
    ax2.legend(fontsize=9)
    ax2.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    out = FIG / "14_diagrama_persistencia_mejorado.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print("guardada:", out)
    print(f"H1: {len(pers1)} ciclos | significativos (>{umbral:.0f} m): {int(sig.sum())} "
          f"| top3 persistencias: {np.round(np.sort(pers1)[::-1][:3]).tolist()}")


if __name__ == "__main__":
    main()

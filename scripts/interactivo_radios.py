"""Demo interactivo: filtracion de Vietoris-Rips con radio movil.

Arrastra el slider de radio r y observa en vivo:
  - las BOLAS de radio r/2 alrededor de cada establecimiento (cobertura),
  - las ARISTAS que conectan pares a distancia <= r (complejo VR),
  - los contadores de componentes conexas (H0) y ciclos/huecos del grafo.

Es la version "pizarron" del analisis topologico: ver como, al crecer el
radio, los puntos se fusionan (baja H0) y se forman/cierran anillos (H1).

Uso:
    python scripts/interactivo_radios.py
(abre una ventana interactiva; requiere entorno grafico / Tkinter)
"""
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib

# OJO: NO fijamos el backend al importar. Si lo hiciéramos (p.ej. TkAgg),
# se anularía el "%matplotlib inline" del notebook y las figuras saldrían
# en ventanas aparte (o en blanco). El backend Tk se activa solo en main().
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, CheckButtons
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.patches import Circle
from scipy.spatial.distance import pdist, squareform
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

# Rutas relativas a la raiz del proyecto (ejecutar desde ahi).
BASE = Path(__file__).resolve().parent.parent
DATA_CSV = BASE / "outputs" / "salud_general_iztapalapa_enriquecida.csv"
ALCALDIAS = BASE / "data" / "limite-de-las-alcaldas.json"

CODIGOS_PUBLICOS = [621112, 621116, 622112]


def cargar_datos():
    """Carga los 563 establecimientos proyectados a metros (UTM 14N) y
    el limite de Iztapalapa en el mismo CRS."""
    df = pd.read_csv(DATA_CSV, encoding="latin1")
    df = df.dropna(subset=["latitud", "longitud"]).copy()
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["longitud"], df["latitud"]),
        crs="EPSG:4326",
    ).to_crs("EPSG:32614")
    xy = np.column_stack([gdf.geometry.x.values, gdf.geometry.y.values])
    es_pub = df["codigo_act"].isin(CODIGOS_PUBLICOS).values

    alc = gpd.read_file(ALCALDIAS).to_crs("EPSG:32614")
    izt = alc[alc["NOMGEO"] == "Iztapalapa"]
    return xy, es_pub, izt


def precomputar_pares(xy):
    """Ordena todos los pares de puntos por distancia para poder filtrar
    rapidamente las aristas con d <= r en cada actualizacion del slider."""
    d = squareform(pdist(xy))
    iu = np.triu_indices(len(xy), k=1)
    dist = d[iu]
    orden = np.argsort(dist)
    return dist[orden], iu[0][orden], iu[1][orden]


def estado_en_radio(xy, dist_ord, pi, pj, r):
    """Devuelve aristas, componentes y ciclos del grafo VR a radio r."""
    n = len(xy)
    k = int(np.searchsorted(dist_ord, r, side="right"))
    ei, ej = pi[:k], pj[:k]
    if k > 0:
        g = coo_matrix((np.ones(k), (ei, ej)), shape=(n, n))
        ncomp, labels = connected_components(g, directed=False)
    else:
        ncomp, labels = n, np.arange(n)
    ciclos = k - n + ncomp  # rango de ciclos (primer numero de Betti del grafo)
    segs = np.stack([xy[ei], xy[ej]], axis=1) if k > 0 else np.empty((0, 2, 2))
    return segs, ncomp, ciclos, labels, k


def construir_figura(xy, es_pub, izt, dist_ord, pi, pj, r0=300.0):
    """Arma la figura con slider de radio y casillas para mostrar/ocultar
    bolas y aristas. Devuelve (fig, update) para poder probar update()."""
    fig, ax = plt.subplots(figsize=(9, 9))
    plt.subplots_adjust(left=0.06, right=0.98, bottom=0.20, top=0.93)

    izt.boundary.plot(ax=ax, color="0.4", linewidth=1.0, zorder=1)

    # Puntos coloreados por componente (se recolorean al mover el slider).
    scat = ax.scatter(
        xy[:, 0], xy[:, 1], c="0.2", s=14, zorder=4,
        edgecolors="white", linewidths=0.3,
    )
    # Marca los publicos con borde para distinguirlos.
    ax.scatter(
        xy[es_pub, 0], xy[es_pub, 1], facecolors="none",
        edgecolors="crimson", s=55, linewidths=1.1, zorder=5,
        label="Publico",
    )

    ax.set_aspect("equal")
    ax.set_xlabel("X UTM (m)")
    ax.set_ylabel("Y UTM (m)")
    ax.legend(loc="upper right", fontsize=9)

    estado = {"lc": None, "balls": None}
    mostrar = {"bolas": True, "aristas": True}

    titulo = ax.set_title("")

    def update(r):
        segs, ncomp, ciclos, labels, k = estado_en_radio(
            xy, dist_ord, pi, pj, r
        )
        # recolorear puntos por componente
        scat.set_array(labels % 20)
        scat.set_cmap("tab20")
        scat.set_clim(0, 19)

        # aristas
        if estado["lc"] is not None:
            estado["lc"].remove()
            estado["lc"] = None
        if mostrar["aristas"] and len(segs) > 0:
            estado["lc"] = LineCollection(
                segs, colors="steelblue", linewidths=0.5, alpha=0.5, zorder=2
            )
            ax.add_collection(estado["lc"])

        # bolas de radio r/2
        if estado["balls"] is not None:
            estado["balls"].remove()
            estado["balls"] = None
        if mostrar["bolas"]:
            circles = [Circle((x, y), r / 2.0) for x, y in xy]
            pc = PatchCollection(
                circles, facecolor="orange", alpha=0.06,
                edgecolor="orange", linewidths=0.2, zorder=0,
            )
            estado["balls"] = pc
            ax.add_collection(pc)

        titulo.set_text(
            f"Radio r = {r:,.0f} m   |   componentes H0 = {ncomp}   |   "
            f"aristas = {k:,}   |   ciclos del grafo = {ciclos}"
        )
        fig.canvas.draw_idle()

    # Slider de radio
    ax_r = plt.axes([0.12, 0.08, 0.66, 0.03])
    s_r = Slider(ax_r, "radio r (m)", 0.0, 2500.0, valinit=r0, valstep=10.0)
    s_r.on_changed(update)

    # Casillas para mostrar/ocultar capas
    ax_chk = plt.axes([0.83, 0.04, 0.14, 0.10])
    chk = CheckButtons(ax_chk, ["bolas", "aristas"], [True, True])

    def toggle(label):
        mostrar[label] = not mostrar[label]
        update(s_r.val)

    chk.on_clicked(toggle)

    update(r0)
    return fig, update, s_r, chk


def grid_estatico(xy, es_pub, izt, dist_ord, pi, pj, radios=(150, 300, 700, 1500)):
    """Panel estatico de 4 radios (para vista inline en el notebook o
    figura del reporte). Devuelve la figura."""
    fig, axes = plt.subplots(2, 2, figsize=(11, 11))
    for ax, r in zip(axes.ravel(), radios):
        izt.boundary.plot(ax=ax, color="0.4", linewidth=0.8, zorder=1)
        segs, ncomp, ciclos, labels, k = estado_en_radio(xy, dist_ord, pi, pj, r)
        circles = [Circle((x, y), r / 2.0) for x, y in xy]
        ax.add_collection(PatchCollection(
            circles, facecolor="orange", alpha=0.07,
            edgecolor="orange", linewidths=0.15, zorder=0))
        if len(segs) > 0:
            ax.add_collection(LineCollection(
                segs, colors="steelblue", linewidths=0.4, alpha=0.5, zorder=2))
        ax.scatter(xy[:, 0], xy[:, 1], c=labels % 20, cmap="tab20",
                   s=10, zorder=4, edgecolors="white", linewidths=0.2)
        ax.set_aspect("equal")
        ax.set_title(f"r = {r:,} m   |   H0 = {ncomp}   |   aristas = {k:,}",
                     fontsize=11)
        ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle("Filtracion de Vietoris-Rips al crecer el radio "
                 "(563 establecimientos de salud, Iztapalapa)", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    return fig


def main():
    # Backend interactivo solo al ejecutar como script (ventana arrastrable).
    try:
        matplotlib.use("TkAgg", force=True)
    except Exception:
        pass
    xy, es_pub, izt = cargar_datos()
    dist_ord, pi, pj = precomputar_pares(xy)
    construir_figura(xy, es_pub, izt, dist_ord, pi, pj)
    print("Listo. Mueve el slider 'radio r (m)' en la ventana.")
    plt.show()


if __name__ == "__main__":
    main()

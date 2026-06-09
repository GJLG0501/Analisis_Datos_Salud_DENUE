"""Mapa interactivo (HTML) ANTES vs DESPUES de las unidades propuestas.

Capas conmutables:
  - "Antes": AGEBs coloreados por minutos caminando al hospital publico.
  - "Despues": lo mismo, agregando las propuestas VIABLES como publicas.
  - Centros propuestos distinguidos por clase (validacion territorial):
      accionable (P1,P4)  -> estrella verde
      mixto (P3,P5)       -> estrella naranja (requiere validacion)
      falso positivo (P2) -> X gris: DESCARTADO (sobre la Sierra, no habitado)
  - Contorno de colonias (IECM 2019) y limite de Iztapalapa.
  - Hospitales publicos actuales.

El escenario "despues" excluye P2 (falso positivo territorial): no se
acredita cobertura en zona no habitada.

Salida: outputs/interactivo/mapa_propuesta_antes_despues.html
"""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import Fullscreen
import branca.colormap as cm

BASE = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("c2", BASE / "scripts" / "acceso_por_zona.py")
c2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c2)

HOSP_PUB = [622112]
VMIN, VMAX = 0.0, 40.0

# clase de validacion territorial y estilo por candidato
CLASE = {"P1": "accionable", "P2": "falso_positivo", "P3": "mixto",
         "P4": "accionable", "P5": "mixto"}
ESTILO = {
    "accionable":     ("green",     "star",   "Propuesta accionable (interior 100% urbano)"),
    "mixto":          ("orange",    "star",   "Mixto: requiere validacion de poblacion (accionable a 500 m)"),
    "falso_positivo": ("lightgray", "remove", "DESCARTADO: falso positivo sobre la Sierra de Santa Catarina (no habitado)"),
}
VIABLES = ["P1", "P3", "P4", "P5"]   # se excluye P2 del escenario "despues"


def tiempos_publico(agebs, pub_xy):
    d = c2.dist_min(agebs[["x", "y"]].values, pub_xy)
    return d / c2.VEL_CAMINANDO_M_MIN


def main():
    agebs, salud = c2.cargar()
    pub = salud[salud["codigo_act"].isin(HOSP_PUB)]
    pub_xy = pub[["x", "y"]].values

    # propuestas -> UTM, con clase
    prop = pd.read_csv(BASE / "outputs" / "propuesta_ubicaciones.csv")
    prop["clase"] = prop["id"].map(CLASE)
    gp = gpd.GeoDataFrame(prop, geometry=gpd.points_from_xy(prop.lon, prop.lat),
                          crs="EPSG:4326").to_crs("EPSG:32614")
    prop["x"] = gp.geometry.x.values
    prop["y"] = gp.geometry.y.values
    viables_xy = prop[prop["id"].isin(VIABLES)][["x", "y"]].values

    # tiempos antes / despues (despues = solo viables, sin P2)
    t_antes = tiempos_publico(agebs, pub_xy)
    t_despues = tiempos_publico(agebs, np.vstack([pub_xy, viables_xy]))
    # tiempo a CUALQUIER salud general (incluye consultorios y clinicas)
    t_salud = tiempos_publico(agebs, salud[["x", "y"]].values)
    agebs = agebs.assign(t_antes=t_antes, t_despues=t_despues, t_salud=t_salud)

    pob = agebs["POBTOT"].values
    crit_antes = int(pob[t_antes > 30].sum())
    crit_desp = int(pob[t_despues > 30].sum())
    salen = crit_antes - crit_desp

    # ---- mapa ----
    centro = [agebs["lat"].mean(), agebs["lon"].mean()]
    m = folium.Map(location=centro, zoom_start=12, tiles="CartoDB positron",
                   control_scale=True)
    Fullscreen().add_to(m)
    colormap = cm.LinearColormap(["#1a9850", "#fee08b", "#f46d43", "#a50026"],
                                 vmin=VMIN, vmax=VMAX,
                                 caption="Minutos caminando al hospital publico (verde=cerca, rojo=lejos)")
    colormap.add_to(m)

    # contorno de colonias (IECM) + limite alcaldia
    col = gpd.read_file(BASE / "data" / "colonias" / "colonias_iztapalapa.geojson")
    folium.GeoJson(
        col, name="Contorno de colonias",
        style_function=lambda x: {"color": "#777", "weight": 0.6, "fill": False},
        tooltip=folium.GeoJsonTooltip(fields=["NOMUT"], aliases=["Colonia:"]),
    ).add_to(m)
    alc = gpd.read_file(BASE / "data" / "limite-de-las-alcaldas.json")
    izt_b = alc[alc["NOMGEO"] == "Iztapalapa"].to_crs("EPSG:4326")
    folium.GeoJson(izt_b, name="Limite Iztapalapa",
                   style_function=lambda x: {"color": "#222", "weight": 2, "fill": False}).add_to(m)

    def capa_agebs(col_t, nombre, show):
        fg = folium.FeatureGroup(name=nombre, show=show)
        for _, r in agebs.iterrows():
            folium.CircleMarker(
                location=[r["lat"], r["lon"]],
                radius=2 + np.sqrt(r["POBTOT"]) / 18,
                weight=0, fill=True,
                fill_color=colormap(min(r[col_t], VMAX)), fill_opacity=0.78,
                popup=folium.Popup(
                    f"<b>AGEB {r['ageb']}</b><br>Poblacion: {int(r['POBTOT']):,}<br>"
                    f"Al hospital publico (antes): <b>{r['t_antes']:.0f} min</b><br>"
                    f"Al hospital publico (despues): <b>{r['t_despues']:.0f} min</b><br>"
                    f"A cualquier salud (consultorio/clinica): "
                    f"<b>{r['t_salud']:.0f} min</b>", max_width=230),
            ).add_to(fg)
        fg.add_to(m)

    capa_agebs("t_antes", "① ANTES — lejania al hospital publico", True)
    capa_agebs("t_despues", "② DESPUES (propuestas viables P1,P3,P4,P5)", False)
    capa_agebs("t_salud", "③ Acceso a CUALQUIER salud (consultorios+clinicas)", False)

    # hospitales publicos actuales
    fg_h = folium.FeatureGroup(name="Hospitales publicos actuales (18)", show=True)
    for _, r in pub.iterrows():
        folium.Marker([r["latitud"], r["longitud"]],
                      icon=folium.Icon(color="darkblue", icon="plus-sign"),
                      popup="Hospital publico actual").add_to(fg_h)
    fg_h.add_to(m)

    # consultorios y clinicas (lo que cubre el acceso de la capa ③)
    cons = salud[~salud["codigo_act"].isin([622111, 622112])]
    fg_c = folium.FeatureGroup(name=f"Consultorios y clinicas ({len(cons)})", show=False)
    for _, r in cons.iterrows():
        folium.CircleMarker([r["latitud"], r["longitud"]], radius=1.6, weight=0,
                            fill=True, fill_color="#3a6ea5", fill_opacity=0.55,
                            popup=str(r["tipo_establecimiento"])).add_to(fg_c)
    fg_c.add_to(m)

    # centros propuestos por clase
    fg_p = folium.FeatureGroup(name="Centros propuestos (por clase)", show=True)
    for _, r in prop.iterrows():
        color, icono, desc = ESTILO[r["clase"]]
        if r["id"] in VIABLES:
            folium.Circle([r["lat"], r["lon"]], radius=1000, color="green",
                          weight=1.2, fill=True, fill_color="green",
                          fill_opacity=0.07).add_to(fg_p)
        folium.Marker(
            [r["lat"], r["lon"]],
            icon=folium.Icon(color=color, icon=icono, prefix="fa"),
            popup=folium.Popup(
                f"<b>{r['id']} — {r['colonia_cercana'].title()}</b><br>"
                f"Clase: <b>{r['clase'].replace('_',' ')}</b><br>{desc}<br>"
                f"Hueco H1: {r['dist_hueco_m']:.0f} m", max_width=260),
        ).add_to(fg_p)
    fg_p.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    # recuadro de impacto
    titulo = f"""
    <div style="position: fixed; top: 12px; left: 60px; z-index: 9999;
                background: white; padding: 10px 14px; border-radius: 8px;
                box-shadow: 0 1px 6px rgba(0,0,0,.3); font-family: sans-serif;
                font-size: 13px; max-width: 340px;">
      <b>Acceso al hospital publico — Iztapalapa</b><br>
      Apaga <b>① ANTES</b> y prende <b>② DESPUES</b> (panel derecho) para comparar.<br><br>
      Poblacion a <b>&gt;30 min</b> caminando del hospital publico:<br>
      &nbsp;&nbsp;Antes: <b>{crit_antes:,}</b> ({100*crit_antes/pob.sum():.1f}%)<br>
      &nbsp;&nbsp;Despues: <b>{crit_desp:,}</b> ({100*crit_desp/pob.sum():.1f}%)<br>
      <span style="color:#1a7a1a;"><b>&#9733; {salen:,} personas</b> salen de la zona critica</span>
      <br><br><span style="font-size:11.5px;">Prende <b>③</b> (acceso a cualquier
      salud): el oeste se vuelve <b style="color:#1a9850;">verde</b> &mdash; ya tiene
      consultorios/clinicas a ~3 min, por eso ahi no hace falta un hospital nuevo.</span>
      <br><span style="font-size:11px;color:#666;">P2 se descarta: falso positivo
      sobre la Sierra (no habitado), por eso no cuenta en el "despues".</span>
    </div>"""
    m.get_root().html.add_child(folium.Element(titulo))

    out = BASE / "outputs" / "interactivo" / "mapa_propuesta_antes_despues.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out))
    print("guardado:", out)
    print(f"Antes >30min: {crit_antes:,} | Despues (viables): {crit_desp:,} | salen: {salen:,}")


if __name__ == "__main__":
    main()
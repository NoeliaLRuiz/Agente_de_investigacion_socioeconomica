"""Mapa coroplético de la pobreza monetaria por departamento con la ENAHO 2024.

    uv run .claude/skills/mapeando-enaho/scripts/mapear.py
    uv run .claude/skills/mapeando-enaho/scripts/mapear.py --indicador extrema

Une las cifras con los límites por código, nunca por nombre: ubigeo[:2] de la ENAHO con FIRST_IDDP del GeoJSON,
los dos como texto de dos dígitos. Exige 25 departamentos con dato, con Lima (15) y Callao (07) separados, y
compara la pobreza con la referencia de la Sesión 16. Guarda mapas/<indicador>_departamento.png y
salidas/comparacion_mapa.csv. Si falta la base limpia, pide correr primero la skill limpiando-enaho.
"""
import argparse
import math
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib import patheffects

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[3]
REFERENCIA = AQUI.parent / "referencia" / "pobreza_departamento_2024.csv"
URL_GEOJSON = ("https://raw.githubusercontent.com/d2cml-ai/Data-Science-Python/main/sessions/06-geoespacial/lab/"
               "Data/peru_departamental_simple.geojson")
TOLERANCIA_PP = 0.1
# Rampa secuencial de un solo tono (azul), de claro a oscuro: más pobreza, más oscuro
RAMPA = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
TEXTO, TEXTO_2 = "#0b0b0b", "#52514e"
INDICADORES = {"pobreza": ("pobre", "pobreza monetaria"), "extrema": ("pobre_extremo", "pobreza extrema")}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--indicador", choices=list(INDICADORES), default="pobreza")
    p.add_argument("--anio", type=int, default=2024)
    p.add_argument("--geojson", type=Path, default=RAIZ / "datos" / "peru_departamental_simple.geojson")
    p.add_argument("--salidas", type=Path, default=RAIZ / "salidas")
    p.add_argument("--mapas", type=Path, default=RAIZ / "mapas")
    a = p.parse_args()
    variable, nombre = INDICADORES[a.indicador]

    base = a.salidas / f"hogares_{a.anio}.parquet"
    if not base.exists():
        sys.exit(f"ERROR: falta salidas/{base.name}. Usa primero la skill limpiando-enaho "
                 f"(uv run .claude/skills/limpiando-enaho/scripts/limpiar.py --anio {a.anio}).")
    if not a.geojson.exists():
        sys.exit(f"ERROR: falta {a.geojson.name} en datos/. Bájenlo de {URL_GEOJSON}")

    # Cifras por departamento, ponderadas como el INEI (hogares, factor07 × mieperho)
    h = pd.read_parquet(base)
    h["_num"] = h[variable] * h.peso_personas
    g = h.groupby("departamento")
    cifras = pd.DataFrame({"pct": g._num.sum() / g.peso_personas.sum() * 100,
                           "nombre": g.departamento_nombre.first(), "n_hogares": g.size()}).reset_index()

    # Unión por código oficial, como texto de dos dígitos
    geo = gpd.read_file(a.geojson)
    geo["departamento"] = geo.FIRST_IDDP.astype(str).str.strip().str.zfill(2)
    mapa = geo.merge(cifras, on="departamento", how="left", validate="1:1")
    errores = []
    if len(mapa) != 25 or mapa.departamento.nunique() != 25:
        errores.append(f"el mapa tiene {mapa.departamento.nunique()} códigos, no 25")
    if mapa.pct.isna().any():
        errores.append("departamentos sin dato: " + ", ".join(mapa.loc[mapa.pct.isna(), "NOMBDEP"]))
    if not {"07", "15"} <= set(mapa.departamento):
        errores.append("Lima (15) y Callao (07) deben estar separados")
    sobran = sorted(set(cifras.departamento) - set(mapa.departamento))
    if sobran:
        errores.append(f"códigos de la ENAHO sin geometría: {', '.join(sobran)}")
    if errores:
        sys.exit("ERROR en la unión territorial: " + "; ".join(errores))

    # Comparación con la referencia de la Sesión 16 (solo existe para la pobreza monetaria 2024)
    if a.indicador == "pobreza" and a.anio == 2024:
        ref = pd.read_csv(REFERENCIA, dtype={"ccdd": str}).rename(
            columns={"departamento": "nombre_referencia", "ccdd": "departamento", "pobreza_pct": "referencia"})
        comp = cifras.merge(ref[["departamento", "referencia"]], on="departamento", how="outer",
                            validate="1:1", indicator=True)
        comp["calculado"] = comp.pct.round(1)
        comp["diferencia"] = (comp.calculado - comp.referencia).round(2) + 0.0     # + 0.0 evita «-0.0»
        comp["coincide"] = comp.diferencia.abs() <= TOLERANCIA_PP
        a.salidas.mkdir(exist_ok=True)
        comp[["departamento", "nombre", "calculado", "referencia", "diferencia", "coincide", "n_hogares"]].to_csv(
            a.salidas / "comparacion_mapa.csv", index=False, encoding="utf-8")
        malos = comp[~comp.coincide | (comp._merge != "both")]
        print(f"Comparación con la referencia de la Sesión 16: {comp.coincide.sum()} de {len(comp)} departamentos "
              f"coinciden (tolerancia ±{TOLERANCIA_PP} pp; diferencia máxima {comp.diferencia.abs().max():.2f} pp). "
              "Detalle en salidas/comparacion_mapa.csv")
        if not malos.empty:
            sys.exit("ERROR: no coinciden con la referencia: " + ", ".join(malos.nombre.astype(str)))

    # Mapa
    tope = math.ceil(mapa.pct.max() / 10) * 10
    cmap = LinearSegmentedColormap.from_list("azul", RAMPA)
    norma = Normalize(vmin=0, vmax=tope)
    fig = plt.figure(figsize=(7.2, 9.6), dpi=200)
    ax = fig.add_axes((0.02, 0.07, 0.8, 0.83))           # el mapa
    cax = fig.add_axes((0.84, 0.3, 0.025, 0.36))         # la barra de colores, con espacio para su texto
    mapa.plot(column="pct", cmap=cmap, norm=norma, edgecolor="white", linewidth=0.6, ax=ax)
    for _, f in mapa.iterrows():
        punto = f.geometry.representative_point()
        color = "white" if norma(f.pct) > 0.55 else TEXTO
        if f.departamento == "07":          # Callao es muy pequeño: etiqueta afuera, en el mar
            ax.annotate(f"Callao\n{f.pct:.1f} %", (punto.x, punto.y), xytext=(-78.9, -12.3), fontsize=6.5,
                        color=TEXTO, ha="right", va="center",
                        arrowprops={"arrowstyle": "-", "color": TEXTO_2, "linewidth": 0.6})
            continue
        borde = "#184f95" if color == "white" else "white"   # halo para que los límites no tapen la cifra
        ax.text(punto.x, punto.y, f"{f.pct:.1f}", fontsize=6.5, color=color, ha="center", va="center",
                path_effects=[patheffects.withStroke(linewidth=2, foreground=borde)])
    ax.set_axis_off()
    barra = fig.colorbar(plt.cm.ScalarMappable(norm=norma, cmap=cmap), cax=cax)
    barra.set_label(f"% de personas en {nombre}", fontsize=8.5, color=TEXTO_2)
    barra.ax.tick_params(labelsize=7.5, colors=TEXTO_2)
    barra.outline.set_visible(False)
    top = mapa.nlargest(3, "pct")
    baja = mapa.nsmallest(1, "pct").iloc[0]
    fig.text(0.04, 0.975, f"{top.nombre.iloc[0]} ({top.pct.iloc[0]:.1f} %), {top.nombre.iloc[1]} y "
                          f"{top.nombre.iloc[2]} tienen la mayor {nombre};", fontsize=11, color=TEXTO, va="top")
    fig.text(0.04, 0.951, f"{baja.nombre} la menor ({baja.pct:.1f} %)", fontsize=11, color=TEXTO, va="top")
    fig.text(0.04, 0.925, f"% de personas en {nombre} por departamento, Perú, {a.anio}. Lima y Callao por separado.",
             fontsize=8.5, color=TEXTO_2, va="top")
    fig.text(0.04, 0.02, f"Fuente: INEI, ENAHO {a.anio} (sumaria), ponderado con factor07 × mieperho. Límites "
                         "departamentales: repositorio del curso\n(peru_departamental_simple.geojson), unidos por "
                         "código (ubigeo[:2] = FIRST_IDDP). Elaboración propia.", fontsize=6.5, color=TEXTO_2)
    a.mapas.mkdir(exist_ok=True)
    archivo = a.mapas / f"{a.indicador}_departamento.png"
    fig.savefig(archivo, facecolor="white")
    plt.close(fig)

    print(f"{archivo.relative_to(RAIZ).as_posix()}: 25 departamentos unidos por código, sin faltantes.")
    tabla = mapa[["departamento", "nombre", "pct"]].sort_values("pct", ascending=False)
    print(tabla.assign(pct=tabla.pct.astype(float).round(2)).to_string(index=False))


if __name__ == "__main__":
    main()

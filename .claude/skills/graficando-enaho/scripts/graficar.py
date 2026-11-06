"""Gráficos de pobreza monetaria con la ENAHO 2024 limpia, siempre con estimaciones ponderadas.

    uv run .claude/skills/graficando-enaho/scripts/graficar.py --por area sexo edad departamento
    uv run .claude/skills/graficando-enaho/scripts/graficar.py --por departamento --indicador extrema

Usa la base de hogares (factor07 × mieperho, como el INEI) para área y departamento, y la de personas
(facpob07) para sexo y edad. Guarda figuras/enaho_<indicador>_<por>.png a 200 dpi e imprime las cifras.
Si falta la base limpia, termina con un error que pide correr primero la skill limpiando-enaho.
"""
import argparse
import sys
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

RAIZ = Path(__file__).resolve().parents[4]
AZUL, TEXTO, TEXTO_2, GRILLA = "#2a78d6", "#0b0b0b", "#52514e", "#e4e3df"
INDICADORES = {"pobreza": ("pobre", "pobreza monetaria"), "extrema": ("pobre_extremo", "pobreza extrema")}
GRUPOS = {  # por: (base, columna, ponderador, orden de las categorías)
    "area": ("hogares", "area", "peso_personas", ["Urbana", "Rural"]),
    "sexo": ("personas", "sexo", "facpob07", ["Hombre", "Mujer"]),
    "edad": ("personas", "grupo_edad", "facpob07",
             ["0 a 14 años", "15 a 29 años", "30 a 44 años", "45 a 59 años", "60 años a más"]),
    "departamento": ("hogares", "departamento_nombre", "peso_personas", None),
}


def tasas(df, col, peso, variable):
    """Porcentaje ponderado por categoría: suma de pesos de los pobres entre la suma de pesos."""
    g = df.assign(_num=df[variable] * df[peso]).groupby(col, observed=True)
    return (g._num.sum() / g[peso].sum() * 100).rename("pct")


def titulo(por, t, nombre):
    """Un título que dice qué muestra el gráfico, con las cifras que salen de los datos."""
    if por == "area":
        alta, baja = t.idxmax(), t.idxmin()
        return (f"La {nombre} {alta.lower()} ({t[alta]:.1f} %) supera a la {baja.lower()} "
                f"({t[baja]:.1f} %) en {t[alta] - t[baja]:.1f} puntos")
    if por == "sexo":
        m, h = t["Mujer"], t["Hombre"]
        if abs(m - h) < 1:
            return f"La {nombre} es casi igual en mujeres ({m:.1f} %) y en hombres ({h:.1f} %)"
        mayor = "mujeres" if m > h else "hombres"
        return f"La {nombre} es mayor en {mayor}: {max(m, h):.1f} % frente a {min(m, h):.1f} %"
    if por == "edad":
        return (f"La {nombre} es más alta entre las personas de {t.idxmax()} ({t.max():.1f} %) "
                f"y más baja entre las de {t.idxmin()} ({t.min():.1f} %)")
    return f"La {nombre} va de {t.min():.1f} % en {t.idxmin()} a {t.max():.1f} % en {t.idxmax()}"


def graficar(por, indicador, bases, figuras):
    base, col, peso, orden = GRUPOS[por]
    variable, nombre = INDICADORES[indicador]
    df = bases[base]
    t = tasas(df, col, peso, variable)
    if orden:
        t = t.reindex(orden)
    else:
        t = t.sort_values(ascending=False)
    nacional = float((df[variable] * df[peso]).sum() / df[peso].sum() * 100)

    alto = 0.42 * len(t) + 1.9
    fig, ax = plt.subplots(figsize=(8, alto), dpi=200)
    y = range(len(t))[::-1]
    ax.barh(list(y), t.values, color=AZUL, height=0.62)
    for yi, v in zip(y, t.values):
        ax.text(v + t.max() * 0.012, yi, f"{v:.1f} %", va="center", fontsize=9, color=TEXTO, zorder=4,
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.2})
    ax.set_yticks(list(y), t.index, fontsize=9, color=TEXTO)
    ax.axvline(nacional, color=TEXTO_2, linewidth=1, linestyle=(0, (4, 3)), zorder=3)
    etiqueta = "Perú" if base == "hogares" else "Perú (personas)"
    ax.text(nacional, len(t) - 0.35, f" {etiqueta}: {nacional:.1f} %", fontsize=8, color=TEXTO_2, va="bottom")
    ax.set_xlim(0, max(t.max() * 1.16, nacional * 1.3))
    ax.set_ylim(-0.6, len(t) - 0.1)
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:.0f} %")
    ax.tick_params(axis="x", colors=TEXTO_2, labelsize=8)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=GRILLA, linewidth=0.6)
    ax.set_axisbelow(True)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(GRILLA)
    lineas = textwrap.wrap(titulo(por, t, nombre), 82)
    extra = 0.24 * (len(lineas) - 1)
    fig.text(0.02, 1 - 0.22 / alto, "\n".join(lineas), fontsize=11.5, color=TEXTO, va="top", linespacing=1.3)
    fig.text(0.02, 1 - (0.52 + extra) / alto, f"% de personas en {nombre}, Perú, 2024", fontsize=9,
             color=TEXTO_2, va="top")
    metodo = ("hogares de la sumaria, ponderados con factor07 × mieperho (método del INEI)" if base == "hogares"
              else "personas residentes habituales, ponderadas con facpob07")
    fig.text(0.02, 0.012, f"Fuente: INEI, ENAHO 2024 (módulos 34 y 02). Estimación con {metodo}. "
                          "Elaboración propia.", fontsize=6.8, color=TEXTO_2)
    fig.tight_layout(rect=(0, 0.3 / alto, 1, 1 - (0.85 + extra) / alto))
    figuras.mkdir(exist_ok=True)
    archivo = figuras / f"enaho_{indicador}_{por}.png"
    fig.savefig(archivo, facecolor="white")
    plt.close(fig)

    print(f"\n{archivo.relative_to(RAIZ).as_posix()}  ({nombre} por {por}; Perú {nacional:.2f} %)")
    print(t.astype(float).round(2).to_string())
    return archivo


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--por", nargs="+", choices=list(GRUPOS), default=list(GRUPOS))
    p.add_argument("--indicador", choices=list(INDICADORES), default="pobreza")
    p.add_argument("--anio", type=int, default=2024)
    p.add_argument("--salidas", type=Path, default=RAIZ / "salidas")
    p.add_argument("--figuras", type=Path, default=RAIZ / "figuras")
    a = p.parse_args()
    archivos = {b: a.salidas / f"{b}_{a.anio}.parquet" for b in ("hogares", "personas")}
    faltan = [f.name for f in archivos.values() if not f.exists()]
    if faltan:
        sys.exit(f"ERROR: falta {', '.join(faltan)} en salidas/. Usa primero la skill limpiando-enaho "
                 f"(uv run .claude/skills/limpiando-enaho/scripts/limpiar.py --anio {a.anio}).")
    bases = {b: pd.read_parquet(f) for b, f in archivos.items()}
    for por in a.por:
        graficar(por, a.indicador, bases, a.figuras)


if __name__ == "__main__":
    main()

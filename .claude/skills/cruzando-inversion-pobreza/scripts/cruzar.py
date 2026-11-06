"""Cruza la inversión de los gobiernos regionales y locales (BCRP) con la pobreza monetaria (ENAHO 2024).

    uv run .claude/skills/cruzando-inversion-pobreza/scripts/cruzar.py --codigos   # qué pedir al MCP del BCRP
    uv run .claude/skills/cruzando-inversion-pobreza/scripts/cruzar.py             # el cruce

Entradas:
- salidas/bcrp_inversion_2020_2024.csv y salidas/bcrp_ipc_2020_2024.csv, que deja la herramienta
  exportar_series del MCP del BCRP. Los datos llegan del BCRP sin copiarlos a mano.
- salidas/indicadores.csv, que deja la skill limpiando-enaho (pobreza y población por departamento).

Método: la inversión de cada año se pasa a soles de 2024 con el promedio anual del IPC de Lima (PN38705PM).
Para cada departamento se suma la inversión de los gobiernos regionales y locales. En Lima se incluye la
Municipalidad Metropolitana de Lima, que el BCRP cuenta como gobierno regional. Se divide entre la población
expandida de la ENAHO 2024 y entre el número de años. La relación con la pobreza se mide con las correlaciones
de Pearson y Spearman. Para Spearman se calcula un valor p por permutaciones. Todo es descriptivo, no causal.

Salidas: salidas/cruce_inversion_pobreza.csv, salidas/cruce_resultados.txt, figuras/bcrp_inversion_gr_gl.png,
figuras/cruce_inversion_pobreza.png y mapas/inversion_por_habitante.png.
"""
import argparse
import json
import math
import sys
import textwrap
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import patheffects
from matplotlib.colors import LinearSegmentedColormap, Normalize

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[3]
SERIES = AQUI.parent / "referencia" / "series_bcrp.csv"
IPC = "PN38705PM"
AZUL, NARANJA, TEXTO, TEXTO_2, GRILLA = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e4e3df"
RAMPA_NARANJA = ["#fde7da", "#f9c3a5", "#f39a6e", "#eb6834", "#c9501f", "#9c3c14", "#6e2a0c"]
FUENTE_BCRP = ("BCRP, inversión bruta fija de los gobiernos regionales y locales por departamento (datos del MEF) "
               f"e IPC de Lima ({IPC})")


def leer_csv(ruta, quien):
    if not ruta.exists():
        sys.exit(f"ERROR: falta {ruta.relative_to(RAIZ).as_posix()}. {quien}")
    return pd.read_csv(ruta, dtype={"codigo": str, "periodo": str})


def correlaciones(x, y, semilla=2024, n_perm=20_000):
    """Pearson, Spearman y valor p de Spearman por permutaciones (dos colas), sin depender de scipy."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    rx, ry = pd.Series(x).rank().to_numpy(), pd.Series(y).rank().to_numpy()
    pearson = float(np.corrcoef(x, y)[0, 1])
    spearman = float(np.corrcoef(rx, ry)[0, 1])
    rng = np.random.default_rng(semilla)
    perm = np.array([np.corrcoef(rx, rng.permutation(ry))[0, 1] for _ in range(n_perm)])
    p = float((np.abs(perm) >= abs(spearman) - 1e-12).mean())
    return {"pearson": round(pearson, 3), "spearman": round(spearman, 3), "p_spearman": round(p, 3), "n": len(x)}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--desde", type=int, default=2020)
    p.add_argument("--hasta", type=int, default=2024)
    p.add_argument("--codigos", action="store_true", help="imprime las llamadas a exportar_series y termina")
    p.add_argument("--salidas", type=Path, default=RAIZ / "salidas")
    p.add_argument("--geojson", type=Path, default=RAIZ / "datos" / "peru_departamental_simple.geojson")
    a = p.parse_args()
    series = pd.read_csv(SERIES, dtype=str)
    archivo_inv, archivo_ipc = f"bcrp_inversion_{a.desde}_{a.hasta}", f"bcrp_ipc_{a.desde}_{a.hasta}"

    if a.codigos:
        print(json.dumps([
            {"herramienta": "exportar_series", "codigos": series.codigo.tolist(), "desde": str(a.desde),
             "hasta": str(a.hasta), "archivo": archivo_inv},
            {"herramienta": "exportar_series", "codigos": [IPC], "desde": f"{a.desde}-01", "hasta": f"{a.hasta}-12",
             "archivo": archivo_ipc}], ensure_ascii=False, indent=1))
        return

    pide_mcp = "Usa la herramienta exportar_series del MCP del BCRP (ver --codigos)."
    inv = leer_csv(a.salidas / f"{archivo_inv}.csv", pide_mcp)
    ipc = leer_csv(a.salidas / f"{archivo_ipc}.csv", pide_mcp)
    ind = leer_csv(a.salidas / "indicadores.csv", "Usa primero la skill limpiando-enaho.")
    anios = [str(x) for x in range(a.desde, a.hasta + 1)]

    controles = []

    def control(nombre, ok, detalle, esencial=True):
        controles.append({"nombre": nombre, "ok": bool(ok), "detalle": detalle, "esencial": esencial})

    # 1. Las series de inversión, completas
    inv = inv.merge(series[["codigo", "nivel", "departamento"]], on="codigo", how="inner", validate="m:1")
    por_serie = inv.groupby("codigo").periodo.apply(set)
    incompletas = [c for c in series.codigo if c not in por_serie or not set(anios) <= por_serie[c]]
    control(f"Las {len(series)} series de inversión tienen los {len(anios)} años", not incompletas,
            f"{por_serie.size} series en el CSV; incompletas o ausentes: {', '.join(incompletas) or 'ninguna'}")
    inv = inv[inv.periodo.isin(anios)]
    # 2. Los departamentos suman el total que publica el BCRP
    deps = inv[inv.departamento != "TOTAL"].groupby(["nivel", "periodo"]).valor.sum()
    tot = inv[inv.departamento == "TOTAL"].set_index(["nivel", "periodo"]).valor
    dif = (deps - tot).abs()
    control("La suma de los departamentos es igual al total del BCRP (cada nivel y año)",
            len(dif) == 2 * len(anios) and dif.max() <= 0.5,
            f"diferencia máxima {dif.max():.3f} millones de soles en {len(dif)} comparaciones")
    # 3. El IPC, 12 meses por año
    ipc["anio"] = ipc.periodo.str[:4]
    meses = ipc[ipc.codigo == IPC].groupby("anio").size()
    control(f"El IPC {IPC} tiene 12 meses por año", all(meses.get(x, 0) == 12 for x in anios),
            ", ".join(f"{x}: {meses.get(x, 0)}" for x in anios))
    ipc_anual = ipc[ipc.codigo == IPC].groupby("anio").valor.mean()
    deflactor = ipc_anual[str(a.hasta)] / ipc_anual
    # 4. La ENAHO, validada
    dep = ind[ind.grupo == "departamento"].rename(columns={"codigo": "departamento", "categoria": "nombre"})
    nac = ind[ind.grupo == "nacional"].iloc[0]
    control("ENAHO: 25 departamentos con pobreza y población", len(dep) == 25 and dep.pobreza_pct.notna().all(),
            f"{len(dep)} departamentos en salidas/indicadores.csv")
    control("ENAHO: pobreza nacional a menos de 0.1 puntos de 27.6 %", abs(nac.pobreza_pct - 27.6) <= 0.1,
            f"{nac.pobreza_pct:.2f} %")
    control("ENAHO: la población de los departamentos suma la nacional",
            abs(dep.poblacion_expandida.sum() - nac.poblacion_expandida) <= 25,
            f"{dep.poblacion_expandida.sum():,.0f} frente a {nac.poblacion_expandida:,.0f}", esencial=False)

    # Cálculos
    d = inv[inv.departamento != "TOTAL"].copy()
    d["real"] = d.valor * d.periodo.map(deflactor)
    tabla = d.pivot_table(index="departamento", columns="nivel", values=["valor", "real"], aggfunc="sum")
    tabla.columns = [f"{'nominal' if m == 'valor' else 'real'}_{'gr' if n == 'gobierno_regional' else 'gl'}"
                     for m, n in tabla.columns]
    tabla = tabla.reset_index()
    tabla["nominal_total"] = tabla.nominal_gr + tabla.nominal_gl
    tabla["real_total"] = tabla.real_gr + tabla.real_gl
    cruce = dep[["departamento", "nombre", "pobreza_pct", "pobreza_extrema_pct", "poblacion_expandida"]].merge(
        tabla, on="departamento", how="outer", validate="1:1", indicator=True)
    control("Unión BCRP-ENAHO por código de departamento: 25 de 25",
            len(cruce) == 25 and (cruce._merge == "both").all(),
            f"{(cruce._merge == 'both').sum()} departamentos unidos")
    fallas = [c for c in controles if not c["ok"] and c["esencial"]]
    lineas = [f"CRUCE INVERSIÓN-POBREZA · skill cruzando-inversion-pobreza · {datetime.now():%Y-%m-%d %H:%M}", ""]
    for c in controles:
        marca = "APROBADO" if c["ok"] else ("FALLÓ   " if c["esencial"] else "REVISAR ")
        lineas.append(f"[{marca}] {'(esencial) ' if c['esencial'] else ''}{c['nombre']}: {c['detalle']}")
    if fallas:
        lineas.append("\nPROCESO DETENIDO: fallaron verificaciones esenciales; no se calculó el cruce.")
        (a.salidas / "cruce_resultados.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8")
        sys.exit("\n".join(lineas))

    cruce = cruce.drop(columns="_merge")
    n_anios = len(anios)
    cruce["inversion_pc_anual"] = cruce.real_total * 1e6 / n_anios / cruce.poblacion_expandida
    cruce["inversion_pc_anual_gr"] = cruce.real_gr * 1e6 / n_anios / cruce.poblacion_expandida
    cruce["inversion_pc_anual_gl"] = cruce.real_gl * 1e6 / n_anios / cruce.poblacion_expandida
    cruce["tercil_pobreza"] = pd.qcut(cruce.pobreza_pct.rank(method="first"), 3,
                                      labels=["menos pobres", "intermedios", "más pobres"]).astype(str)
    cruce = cruce.sort_values("pobreza_pct", ascending=False)
    pc_nacional = float(cruce.real_total.sum() * 1e6 / n_anios / cruce.poblacion_expandida.sum())
    todos = correlaciones(cruce.pobreza_pct, cruce.inversion_pc_anual)
    sin_lima = cruce[~cruce.departamento.isin(["15", "07"])]
    sin = correlaciones(sin_lima.pobreza_pct, sin_lima.inversion_pc_anual)
    terciles = cruce.groupby("tercil_pobreza").agg(departamentos=("nombre", "size"),
                                                   pobreza_media=("pobreza_pct", "mean"),
                                                   mediana_inversion_pc=("inversion_pc_anual", "median"))
    terciles = terciles.reindex(["más pobres", "intermedios", "menos pobres"])
    nacional = d.groupby(["periodo", "nivel"]).agg(nominal=("valor", "sum"), real=("real", "sum")).reset_index()

    a.salidas.mkdir(exist_ok=True)
    redondeo = {c: 2 for c in cruce.columns if c.startswith(("nominal", "real", "inversion"))}
    cruce.round(redondeo).to_csv(a.salidas / "cruce_inversion_pobreza.csv", index=False, encoding="utf-8")

    real_ini = nacional[nacional.periodo == anios[0]].real.sum()
    real_fin = nacional[nacional.periodo == anios[-1]].real.sum()
    mas = cruce.nlargest(5, "inversion_pc_anual")
    menos = cruce.nsmallest(5, "inversion_pc_anual")
    lineas += ["", "RESULTADOS (inversión en soles de 2024; población ENAHO 2024)",
               f"Deflactor (promedio anual del IPC {IPC}): "
               + ", ".join(f"{x}: {ipc_anual[x]:.3f}" for x in anios),
               f"Inversión real GR+GL, Perú: {real_ini:,.0f} millones en {anios[0]} y {real_fin:,.0f} en {anios[-1]} "
               f"({(real_fin / real_ini - 1) * 100:+.1f} %); total {anios[0]}-{anios[-1]}: "
               f"{nacional.real.sum():,.0f} millones (nominal {nacional.nominal.sum():,.0f})",
               f"Inversión real por habitante al año, Perú: {pc_nacional:,.0f} soles",
               f"Correlación pobreza 2024 vs inversión por habitante (25 departamentos): Pearson {todos['pearson']:+.3f}, "
               f"Spearman {todos['spearman']:+.3f} (p por permutaciones = {todos['p_spearman']:.3f})",
               f"Sin Lima ni Callao (23): Pearson {sin['pearson']:+.3f}, Spearman {sin['spearman']:+.3f} "
               f"(p = {sin['p_spearman']:.3f})",
               "Mediana de inversión por habitante según tercil de pobreza: "
               + "; ".join(f"{t} ({int(r.departamentos)} dptos., pobreza media {r.pobreza_media:.1f} %): "
                           f"{r.mediana_inversion_pc:,.0f} soles" for t, r in terciles.iterrows()),
               "Más inversión por habitante: " + ", ".join(f"{r.nombre} {r.inversion_pc_anual:,.0f}"
                                                         for r in mas.itertuples()),
               "Menos inversión por habitante: " + ", ".join(f"{r.nombre} {r.inversion_pc_anual:,.0f}"
                                                           for r in menos.itertuples()),
               "Los 5 más pobres: " + ", ".join(f"{r.nombre} ({r.pobreza_pct:.1f} %) {r.inversion_pc_anual:,.0f}"
                                               for r in cruce.head(5).itertuples()),
               "Lectura: correlación descriptiva entre 25 departamentos; no mide causalidad."]
    texto = "\n".join(lineas) + "\n"
    (a.salidas / "cruce_resultados.txt").write_text(texto, encoding="utf-8")
    print(texto)

    archivos = [graficar_nacional(nacional, anios, a), graficar_cruce(cruce, todos, pc_nacional, nac, anios, a),
                mapear_inversion(cruce, anios, a)]
    print("Figuras: " + ", ".join(f.relative_to(RAIZ).as_posix() for f in archivos if f))
    print("Tabla: salidas/cruce_inversion_pobreza.csv · Resultados: salidas/cruce_resultados.txt")


def _pie(fig, texto, y=0.015):
    fig.text(0.02, y, "\n".join(textwrap.wrap(texto, 150)), fontsize=6.6, color=TEXTO_2, va="bottom")


def _rotular(fig, ax, puntos):
    """Pone cada nombre junto a su punto probando cuatro posiciones, para que no se tapen entre sí."""
    fig.canvas.draw()
    render = fig.canvas.get_renderer()
    ocupadas = []
    for nombre, x, y in puntos:
        for dx, dy, ha in [(5, 4, "left"), (5, -11, "left"), (-5, 4, "right"), (-5, -11, "right")]:
            texto = ax.annotate(nombre, (x, y), xytext=(dx, dy), textcoords="offset points", ha=ha, fontsize=7.5,
                                color=TEXTO, path_effects=[patheffects.withStroke(linewidth=2.2, foreground="white")])
            caja = texto.get_window_extent(render).expanded(1.05, 1.15)
            if not any(caja.overlaps(o) for o in ocupadas):
                ocupadas.append(caja)
                break
            texto.remove()
        else:
            ocupadas.append(ax.annotate(nombre, (x, y), xytext=(5, 4), textcoords="offset points", fontsize=7.5,
                                        color=TEXTO).get_window_extent(render))


def graficar_nacional(nacional, anios, a):
    """Barras agrupadas: inversión real de los gobiernos regionales y locales por año, con el BCRP."""
    t = nacional.pivot(index="periodo", columns="nivel", values="real").reindex(anios) / 1000
    fig, ax = plt.subplots(figsize=(8, 4.6), dpi=200)
    x = np.arange(len(anios))
    ancho = 0.38
    for i, (nivel, color, etiqueta) in enumerate([("gobierno_regional", AZUL, "Gobiernos regionales"),
                                                   ("gobierno_local", NARANJA, "Gobiernos locales")]):
        pos = x + (i - 0.5) * (ancho + 0.02)
        ax.bar(pos, t[nivel], width=ancho, color=color, label=etiqueta)
        for xi, v in zip(pos, t[nivel]):
            ax.text(xi, v + t.values.max() * 0.015, f"{v:,.1f}", ha="center", va="bottom", fontsize=8, color=TEXTO)
    ax.set_xticks(x, anios, fontsize=9, color=TEXTO)
    ax.set_ylim(0, t.values.max() * 1.15)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    ax.tick_params(axis="y", colors=TEXTO_2, labelsize=8, length=0)
    ax.tick_params(axis="x", length=0)
    ax.grid(axis="y", color=GRILLA, linewidth=0.6)
    ax.set_axisbelow(True)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(GRILLA)
    ax.legend(frameon=False, fontsize=8.5, loc="upper left", ncols=2)
    total = t.sum(axis=1)
    fig.text(0.02, 0.965, f"La inversión real de los gobiernos regionales y locales subió {(total.iloc[-1] / total.iloc[0] - 1) * 100:.0f} % "
                          f"entre {anios[0]} y {anios[-1]}", fontsize=11.5, color=TEXTO, va="top")
    fig.text(0.02, 0.905, "Inversión bruta fija, miles de millones de soles de 2024 (deflactada con el IPC de Lima)",
             fontsize=8.5, color=TEXTO_2, va="top")
    _pie(fig, f"Fuente: {FUENTE_BCRP}. Series RD16735DA y RD16708DA. Elaboración propia.")
    fig.tight_layout(rect=(0, 0.06, 1, 0.87))
    a_fig = RAIZ / "figuras"
    a_fig.mkdir(exist_ok=True)
    archivo = a_fig / "bcrp_inversion_gr_gl.png"
    fig.savefig(archivo, facecolor="white")
    plt.close(fig)
    return archivo


def graficar_cruce(cruce, cor, pc_nacional, nac, anios, a):
    """Dispersión: pobreza 2024 (x) e inversión por habitante (y), con las líneas del promedio de Perú."""
    fig, ax = plt.subplots(figsize=(8, 6), dpi=200)
    ax.scatter(cruce.pobreza_pct, cruce.inversion_pc_anual, s=46, color=AZUL, edgecolor="white", linewidth=1.2,
               zorder=3)
    ax.axvline(nac.pobreza_pct, color=TEXTO_2, linewidth=0.9, linestyle=(0, (4, 3)), zorder=2)
    ax.axhline(pc_nacional, color=TEXTO_2, linewidth=0.9, linestyle=(0, (4, 3)), zorder=2)
    ax.text(nac.pobreza_pct, cruce.inversion_pc_anual.max() * 1.07,
            f" Pobreza Perú: {nac.pobreza_pct:.1f} %", fontsize=7.5, color=TEXTO_2, va="top")
    ax.text(0.4, pc_nacional, f"Inversión Perú: {pc_nacional:,.0f} soles", fontsize=7.5, color=TEXTO_2,
            va="bottom", ha="left")
    ax.set_xlim(0, cruce.pobreza_pct.max() * 1.08)
    ax.set_ylim(0, cruce.inversion_pc_anual.max() * 1.1)
    rotular = set(cruce.nlargest(5, "inversion_pc_anual").departamento) | set(cruce.nlargest(5, "pobreza_pct")
                                                                               .departamento) | {"15", "07", "11"}
    elegidos = cruce[cruce.departamento.isin(rotular)].sort_values("inversion_pc_anual", ascending=False)
    ax.set_xlabel(f"Pobreza monetaria {anios[-1]} (% de personas)", fontsize=8.5, color=TEXTO_2)
    ax.set_ylabel(f"Inversión por habitante al año, {anios[0]}-{anios[-1]} (soles de 2024)", fontsize=8.5,
                  color=TEXTO_2)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f} %")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    ax.tick_params(colors=TEXTO_2, labelsize=8)
    ax.grid(color=GRILLA, linewidth=0.5)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    rho = cor["spearman"]
    if rho <= -0.1:
        titulo = "Los departamentos más pobres no recibieron más inversión por habitante"
    elif rho >= 0.1:
        titulo = "Los departamentos más pobres recibieron más inversión por habitante"
    else:
        titulo = "No hay una relación clara entre pobreza e inversión por habitante"
    fig.text(0.02, 0.975, titulo, fontsize=11.5, color=TEXTO, va="top")
    fig.text(0.02, 0.937, f"Gobiernos regionales y locales, 25 departamentos. Spearman {rho:+.2f} "
                          f"(p = {cor['p_spearman']:.2f}); Pearson {cor['pearson']:+.2f}. Asociación descriptiva, no causal.",
             fontsize=8.5, color=TEXTO_2, va="top")
    _pie(fig, f"Fuente: {FUENTE_BCRP}; INEI, ENAHO 2024 (pobreza y población, factor07 × mieperho). "
              "Elaboración propia.")
    fig.tight_layout(rect=(0, 0.05, 1, 0.92))
    _rotular(fig, ax, list(zip(elegidos.nombre, elegidos.pobreza_pct, elegidos.inversion_pc_anual)))
    archivo = RAIZ / "figuras" / "cruce_inversion_pobreza.png"
    fig.savefig(archivo, facecolor="white")
    plt.close(fig)
    return archivo


def mapear_inversion(cruce, anios, a):
    """Mapa de la inversión por habitante, con una rampa naranja (la de la pobreza es azul)."""
    if not a.geojson.exists():
        print(f"AVISO: falta {a.geojson.name} en datos/; no se hizo el mapa de inversión.")
        return None
    geo = gpd.read_file(a.geojson)
    geo["departamento"] = geo.FIRST_IDDP.astype(str).str.strip().str.zfill(2)
    mapa = geo.merge(cruce, on="departamento", how="left", validate="1:1")
    if len(mapa) != 25 or mapa.inversion_pc_anual.isna().any():
        sys.exit("ERROR: el mapa de inversión no tiene los 25 departamentos con dato.")
    tope = math.ceil(mapa.inversion_pc_anual.max() / 500) * 500
    cmap = LinearSegmentedColormap.from_list("naranja", RAMPA_NARANJA)
    norma = Normalize(vmin=0, vmax=tope)
    fig = plt.figure(figsize=(7.2, 9.6), dpi=200)
    ax = fig.add_axes((0.02, 0.07, 0.8, 0.83))
    cax = fig.add_axes((0.84, 0.3, 0.025, 0.36))
    mapa.plot(column="inversion_pc_anual", cmap=cmap, norm=norma, edgecolor="white", linewidth=0.6, ax=ax)
    for _, f in mapa.iterrows():
        punto = f.geometry.representative_point()
        color = "white" if norma(f.inversion_pc_anual) > 0.55 else TEXTO
        borde = "#9c3c14" if color == "white" else "white"
        if f.departamento == "07":
            ax.annotate(f"Callao\n{f.inversion_pc_anual:,.0f}", (punto.x, punto.y), xytext=(-78.9, -12.3),
                        fontsize=6.5, color=TEXTO, ha="right", va="center",
                        arrowprops={"arrowstyle": "-", "color": TEXTO_2, "linewidth": 0.6})
            continue
        ax.text(punto.x, punto.y, f"{f.inversion_pc_anual:,.0f}", fontsize=6.5, color=color, ha="center",
                va="center", path_effects=[patheffects.withStroke(linewidth=2, foreground=borde)])
    ax.set_axis_off()
    barra = fig.colorbar(plt.cm.ScalarMappable(norm=norma, cmap=cmap), cax=cax)
    barra.set_label("Soles de 2024 por habitante al año", fontsize=8.5, color=TEXTO_2)
    barra.ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    barra.ax.tick_params(labelsize=7.5, colors=TEXTO_2)
    barra.outline.set_visible(False)
    top = mapa.nlargest(3, "inversion_pc_anual")
    baja = mapa.nsmallest(1, "inversion_pc_anual").iloc[0]
    fig.text(0.04, 0.975, f"{top.nombre.iloc[0]} ({top.inversion_pc_anual.iloc[0]:,.0f} soles), {top.nombre.iloc[1]} y "
                          f"{top.nombre.iloc[2]} tuvieron más inversión por habitante;", fontsize=11, color=TEXTO,
             va="top")
    fig.text(0.04, 0.951, f"{baja.nombre} la menor ({baja.inversion_pc_anual:,.0f} soles)", fontsize=11, color=TEXTO,
             va="top")
    fig.text(0.04, 0.925, f"Inversión de gobiernos regionales y locales por habitante, promedio anual "
                          f"{anios[0]}-{anios[-1]}, soles de 2024.", fontsize=8.5, color=TEXTO_2, va="top")
    fig.text(0.04, 0.02, f"Fuente: {FUENTE_BCRP};\npoblación: INEI, ENAHO 2024. Unión por código de departamento "
                         "(FIRST_IDDP). Elaboración propia.", fontsize=6.5, color=TEXTO_2)
    a_mapas = RAIZ / "mapas"
    a_mapas.mkdir(exist_ok=True)
    archivo = a_mapas / "inversion_por_habitante.png"
    fig.savefig(archivo, facecolor="white")
    plt.close(fig)
    return archivo


if __name__ == "__main__":
    main()

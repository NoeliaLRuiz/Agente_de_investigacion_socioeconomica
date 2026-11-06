"""Servidor MCP del BCRP para el agente de investigación socioeconómica (Tarea 4).

    uv run pytest                       # las 10 pruebas: 8 originales de la Sesión 04 + 2 de comparar_periodos
    uv run mcp/server.py                # el servidor, por stdio (Claude Code lo abre solo con .mcp.json)

Herramientas: buscar_series, serie, resumen, comparar_periodos (propia) y graficar_serie.
Las cuentas las hace Python, no el modelo: así cada cifra sale de una llamada que se puede repetir.
"""
import re
import time
import unicodedata
from datetime import date
from functools import cache
from pathlib import Path

import httpx
import pandas as pd
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

AQUI = Path(__file__).parent
FIGURAS = AQUI.parent / "figuras"
CATALOGO = AQUI / "datos" / "catalogo_bcrp.csv"
URL_CATALOGO = "https://estadisticas.bcrp.gob.pe/estadisticas/series/metadata"
API = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"
SOLO_LECTURA = {"readOnlyHint": True, "openWorldHint": True}

mcp = FastMCP("bcrp", instructions=(
    "Series oficiales del Banco Central de Reserva del Perú (BCRP). Primero busca el código con buscar_series; "
    "luego usa resumen para variaciones, promedios y extremos de un periodo, comparar_periodos para contrastar "
    "dos intervalos y serie para los datos. graficar_serie guarda un gráfico en figuras/. No calcules a mano: "
    "cita siempre el código de la serie, el periodo y la URL de la fuente."))


def _sin_tildes(s):
    return unicodedata.normalize("NFD", str(s).lower()).encode("ascii", "ignore").decode()


@cache
def catalogo():
    """El catálogo oficial: 17 mil series en unos 7 MB. Se baja una vez y queda en mcp/datos/."""
    if not CATALOGO.exists():
        CATALOGO.parent.mkdir(exist_ok=True)
        r = httpx.get(URL_CATALOGO, timeout=120)
        r.raise_for_status()
        CATALOGO.write_text(r.content.decode("latin-1"), encoding="utf-8")
    df = pd.read_csv(CATALOGO, sep=";", dtype=str).fillna("")
    df = df.rename(columns={"Código de serie": "codigo", "Categoría de serie": "categoria", "Grupo de serie": "grupo",
                            "Nombre de serie": "nombre", "Frecuencia": "frecuencia",
                            "Fecha de actualización": "actualizada", "Fecha de inicio": "inicio"})
    df["texto"] = (df.categoria + " " + df.grupo + " " + df.nombre).map(_sin_tildes)
    return df


def _ficha(codigo):
    fila = catalogo().query("codigo == @codigo")
    if fila.empty:
        raise ToolError(f"No existe el código de serie {codigo!r}. Búsquenlo con buscar_series.")
    f = fila.iloc[0]
    return {"codigo": f.codigo, "nombre": f"{f.grupo} - {f.nombre}", "categoria": f.categoria,
            "frecuencia": f.frecuencia, "inicio": f.inicio, "actualizada": f.actualizada}


@mcp.tool(annotations=SOLO_LECTURA)
def buscar_series(texto: str, frecuencia: str | None = None, limite: int = 10) -> list[dict]:
    """Busca series del BCRP por palabras: todas deben aparecer en la categoría, el grupo o el nombre.

    Ejemplos: "ipc 12 meses", "tipo de cambio interbancario venta", "reservas internacionales netas",
    "tasa de referencia", "cobre precio". frecuencia: "Diaria", "Mensual", "Trimestral" o "Anual".
    Devuelve el código, el nombre completo, la frecuencia y desde cuándo hay datos. Si no hay resultados,
    prueben con menos palabras.
    """
    df = catalogo()
    m = pd.Series(True, index=df.index)
    for palabra in _sin_tildes(texto).split():
        m &= df.texto.str.contains(re.escape(palabra))
    if frecuencia:
        m &= df.frecuencia.str.lower() == frecuencia.lower()
    # primero las series vigentes y, entre ellas, las de nombre más corto (las más generales)
    sel = df[m]
    orden = sel.assign(vieja=sel.actualizada < "2025", largo=(sel.grupo + sel.nombre).str.len())
    return [_ficha(c) for c in orden.sort_values(["vieja", "largo"]).head(limite).codigo]


# La API pide 2025-1 (mensual y trimestral), 2025-01-15 (diaria) o 2025 (anual) y devuelve
# "Ene.2025", "01.Oct.26", "T1.25" o "2025"; setiembre puede venir como "Set" o "Sep".
MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "set": 9,
         "oct": 10, "nov": 11, "dic": 12}


def _fecha_api(fecha, frecuencia, fin=False):
    """De "2025-01", "2025-01-15", "2025-T1" o "2025" al formato de la API. Lo que falta se completa al inicio
    del periodo en «desde» y al final en «hasta»: "2025" en una serie mensual va de 2025-1 a 2025-12."""
    m = re.fullmatch(r"(\d{4})(?:-(T?)(\d{1,2})(?:-(\d{1,2}))?)?", str(fecha).strip().upper())
    if not m:
        raise ToolError(f"Fecha {fecha!r} no válida. Usen 2025-01 (mensual), 2025-01-15 (diaria), 2025-T1 o 2025.")
    anio, trimestre, n, dia = int(m[1]), m[2] == "T", m[3] and int(m[3]), m[4] and int(m[4])
    if n and not 1 <= n <= (4 if trimestre else 12):
        raise ToolError(f"Fecha {fecha!r} no válida: el {'trimestre' if trimestre else 'mes'} no existe.")
    if frecuencia == "Anual":
        return str(anio)
    if frecuencia == "Trimestral":
        if trimestre:
            return f"{anio}-{n}"
        return f"{anio}-{(n - 1) // 3 + 1 if n else 4 if fin else 1}"
    mes = (n * 3 if fin else n * 3 - 2) if trimestre else n or (12 if fin else 1)
    if frecuencia == "Mensual":
        return f"{anio}-{mes}"
    dia = dia or (pd.Period(f"{anio}-{mes:02d}").days_in_month if fin else 1)
    return f"{anio}-{mes:02d}-{dia:02d}"


def _anio(aa):
    """Los años de dos cifras de la API: "26" es 2026 y "97" es 1997."""
    return 2000 + int(aa) if 2000 + int(aa) <= date.today().year else 1900 + int(aa)


def _periodo(nombre):
    """De "Ene.2025", "01.Oct.26", "T1.25" o "2025" a "2025-01", "2026-10-01", "2025-T1" o "2025"."""
    partes = nombre.split(".")
    if len(partes) == 3:
        dia, mes, aa = partes
        return f"{_anio(aa)}-{MESES[mes.lower()]:02d}-{int(dia):02d}"
    if len(partes) == 2:
        a, b = partes
        return f"{_anio(b)}-{a}" if a.startswith("T") else f"{b}-{MESES[a.lower()]:02d}"
    return nombre


@cache
def _descargar(codigo, desde, hasta):
    """Pide la serie a la API y guarda la respuesta. Si llega HTML en vez de JSON, espera y reintenta."""
    url = f"{API}/{codigo}/json/{desde}/{hasta}"
    for espera in (0, 2, 5, 10):
        time.sleep(espera)
        try:
            return url, httpx.get(url, timeout=60).json()
        except (httpx.HTTPError, ValueError):
            continue
    raise ToolError(f"El BCRP no respondió con datos para {codigo}. Esperen unos segundos y reintenten: {url}")


def _serie(codigo, desde, hasta):
    ficha = _ficha(codigo)
    url, js = _descargar(codigo, _fecha_api(desde, ficha["frecuencia"]), _fecha_api(hasta, ficha["frecuencia"], True))
    datos = [{"periodo": _periodo(p["name"]), "valor": round(float(p["values"][0]), 6)}
             for p in js.get("periods", []) if p["values"][0] != "n.d."]
    if not datos:
        raise ToolError(f"La serie {codigo} no tiene datos entre {desde} y {hasta}. Hay datos desde "
                        f"{ficha['inicio']} y se actualizó el {ficha['actualizada']}.")
    return {"codigo": codigo, "nombre": ficha["nombre"], "frecuencia": ficha["frecuencia"], "datos": datos,
            "fuente": url}


def _cuentas(s):
    """Primer y último dato, cambio, variación %, promedio, máximo y mínimo de una serie ya descargada."""
    d = pd.DataFrame(s["datos"])
    primero, ultimo = s["datos"][0], s["datos"][-1]
    cambio = ultimo["valor"] - primero["valor"]
    return {"n": len(d), "primero": primero, "ultimo": ultimo, "cambio": round(cambio, 6),
            "variacion_pct": round(cambio / primero["valor"] * 100, 4) if primero["valor"] else None,
            "promedio": round(float(d.valor.mean()), 6),
            "maximo": s["datos"][int(d.valor.idxmax())], "minimo": s["datos"][int(d.valor.idxmin())]}


@mcp.tool(annotations=SOLO_LECTURA)
def serie(codigo: str, desde: str, hasta: str) -> dict:
    """Datos de una serie del BCRP entre dos fechas, ambas incluidas, con la URL de la API como fuente.

    Fechas según la frecuencia de la serie: "2025-01" (mensual), "2025-01-15" (diaria), "2025-T1" (trimestral)
    o "2025" (anual). Si dan menos detalle se completa: "2025" en una serie mensual va de enero a diciembre.
    Para el dato de un solo periodo pongan la misma fecha en desde y hasta. Para variaciones, promedios o
    extremos usen resumen, que hace las cuentas.
    """
    return _serie(codigo, desde, hasta)


@mcp.tool(annotations=SOLO_LECTURA)
def resumen(codigo: str, desde: str, hasta: str) -> dict:
    """Las cuentas de una serie del BCRP en un periodo: primer y último dato, cambio (último menos primero, en
    la unidad de la serie: puntos si es un %), variacion_pct (el cambio entre el primero, en %), promedio, máximo
    y mínimo con su periodo. Úsenla siempre en vez de calcular a mano.

    Fechas como en serie: "2025-01", "2025-01-15", "2025-T1" o "2025".
    """
    s = _serie(codigo, desde, hasta)
    return {"codigo": codigo, "nombre": s["nombre"], "frecuencia": s["frecuencia"], **_cuentas(s),
            "fuente": s["fuente"]}


# Herramienta propia: comparar un indicador entre dos intervalos con las cuentas hechas en Python.
@mcp.tool(annotations=SOLO_LECTURA)
def comparar_periodos(codigo: str, desde_1: str, hasta_1: str, desde_2: str, hasta_2: str) -> dict:
    """Compara una serie del BCRP en dos intervalos que no se superponen, por ejemplo la inflación de
    2017-2019 (antes de la pandemia) frente a la de 2022-2024.

    Para cada intervalo da n, primer y último dato, promedio, máximo y mínimo con su periodo. Luego da
    diferencia_promedios (promedio del intervalo 2 menos el del 1, en la unidad de la serie: puntos
    porcentuales si la serie es un %) y variacion_pct_promedios (esa diferencia entre el promedio 1, en %).
    Si los intervalos tienen distinto número de datos, lo advierte. Fechas como en serie: "2025-01",
    "2025-01-15", "2025-T1" o "2025". Da error si los intervalos comparten periodos o si uno no tiene datos.
    """
    s1, s2 = _serie(codigo, desde_1, hasta_1), _serie(codigo, desde_2, hasta_2)
    comunes = sorted({d["periodo"] for d in s1["datos"]} & {d["periodo"] for d in s2["datos"]})
    if comunes:
        raise ToolError(f"Los intervalos se superponen en {len(comunes)} periodos ({comunes[0]} a {comunes[-1]}). "
                        "Elijan intervalos que no compartan periodos.")
    c1, c2 = _cuentas(s1), _cuentas(s2)
    diferencia = c2["promedio"] - c1["promedio"]
    advertencias = []
    if c1["n"] != c2["n"]:
        advertencias.append(f"El intervalo 1 tiene {c1['n']} datos y el 2 tiene {c2['n']}: los promedios cubren "
                            "lapsos distintos.")
    return {"codigo": codigo, "nombre": s1["nombre"], "frecuencia": s1["frecuencia"],
            "intervalo_1": {"desde": desde_1, "hasta": hasta_1, **c1},
            "intervalo_2": {"desde": desde_2, "hasta": hasta_2, **c2},
            "diferencia_promedios": round(diferencia, 6),
            "variacion_pct_promedios": round(diferencia / c1["promedio"] * 100, 4) if c1["promedio"] else None,
            "advertencias": advertencias, "fuentes": [s1["fuente"], s2["fuente"]]}


def _fecha_grafico(periodo):
    """Del periodo de serie ("2025-01", "2026-10-01", "2025-T1" o "2025") a una fecha para el eje."""
    if "-T" in periodo:
        anio, t = periodo.split("-T")
        return pd.Period(f"{anio}Q{t}").to_timestamp()
    return pd.Timestamp(periodo if len(periodo) > 4 else f"{periodo}-01-01")


@mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": True})
def graficar_serie(codigo: str, desde: str, hasta: str, titulo: str | None = None,
                   unidad: str | None = None) -> dict:
    """Dibuja una serie del BCRP como línea y guarda el PNG en figuras/bcrp_<codigo>_<desde>_<hasta>.png.

    titulo: lo que muestra el gráfico (si falta, usa el nombre oficial de la serie). unidad: el texto del eje Y,
    por ejemplo "Variación % en 12 meses" o "Soles por dólar". Marca el último dato con su valor, y el pie
    cita el código y la URL de la API. Devuelve la ruta del archivo y el resumen del periodo graficado.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    s = _serie(codigo, desde, hasta)
    fechas = [_fecha_grafico(d["periodo"]) for d in s["datos"]]
    valores = [d["valor"] for d in s["datos"]]
    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=200)
    ax.plot(fechas, valores, color="#2a78d6", linewidth=2)
    ax.scatter([fechas[-1]], [valores[-1]], color="#2a78d6", s=30, zorder=3)
    ax.annotate(f"{valores[-1]:,.2f}", (fechas[-1], valores[-1]), xytext=(6, 0), textcoords="offset points",
                va="center", fontsize=9, color="#0b0b0b")
    if min(valores) < 0 < max(valores):
        ax.axhline(0, color="#52514e", linewidth=0.8)
    ax.set_title(titulo or s["nombre"], loc="left", fontsize=12, color="#0b0b0b")
    ax.set_ylabel(unidad or "", color="#52514e")
    ax.grid(axis="y", color="#e4e3df", linewidth=0.6)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    ax.tick_params(colors="#52514e", labelsize=9)
    fig.text(0.01, 0.01, f"Fuente: BCRP, serie {codigo} ({s['datos'][0]['periodo']} a {s['datos'][-1]['periodo']}). "
                         f"{s['fuente']}", fontsize=7, color="#52514e")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    FIGURAS.mkdir(exist_ok=True)
    archivo = FIGURAS / f"bcrp_{codigo}_{desde}_{hasta}.png"
    fig.savefig(archivo)
    plt.close(fig)
    return {"archivo": str(archivo.relative_to(AQUI.parent)).replace("\\", "/"), "codigo": codigo,
            "nombre": s["nombre"], **_cuentas(s), "fuente": s["fuente"]}


# Recurso: la ficha de cualquiera de las 17 mil series, con una sola plantilla.
@mcp.resource("bcrp://serie/{codigo}")
def ficha_serie(codigo: str) -> dict:
    """Ficha de una serie del BCRP: nombre, categoría, frecuencia, desde cuándo hay datos y última actualización."""
    return _ficha(codigo)


# Prompts: recetas que piden citar la fuente de cada cifra.
@mcp.prompt
def informe(tema: str) -> str:
    """Informe de cinco viñetas sobre un tema económico, con cada cifra verificable en el BCRP."""
    return (f"Prepara un informe de cinco viñetas sobre «{tema}» con datos oficiales del BCRP. Busca los códigos con "
            "buscar_series y usa resumen para variaciones, promedios y extremos: no hagas cuentas a mano. En cada "
            "viñeta cita el código de la serie y el periodo. Termina con la lista de URLs de las fuentes.")


@mcp.prompt
def interpretar_indicador(indicador: str, desde: str, hasta: str) -> str:
    """Interpretación de un indicador del BCRP en un periodo, comparado con un periodo anterior de igual largo."""
    return (f"Interpreta la evolución de «{indicador}» entre {desde} y {hasta} con datos oficiales del BCRP. "
            "1) Ubica la serie con buscar_series y lee su ficha en el recurso bcrp://serie/{codigo}. "
            "2) Usa resumen para el periodo y comparar_periodos contra un intervalo anterior del mismo largo. "
            "3) Explica en tres párrafos qué pasó, cuándo estuvo el máximo y el mínimo, y qué tan distinto fue del "
            "periodo anterior. No afirmes causas: describe. Cita el código, el periodo y la URL de cada cifra. "
            "Si una herramienta da error o no hay datos, dilo en vez de estimar.")


if __name__ == "__main__":
    mcp.run()

"""Limpia la ENAHO 2024 (módulos 34 y 02) y arma una base de personas con pobreza y factor de expansión.

    uv run .claude/skills/limpiando-enaho/scripts/limpiar.py --anio 2024

Pasos, siempre en este orden: leer, normalizar nombres, filtrar residentes habituales, unir personas con
hogares (m:1), construir indicadores, validar y guardar. Si falla una validación esencial, no guarda la base
y termina con código de error 1: los resultados nunca se ajustan para que coincidan con la referencia.

Dos unidades de análisis, cada una con su factor:
- Hogares (sumaria): la pobreza es una condición del hogar. El INEI la estima con factor07 × mieperho, que son
  las personas que representa cada hogar. Se usa para nacional, área, departamento y dominio.
- Personas (módulo 02 + sumaria): para características de las personas (sexo, edad), con facpob07.

Salidas: salidas/personas_<anio>.parquet, salidas/hogares_<anio>.parquet, salidas/validacion.txt y
salidas/indicadores.csv.
"""
import argparse
import io
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[4]          # scripts → limpiando-enaho → skills → .claude → proyecto
CODIGO_INEI = {2024: 966}                            # código de la ENAHO de cada año en el portal del INEI
LLAVES = ["conglome", "vivienda", "hogar"]
LARGO_LLAVES = {"conglome": 6, "vivienda": 3, "hogar": 2, "codperso": 2, "ubigeo": 6}

# Valores de referencia de la Sesión 16 y del enunciado (INEI). Solo sirven para validar, nunca para corregir.
REFERENCIA = {"pobreza": 27.6, "residentes": 108_664, "hogares": 33_691, "filas_modulo02": 117_721,
              "urbana": 24.8, "rural": 39.3, "extrema": 5.5, "lima_metropolitana": 28.2}
TOLERANCIA_PP = 0.1                                  # puntos porcentuales

DEPARTAMENTOS = {"01": "Amazonas", "02": "Áncash", "03": "Apurímac", "04": "Arequipa", "05": "Ayacucho",
                 "06": "Cajamarca", "07": "Callao", "08": "Cusco", "09": "Huancavelica", "10": "Huánuco",
                 "11": "Ica", "12": "Junín", "13": "La Libertad", "14": "Lambayeque", "15": "Lima",
                 "16": "Loreto", "17": "Madre de Dios", "18": "Moquegua", "19": "Pasco", "20": "Piura",
                 "21": "Puno", "22": "San Martín", "23": "Tacna", "24": "Tumbes", "25": "Ucayali"}
GRUPOS_EDAD = [(0, 14, "0 a 14 años"), (15, 29, "15 a 29 años"), (30, 44, "30 a 44 años"),
               (45, 59, "45 a 59 años"), (60, 200, "60 años a más")]


def leer_stata(zip_path, nombre):
    """Lee un .dta dentro del zip del INEI sin convertir etiquetas y con las llaves como texto."""
    with zipfile.ZipFile(zip_path) as zf, zf.open(nombre) as f:
        df = pd.read_stata(io.BytesIO(f.read()), convert_categoricals=False)
    # minúsculas y sin eñe: la columna del año llega como «aÑo»
    df.columns = [c.lower().replace("ñ", "n") for c in df.columns]
    for c in LARGO_LLAVES:
        if c in df.columns:
            df[c] = df[c].astype("string").str.strip()
    return df


def tasa(df, columna, peso):
    """Porcentaje ponderado: suma de pesos de quienes cumplen la condición entre la suma de todos los pesos."""
    return float((df[columna] * df[peso]).sum() / df[peso].sum() * 100)


def indicadores(hogares, personas):
    """Pobreza y pobreza extrema ponderadas por grupo, con población expandida y tamaño de muestra.

    Los grupos territoriales salen de la base de hogares (factor07 × mieperho, como el INEI) y los de
    características de las personas, de la base de personas (facpob07)."""
    grupos = [("nacional", None, hogares, "peso_personas", "hogares"),
              ("area", "area", hogares, "peso_personas", "hogares"),
              ("departamento", "departamento", hogares, "peso_personas", "hogares"),
              ("nacional_personas", None, personas, "facpob07", "personas"),
              ("sexo", "sexo", personas, "facpob07", "personas"),
              ("grupo_edad", "grupo_edad", personas, "facpob07", "personas")]
    filas = []
    for grupo, col, df, peso, unidad in grupos:
        partes = [("Perú", df)] if col is None else df.groupby(col, observed=True)
        for categoria, d in partes:
            filas.append({"grupo": grupo, "codigo": categoria if grupo == "departamento" else "",
                          "categoria": DEPARTAMENTOS.get(categoria, categoria) if grupo == "departamento"
                          else categoria,
                          "pobreza_pct": round(tasa(d, "pobre", peso), 2),
                          "pobreza_extrema_pct": round(tasa(d, "pobre_extremo", peso), 2),
                          "poblacion_expandida": round(float(d[peso].sum())),
                          "n_muestra": len(d), "unidad_muestra": unidad,
                          "ponderador": "factor07 × mieperho" if peso == "peso_personas" else "facpob07"})
    return pd.DataFrame(filas)


def construir(df):
    """Departamento, área, pobreza y gasto: las mismas reglas para la base de hogares y la de personas."""
    df["departamento"] = df.ubigeo.str[:2]
    df["departamento_nombre"] = df.departamento.map(DEPARTAMENTOS)
    df["urbano"] = df.estrato <= 5
    df["area"] = df.urbano.map({True: "Urbana", False: "Rural"})
    df["lima_metropolitana"] = df.dominio == 8
    df["pobre"] = df.pobreza <= 2
    df["pobre_extremo"] = df.pobreza == 1
    df["gasto_pc_mensual"] = df.gashog2d / df.mieperho / 12
    return df


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--anio", type=int, default=2024)
    p.add_argument("--datos", type=Path, default=RAIZ / "datos")
    p.add_argument("--salidas", type=Path, default=RAIZ / "salidas")
    a = p.parse_args()
    if a.anio not in CODIGO_INEI:
        sys.exit(f"ERROR: solo está preparada la ENAHO {', '.join(map(str, CODIGO_INEI))}; no hay referencia "
                 f"para validar {a.anio}.")
    cod = CODIGO_INEI[a.anio]
    zip34, zip02 = a.datos / f"{cod}-Modulo34.zip", a.datos / f"{cod}-Modulo02.zip"
    faltan = [z.name for z in (zip34, zip02) if not z.exists()]
    if faltan:
        sys.exit(f"ERROR: faltan {', '.join(faltan)} en {a.datos}. Bájenlos del INEI: "
                 f"https://proyectos.inei.gob.pe/iinei/srienaho/descarga/STATA/{cod}-Modulo34.zip y "
                 f"https://proyectos.inei.gob.pe/iinei/srienaho/descarga/STATA/{cod}-Modulo02.zip")

    # 1-2. Leer y normalizar
    sumaria = leer_stata(zip34, f"{cod}-Modulo34/sumaria-{a.anio}.dta")
    miembros = leer_stata(zip02, f"{cod}-Modulo02/enaho01-{a.anio}-200.dta")

    # 3. Residentes habituales: miembro presente que no está ausente 30 días o más, o no miembro que está
    #    presente 30 días o más. Las personas sin dato en p204 quedan fuera.
    residente = (((miembros.p204 == 1) & (miembros.p205 == 2)) | ((miembros.p204 == 2) & (miembros.p206 == 1)))
    personas = miembros.loc[residente, LLAVES + ["codperso", "ubigeo", "p207", "p208a", "facpob07"]]
    personas = personas.rename(columns={"ubigeo": "ubigeo_modulo02"})

    # 4. Unir personas (muchas) con su hogar (uno)
    hogares = sumaria[LLAVES + ["ubigeo", "dominio", "estrato", "pobreza", "factor07", "mieperho", "linea",
                                "linpe", "gashog2d", "inghog2d"]]
    base = personas.merge(hogares, on=LLAVES, how="left", validate="m:1", indicator=True)

    # 5. Indicadores
    hogares = construir(hogares.copy())
    hogares["peso_personas"] = hogares.factor07 * hogares.mieperho
    base = construir(base)
    base["sexo"] = base.p207.map({1: "Hombre", 2: "Mujer"})
    base["edad"] = base.p208a.where(base.p208a != 99)    # 99 = sin dato, según el diccionario del INEI
    base["grupo_edad"] = pd.cut(base.edad, [g[0] - 0.5 for g in GRUPOS_EDAD] + [200.5],
                                labels=[g[2] for g in GRUPOS_EDAD]).astype("string")

    # 6. Validar
    controles = []

    def control(nombre, ok, detalle, esencial=True):
        controles.append({"nombre": nombre, "ok": bool(ok), "detalle": detalle, "esencial": esencial})

    dup_hog = int(sumaria.duplicated(LLAVES).sum())
    control("Llaves únicas en la sumaria (conglome, vivienda, hogar)", dup_hog == 0,
            f"{len(sumaria):,} hogares, {dup_hog} duplicados (referencia: {REFERENCIA['hogares']:,} hogares)")
    dup_per = int(miembros.duplicated(LLAVES + ["codperso"]).sum())
    control("Llaves únicas en el módulo 02 (conglome, vivienda, hogar, codperso)", dup_per == 0,
            f"{len(miembros):,} filas, {dup_per} duplicadas (referencia: {REFERENCIA['filas_modulo02']:,})")
    malas = {c: int((df[c].str.len() != n).sum()) for c, n in LARGO_LLAVES.items()
             for df in (sumaria, miembros) if c in df.columns}
    control("Llaves leídas como texto, con sus ceros iniciales", sum(malas.values()) == 0,
            "largos esperados " + ", ".join(f"{c}={n}" for c, n in LARGO_LLAVES.items())
            + f"; códigos con otro largo: {sum(malas.values())}")
    control("Residentes habituales", len(personas) == REFERENCIA["residentes"],
            f"{len(personas):,} de {len(miembros):,} filas del módulo 02 (referencia: {REFERENCIA['residentes']:,})")
    sin_hogar = int((base._merge != "both").sum())
    control("Unión m:1 sin perder ni duplicar personas", len(base) == len(personas) and sin_hogar == 0,
            f"{len(personas):,} personas antes, {len(base):,} después; {sin_hogar} sin hogar en la sumaria")
    distinto = int((base.ubigeo != base.ubigeo_modulo02).sum())
    control("El ubigeo de la persona coincide con el de su hogar", distinto == 0,
            f"{distinto} personas con ubigeo distinto entre módulos", esencial=False)
    deps = sorted(base.departamento.unique())
    control("25 códigos de departamento (01 a 25)", deps == sorted(DEPARTAMENTOS),
            f"{len(deps)} códigos: {deps[0]} a {deps[-1]}")
    coincide = float(((hogares.gasto_pc_mensual < hogares.linea) == hogares.pobre).mean() * 100)
    control("La pobreza del INEI equivale a gasto per cápita menor que la línea de pobreza", coincide == 100,
            f"coincide en {coincide:.2f} % de los hogares (gashog2d / mieperho / 12 frente a linea)")
    faltan_dem = int(base.sexo.isna().sum() + base.edad.isna().sum())
    control("Sexo y edad completos en los residentes", faltan_dem == 0,
            f"{faltan_dem} datos faltantes de sexo (p207) o edad (p208a)", esencial=False)
    pesos_malos = int((base.facpob07.isna() | (base.facpob07 <= 0)).sum())
    control("Factor de expansión facpob07 completo y positivo", pesos_malos == 0,
            f"{pesos_malos} personas sin factor válido; población expandida {base.facpob07.sum():,.0f}")

    pob_hogares = tasa(hogares, "pobre", "peso_personas")
    pob_personas = tasa(base, "pobre", "facpob07")
    pob_simple = float(hogares.pobre.mean() * 100)
    control("Pobreza monetaria nacional (hogares, factor07 × mieperho, método del INEI)",
            abs(pob_hogares - REFERENCIA["pobreza"]) <= TOLERANCIA_PP,
            f"{pob_hogares:.2f} % (referencia {REFERENCIA['pobreza']} %, tolerancia ±{TOLERANCIA_PP} pp)")
    control("Pobreza monetaria nacional (personas residentes, facpob07)",
            abs(pob_personas - REFERENCIA["pobreza"]) <= TOLERANCIA_PP,
            f"{pob_personas:.2f} %; diferencia con el método por hogares: {pob_personas - pob_hogares:+.2f} pp")
    control("Los factores de expansión cambian el resultado (no es un promedio simple)",
            abs(pob_simple - pob_hogares) > TOLERANCIA_PP,
            f"promedio simple de hogares sin ponderar {pob_simple:.2f} % frente a {pob_hogares:.2f} % "
            "ponderado: se usa siempre el ponderado", esencial=False)
    for nombre, filtro, ref in [("urbana", hogares.urbano, "urbana"), ("rural", ~hogares.urbano, "rural")]:
        v = tasa(hogares[filtro], "pobre", "peso_personas")
        control(f"Pobreza {nombre} (estrato {'<= 5' if nombre == 'urbana' else '>= 6'}, hogares)",
                abs(v - REFERENCIA[ref]) <= TOLERANCIA_PP,
                f"{v:.2f} % (referencia {REFERENCIA[ref]} %)", esencial=False)
    v = tasa(hogares, "pobre_extremo", "peso_personas")
    control("Pobreza extrema nacional (hogares)", abs(v - REFERENCIA["extrema"]) <= TOLERANCIA_PP,
            f"{v:.2f} % (referencia {REFERENCIA['extrema']} %)", esencial=False)
    v = tasa(hogares[hogares.lima_metropolitana], "pobre", "peso_personas")
    control("Pobreza de Lima Metropolitana (dominio 8, hogares)",
            abs(v - REFERENCIA["lima_metropolitana"]) <= TOLERANCIA_PP,
            f"{v:.2f} % (referencia {REFERENCIA['lima_metropolitana']} %)", esencial=False)

    # Reporte
    a.salidas.mkdir(exist_ok=True)
    fallas = [c for c in controles if not c["ok"] and c["esencial"]]
    lineas = [f"VALIDACIÓN ENAHO {a.anio} · skill limpiando-enaho",
              f"Ejecutado: {datetime.now():%Y-%m-%d %H:%M}",
              f"Archivos: {zip34.name} (sumaria-{a.anio}.dta) y {zip02.name} (enaho01-{a.anio}-200.dta)",
              "Unidades de análisis: hogares (sumaria, factor07 × mieperho) para cifras nacionales y "
              "territoriales;",
              "personas residentes habituales (módulo 02, facpob07) para sexo y edad.", ""]
    for c in controles:
        marca = "APROBADO" if c["ok"] else ("FALLÓ   " if c["esencial"] else "REVISAR ")
        lineas.append(f"[{marca}] {'(esencial) ' if c['esencial'] else ''}{c['nombre']}: {c['detalle']}")
    aprobados = sum(c["ok"] for c in controles)
    lineas += ["", f"Resultado: {aprobados} de {len(controles)} verificaciones aprobadas; "
               f"esenciales fallidas: {len(fallas)}."]
    lineas.append(f"Bases guardadas en salidas/personas_{a.anio}.parquet y salidas/hogares_{a.anio}.parquet."
                  if not fallas else
                  "PROCESO DETENIDO: no se guardó la base porque fallaron verificaciones esenciales.")
    texto = "\n".join(lineas) + "\n"
    (a.salidas / "validacion.txt").write_text(texto, encoding="utf-8")
    print(texto)
    if fallas:
        sys.exit(1)

    # 7. Guardar
    columnas = LLAVES + ["codperso", "ubigeo", "departamento", "departamento_nombre", "dominio", "estrato",
                         "urbano", "area", "lima_metropolitana", "sexo", "edad", "grupo_edad", "pobreza",
                         "pobre", "pobre_extremo", "linea", "linpe", "gasto_pc_mensual", "facpob07", "factor07",
                         "mieperho"]
    base[columnas].to_parquet(a.salidas / f"personas_{a.anio}.parquet", index=False)
    columnas_hogar = LLAVES + ["ubigeo", "departamento", "departamento_nombre", "dominio", "estrato", "urbano",
                               "area", "lima_metropolitana", "pobreza", "pobre", "pobre_extremo", "linea", "linpe",
                               "gasto_pc_mensual", "factor07", "mieperho", "peso_personas"]
    hogares[columnas_hogar].to_parquet(a.salidas / f"hogares_{a.anio}.parquet", index=False)
    tabla = indicadores(hogares, base)
    tabla.insert(0, "anio", a.anio)
    tabla.to_csv(a.salidas / "indicadores.csv", index=False, encoding="utf-8")
    print(f"Guardados: salidas/personas_{a.anio}.parquet ({len(base):,} personas), "
          f"salidas/hogares_{a.anio}.parquet ({len(hogares):,} hogares) y salidas/indicadores.csv "
          f"({len(tabla)} filas).")


if __name__ == "__main__":
    main()

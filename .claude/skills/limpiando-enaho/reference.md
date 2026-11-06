# Referencia de la ENAHO 2024

Etiquetas tomadas del `Diccionario2024.pdf` del INEI, que viene dentro de los dos zip.

## Archivos

| Zip | Archivo | Una fila por | Filas | Llaves |
|---|---|---|---|---|
| `966-Modulo34.zip` | `sumaria-2024.dta` (sumaria por 8 grupos de gasto) | hogar | 33,691 | `conglome`, `vivienda`, `hogar` |
| `966-Modulo02.zip` | `enaho01-2024-200.dta` (características de los miembros) | persona | 117,721 | las tres + `codperso` |

El zip 34 también trae `sumaria-2024-12g.dta` (12 grupos de gasto). Da la misma pobreza (27.58 %), pero la
skill usa `sumaria-2024.dta`.

## Llaves y territorio

| Variable | Tipo | Qué es |
|---|---|---|
| `conglome` | texto, 6 | Conglomerado |
| `vivienda` | texto, 3 | Vivienda dentro del conglomerado |
| `hogar` | texto, 2 | Hogar dentro de la vivienda |
| `codperso` | texto, 2 | Persona dentro del hogar (módulo 02) |
| `ubigeo` | texto, 6 | Departamento (2), provincia (2), distrito (2). `ubigeo[:2]` es el departamento, de 01 a 25, con Lima (15) y Callao (07) por separado |
| `dominio` | número | 1 Costa Norte, 2 Costa Centro, 3 Costa Sur, 4 Sierra Norte, 5 Sierra Centro, 6 Sierra Sur, 7 Selva, 8 Lima Metropolitana |
| `estrato` | número | 1: 500 000 a más habitantes · 2: 100 000 a 499 999 · 3: 50 000 a 99 999 · 4: 20 000 a 49 999 · 5: 2 000 a 19 999 · 6: 500 a 1 999 · 7: Área de Empadronamiento Rural (AER) compuesto · 8: AER simple |

Regla del curso: **urbano = `estrato <= 5`**, rural = `estrato >= 6`.

Las llaves se leen como texto (`astype("string")`). Si se leen como número, se pierden los ceros
iniciales y fallan las uniones: `"010101"` se vuelve `10101`.

## Pobreza (módulo 34)

| Variable | Qué es |
|---|---|
| `pobreza` | 1 pobre extremo, 2 pobre no extremo, 3 no pobre. Pobre = `pobreza <= 2`; extremo = `pobreza == 1` |
| `linea` | Línea de pobreza total, en soles por persona al mes |
| `linpe` | Línea de pobreza extrema (alimentaria), en soles por persona al mes |
| `gashog2d` | Gasto total bruto anual del hogar. Gasto per cápita mensual = `gashog2d / mieperho / 12` |
| `inghog2d` | Ingreso neto total anual del hogar |
| `mieperho` | Total de miembros del hogar |
| `factor07` | Factor de expansión anual del hogar (proyecciones CPV-2007) |

Un hogar es pobre si su gasto per cápita mensual es menor que `linea`. La limpieza comprueba que esto se cumpla
en el 100 % de los hogares.

## Personas (módulo 02)

| Variable | Qué es |
|---|---|
| `p204` | ¿Es miembro del hogar? 1 sí, 2 no |
| `p205` | ¿Se encuentra ausente del hogar 30 días o más? 1 sí, 2 no |
| `p206` | ¿Está presente en el hogar 30 días o más? (para no miembros) 1 sí, 2 no |
| `p207` | Sexo: 1 hombre, 2 mujer |
| `p208a` | Edad en años cumplidos (1 a 98; 99 = sin dato) |
| `facpob07` | Factor de expansión de la población |

**Residentes habituales:** `((p204 == 1) & (p205 == 2)) | ((p204 == 2) & (p206 == 1))`, es decir, los miembros
que no están ausentes 30 días o más y los no miembros que están presentes 30 días o más. Son 108,664.

## Qué ponderador usar

| Pregunta | Base | Ponderador | Pobreza nacional |
|---|---|---|---|
| Nacional, área, departamento, dominio (cifra oficial del INEI) | `hogares_2024.parquet` | `peso_personas` = `factor07 × mieperho` | 27.58 % |
| Sexo, edad u otra característica de la persona | `personas_2024.parquet` | `facpob07` | 27.53 % |

La diferencia, de 0.05 puntos, existe porque `mieperho` cuenta 109,842 personas y los residentes habituales son
108,664. Con el método por hogares se reproducen exactamente los 25 departamentos de la referencia de la
Sesión 16. Sin ponderar, la pobreza de los hogares daría 20.22 %, una cifra que no es válida.

## Bases que deja la skill

- `salidas/hogares_2024.parquet`: una fila por hogar, con `departamento`, `departamento_nombre`, `area`,
  `urbano`, `lima_metropolitana`, `pobre`, `pobre_extremo`, `gasto_pc_mensual`, `linea`, `linpe` y `peso_personas`.
- `salidas/personas_2024.parquet`: una fila por residente habitual, con lo mismo más `codperso`, `sexo`, `edad`,
  `grupo_edad` (0 a 14, 15 a 29, 30 a 44, 45 a 59 y 60 años a más) y `facpob07`.
- `salidas/indicadores.csv`: pobreza y pobreza extrema por grupo, con la población expandida, el tamaño de
  muestra y el ponderador.
- `salidas/validacion.txt`: las verificaciones, con APROBADO, FALLÓ o REVISAR.

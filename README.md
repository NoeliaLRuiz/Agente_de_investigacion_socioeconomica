# Agente de investigación socioeconómica: MCP, Skills y datos oficiales del Perú

Tarea 4 del curso Python Intermedio. Es un agente de Claude Code que responde preguntas sobre la realidad
socioeconómica del Perú con dos fuentes oficiales:

- **BCRP:** las series estadísticas, que consulta con un servidor MCP propio.
- **INEI, ENAHO 2024:** los microdatos, que procesa con Skills de Claude Code.

Todas las cifras salen de código que se puede volver a correr y verificar. Ninguna sale de la memoria del modelo.

**Pregunta de investigación:** ¿La inversión de los gobiernos regionales y locales por habitante fue mayor en los
departamentos con más pobreza entre 2020 y 2024?

**Respuesta corta: no.** La correlación entre la pobreza de 2024 y la inversión real por habitante de 2020 a 2024 es
negativa y débil: Spearman −0.33 (p = 0.10, por permutaciones) en los 25 departamentos. El informe completo está en
[`informes/informe_final.md`](informes/informe_final.md).

## Arquitectura

```text
Pregunta en lenguaje natural
        │
        ▼
   Claude Code ── .mcp.json ──► MCP bcrp (mcp/server.py) ──► API del BCRP
        │                         buscar_series · serie · resumen · comparar_periodos
        │                         graficar_serie · exportar_series · recurso · 2 prompts
        │                                   │
        │                                   ├─► salidas/bcrp_*.csv   (exportar_series)
        │                                   └─► figuras/bcrp_*.png   (graficar_serie)
        │
        └── .claude/skills/ ──► limpiando-enaho ───► salidas/hogares_2024.parquet, personas_2024.parquet,
                                (datos/ del INEI)     indicadores.csv, validacion.txt
                              ► graficando-enaho ──► figuras/enaho_*.png
                              ► mapeando-enaho ────► mapas/pobreza_departamento.png
                              ► cruzando-inversion-pobreza (BCRP + ENAHO) ──► salidas/cruce_*, figuras/cruce_*,
                                                                              mapas/inversion_por_habitante.png
        │
        ▼
informes/informe_final.md
```

- Los cálculos los hace Python, en el servidor MCP y en los scripts de las Skills. El modelo decide qué herramienta
  usar y redacta el resultado.
- Los datos pasan del BCRP al análisis por archivos: `exportar_series` guarda un CSV y la Skill del cruce lo lee.
- Ninguna cifra se copia a mano.

## Herramientas del servidor MCP (`mcp/server.py`)

| Herramienta | Qué hace |
|---|---|
| `buscar_series` | Busca series en el catálogo oficial del BCRP (17 mil series) por palabras clave y frecuencia |
| `serie` | Descarga los datos de una serie entre dos fechas, con la URL de la API como fuente |
| `resumen` | Calcula para un periodo el primer y el último dato, el cambio, la variación %, el promedio, el máximo y el mínimo |
| `comparar_periodos` | **Herramienta propia.** Compara una serie en dos intervalos que no se superponen: promedios, extremos, diferencia y variación entre promedios. Avisa si los intervalos tienen distinto número de datos y da error si se superponen |
| `graficar_serie` | Guarda un gráfico de línea de una serie en `figuras/`, con título, unidad y fuente |
| `exportar_series` | Descarga muchas series de una vez a `salidas/<archivo>.csv`. Si una serie no existe, la lista en «faltantes» y no la inventa |
| Recurso `bcrp://serie/{codigo}` | Ficha de la serie en JSON: nombre, categoría, frecuencia, inicio y última actualización |
| Prompt `informe(tema)` | Informe de cinco viñetas, con el código y el periodo de cada cifra |
| Prompt `interpretar_indicador(indicador, desde, hasta)` | Interpreta un indicador y lo compara con el periodo anterior, sin afirmar causas |

**Pruebas: 10 de 10.** Son las 8 originales de la Sesión 04, sin cambios, más 2 propias de `comparar_periodos`:

- una comprueba sus cuentas contra un cálculo a mano;
- otra comprueba que dé error si los periodos se superponen.

## Skills (`.claude/skills/`)

| Skill | Qué hace | Salidas |
|---|---|---|
| `limpiando-enaho` | Lee los módulos 34 y 02 con las llaves como texto y normaliza los nombres. Filtra los residentes habituales y une personas con hogares (`validate="m:1"`). Construye pobreza, área y departamento, y corre 17 verificaciones. Si falla una esencial, se detiene | `salidas/validacion.txt`, `indicadores.csv` y las dos bases `.parquet` |
| `graficando-enaho` | Gráficos ponderados por área, sexo, edad y departamento, con título analítico, unidad y fuente | `figuras/enaho_*.png` |
| `mapeando-enaho` | Mapa coroplético. Une `ubigeo[:2]` con `FIRST_IDDP` como texto, exige 25 departamentos (Lima y Callao separados) y compara con la referencia de la Sesión 16 | `mapas/pobreza_departamento.png`, `salidas/comparacion_mapa.csv` |
| `cruzando-inversion-pobreza` | Skill adicional. Cruza las 53 series de inversión del BCRP con la pobreza y la población de la ENAHO. Pasa la inversión a soles de 2024 con el IPC, calcula correlaciones y valida que los departamentos sumen el total del BCRP | `salidas/cruce_*`, `figuras/cruce_*`, `mapas/inversion_por_habitante.png` |

`graficando`, `mapeando` y `cruzando` corren primero `limpiando-enaho` si no existe la base limpia. Esto está probado
en `evidencias_ia/skills/02_encadenamiento_mapa.txt`.

**Validación ENAHO 2024** (`salidas/validacion.txt`):

| Indicador | Resultado | Referencia |
|---|---|---|
| Pobreza nacional | 27.58 % por hogares (`factor07 × mieperho`, método del INEI); 27.53 % por personas (`facpob07`) | 27.6 % |
| Residentes habituales | 108,664 | 108,664 |
| Pobreza urbana / rural | 24.81 % / 39.30 % | 24.8 % / 39.3 % |
| Departamentos | 25 de 25; coinciden con la Sesión 16 (diferencia máxima 0.00 puntos) | 25 |

Para el nivel nacional, el área y el departamento uso la base de hogares, como el INEI. Para el sexo y la edad, que
son características de las personas, uso la base de personas con `facpob07`. La explicación completa está en
`.claude/skills/limpiando-enaho/reference.md`.

## Datos

No se suben a GitHub (`.gitignore`). Hay que bajarlos a `datos/`:

| Archivo | Enlace |
|---|---|
| ENAHO 2024, módulo 34 (sumaria) | https://proyectos.inei.gob.pe/iinei/srienaho/descarga/STATA/966-Modulo34.zip |
| ENAHO 2024, módulo 02 (miembros) | https://proyectos.inei.gob.pe/iinei/srienaho/descarga/STATA/966-Modulo02.zip |
| Límites departamentales | https://raw.githubusercontent.com/d2cml-ai/Data-Science-Python/main/sessions/06-geoespacial/lab/Data/peru_departamental_simple.geojson |
| Series del BCRP | https://estadisticas.bcrp.gob.pe/estadisticas/series/. El servidor las descarga solo; el catálogo se guarda en `mcp/datos/` |

## Instalación

Requiere [uv](https://docs.astral.sh/uv/), Python 3.14 o superior y [Claude Code](https://code.claude.com).

```bash
git clone https://github.com/NoeliaLRuiz/Agente_de_investigacion_socioeconomica.git
cd Agente_de_investigacion_socioeconomica
uv sync                      # instala fastmcp, pandas, pyarrow, geopandas, matplotlib, httpx y pytest
```

## Conectar el MCP a Claude Code

El proyecto ya trae `.mcp.json`:

```json
{ "mcpServers": { "bcrp": { "type": "stdio", "command": "uv", "args": ["run", "mcp/server.py"] } } }
```

1. Abre Claude Code **en la raíz del proyecto** (`claude`). Si lo abres en otra carpeta, no verá `.mcp.json` ni las
   Skills.
2. Acepta el servidor `bcrp` cuando Claude Code pregunte.
3. Comprueba con `/mcp` (debe decir `bcrp` conectado) y con `/skills` (deben aparecer las 4 Skills).

## Reproducir

```bash
uv run pytest                                                          # 10 passed
uv run .claude/skills/limpiando-enaho/scripts/limpiar.py --anio 2024   # 17 de 17 verificaciones
uv run .claude/skills/graficando-enaho/scripts/graficar.py             # 4 gráficos
uv run .claude/skills/mapeando-enaho/scripts/mapear.py                 # mapa, 25 de 25 departamentos
uv run .claude/skills/cruzando-inversion-pobreza/scripts/cruzar.py     # cruce BCRP-ENAHO
uv run evaluacion/evaluar.py                                           # evaluación, 10 preguntas x 2 modos
```

El cruce usa los CSV del BCRP que están en `salidas/`. Para volver a bajarlos sin Claude Code, con las mismas
funciones del servidor MCP:

```bash
uv run python -c "import sys; sys.path.insert(0, 'mcp'); import server, pandas as pd; c = pd.read_csv('.claude/skills/cruzando-inversion-pobreza/referencia/series_bcrp.csv').codigo.tolist(); server.exportar_series(c, '2020', '2024', 'bcrp_inversion_2020_2024'); server.exportar_series(['PN38705PM'], '2020-01', '2024-12', 'bcrp_ipc_2020_2024')"
```

## Ejemplo de una ejecución completa

Pegué en Claude Code el pedido de [`informes/pedido_investigacion.md`](informes/pedido_investigacion.md). En una sola
sesión de 5 min 46 s, el agente hizo esto:

1. Escribió un plan con la fuente y la herramienta de cada paso.
2. Ubicó las series con `buscar_series` y las descargó con `exportar_series`: 53 series de inversión y 60 meses del
   IPC, sin faltantes.
3. Describió la evolución nacional con `resumen` y `comparar_periodos`, y la graficó con `graficar_serie`.
4. Corrió `limpiando-enaho` (17 de 17), `graficando-enaho`, `mapeando-enaho` (25 de 25) y
   `cruzando-inversion-pobreza`.
5. Escribió `informes/informe_final.md` con 5 hallazgos y 7 figuras.
6. Probó si podía repetir el análisis con la pobreza de 2025. Informó que no hay microdatos de 2025 y no estimó
   ninguna cifra.

El registro completo está en
[`evidencias_ia/integracion/01_investigacion_completa.txt`](evidencias_ia/integracion/01_investigacion_completa.txt).
La sección 8 del informe tiene la verificación manual de 5 cifras, hecha en la web del BCRP, en el informe del INEI y
en Excel.

## Resultados de la evaluación

Usé 10 preguntas con respuestas verificadas en fuentes oficiales: 4 del BCRP, 4 de la ENAHO y 2 combinadas. Las
respuestas esperadas se subieron en un commit antes de evaluar. Cada pregunta corrió en una sesión independiente, con
el mismo modelo (`claude-sonnet-5-5`) en los dos modos.

| Modo | Correctas | Incorrectas | No responde | Tiempo promedio |
|---|---:|---:|---:|---:|
| A, sin MCP ni Skills | 3 | 0 | 7 | 6.2 s |
| B, con MCP y Skills | 8 (10 con revisión manual) | 2 | 0 | 19.4 s |

Las 2 incorrectas del modo B son falsos positivos del filtro automático de causalidad: marcó la frase «no se afirma
ninguna relación causal». El análisis completo está en [`evaluacion/comparacion.md`](evaluacion/comparacion.md) y los
datos en [`evaluacion/resultados.csv`](evaluacion/resultados.csv).

## Limitaciones y problemas encontrados

- **Análisis:**
  - La pobreza es de 2024, y la inversión es el promedio de 2020 a 2024.
  - La población es la expandida de la ENAHO 2024, igual para todos los años.
  - No se incluye la inversión del gobierno nacional.
  - Con 25 departamentos, el resultado es descriptivo y no causal.
- **Solo ENAHO 2024:** `limpiar.py` solo está preparado para 2024. Con otro año se detiene con un mensaje claro.
- **Errores encontrados en la evaluación:**
  - El modo B inventó un «error estándar de 2.1» en Cusco: confundió la columna de pobreza extrema.
  - El filtro de causalidad no reconoce las negaciones.
  - En la corrida 1, el modo B podía ver `preguntas.csv`. Lo corregí bloqueando `evaluacion/` y repetí la
    evaluación.
- **Problemas del proceso, ya corregidos:**
  - `graficar_serie` rotulaba las series anuales con meses.
  - Una sangría mal puesta rompió `mapear.py`, y Claude Code la corrigió (`evidencias_ia/skills/02_encadenamiento_mapa.txt`).
  - Los argumentos de los prompts MCP se separan por espacios en Claude Code: hay que escribir cada argumento en una
    sola palabra.
- **Windows:**
  - Si hay otro entorno virtual activo, `uv` muestra un aviso (`VIRTUAL_ENV`): basta con `deactivate`.
  - En `claude -p`, los comandos compuestos (`cd ... && ...`) pueden necesitar permiso.

## Evidencias del uso de IA

El proyecto se desarrolló con apoyo de Claude Code (Opus 5.5 y Sonnet 5.5). 

| Carpeta | Contenido |
|---|---|
| `evidencias_ia/desarrollo/` | La conversación en la que se planificó y desarrolló el proyecto con Claude Code: servidor, Skills, cruce, evaluación y README |
| `evidencias_ia/mcp/` | Pruebas del MCP en Claude Code: búsqueda, resumen, comparación, recurso, prompt y gráfico |
| `evidencias_ia/skills/` | Activación de las Skills, individual y en lenguaje natural, y el encadenamiento limpiando → mapeando |
| `evidencias_ia/integracion/` | La ejecución integradora completa y la corrección de los gráficos |
| `evidencias_ia/evaluacion/` | El registro de cada una de las 20 llamadas de la evaluación (corrida 2) y la corrida 1 en `corrida1/` |

## Estructura

```text
├── README.md · pyproject.toml · uv.lock · .mcp.json · .gitignore
├── mcp/                  server.py, test_server.py (10 pruebas)
├── .claude/skills/       limpiando-enaho · graficando-enaho · mapeando-enaho · cruzando-inversion-pobreza
├── datos/                microdatos del INEI y GeoJSON (no se suben)
├── salidas/              validacion.txt, indicadores.csv, CSV del BCRP y del cruce
├── figuras/  mapas/
├── evaluacion/           preguntas.csv, evaluar.py, resultados.csv, resumen_modos.csv, comparacion.md, corrida1/
├── informes/             informe_final.md, pedido_investigacion.md
└── evidencias_ia/        desarrollo/, mcp/, skills/, integracion/, evaluacion/
```

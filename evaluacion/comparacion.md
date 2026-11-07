# Evaluación: ¿mejoran el MCP y las Skills las respuestas de Claude Code?

Respondí las mismas 10 preguntas en dos modos de Claude Code, que se diferencian solo en las herramientas.

- **Modo A**, sin el MCP ni las Skills del proyecto.
- **Modo B**, con el MCP del BCRP y las Skills de la ENAHO.

Los resultados oficiales son los de la **corrida 2** (07-11-2026), que está en `resultados.csv`. La **corrida 1**
(06-11-2026), en `corrida1/`, se conserva porque en ella encontré un problema de aislamiento, que se describe en la
sección 5.

## 1. Diseño

**Preguntas (`preguntas.csv`).** Son 10:

- 4 del BCRP: inflación de diciembre de 2024, tasa de referencia, inversión total de los gobiernos regionales en 2024
  e inversión del gobierno regional de Cajamarca en 2024.
- 4 de la ENAHO 2024: pobreza nacional, rural, extrema y de Cusco.
- 2 que combinan las dos fuentes: el departamento más pobre y la inversión de su gobierno regional; y el crecimiento
  de la inversión regional de Puno junto con su pobreza.

Cada respuesta esperada tiene su fuente en el archivo:

- las tablas web del BCRP;
- el informe del INEI *Perú: Evolución de la pobreza monetaria 2015-2024*;
- para Cusco y Cajamarca, el cálculo independiente de la Sesión 16.

Las respuestas esperadas y las tolerancias se subieron en el commit `8648b95`, **antes** de la primera corrida, y no
se cambiaron después.

**Criterio de corrección**, definido en `evaluar.py` antes de correr:

- *Correcta:* cada cifra cae dentro de su tolerancia. En las combinadas, además, la respuesta nombra lo pedido
  («Cajamarca», «mayor») y un filtro automático no encuentra palabras causales (*causa*, *provoca*, *gracias a*…).
- *Incorrecta:* alguna cifra o palabra no coincide, o el filtro marca una afirmación causal.
- *No responde:* el modelo no da ninguna cifra. La instrucción le pide no estimar.

**Condiciones.**

| | Modo A | Modo B |
|---|---|---|
| Carpeta de trabajo | Carpeta temporal vacía, fuera del repositorio | Raíz del repositorio |
| MCP | Ninguno (`--strict-mcp-config`). Tampoco el MCP `mef` que tengo instalado para mi usuario | `bcrp` (`.mcp.json`) |
| Skills | No | Sí (`.claude/skills/`) |
| Otras herramientas | Ninguna (`--tools ""`): sin archivos, sin terminal, sin web | `Skill`, `Read`, `Glob`, `Grep`, y la terminal solo para `uv run .claude/skills/...`, `cd` y `ls`. Sin web |
| Acceso a las respuestas | No puede leer ningún archivo | No puede leer `evaluacion/` ni `evidencias_ia/` (`--disallowedTools Read(...)`) |
| Modelo e instrucción | `claude-sonnet-5-5`, la misma instrucción | Igual |
| Sesiones | Una llamada `claude -p` por pregunta, sin guardar la sesión | Igual |

El registro de cada llamada está en `evidencias_ia/evaluacion/<modo>_<pregunta>.jsonl`, con las herramientas usadas.

## 2. Resultados (corrida 2)

| Modo | Correctas | Incorrectas | No responde | Tiempo promedio | Llamadas a herramientas | Costo estimado |
|---|---:|---:|---:|---:|---:|---:|
| A, sin MCP ni Skills | 3 | 0 | 7 | 6.2 s | 0 | 0.09 USD |
| B, con MCP y Skills | 8 | 2 | 0 | 19.4 s | 27 | 0.57 USD |

Según el criterio automático, el modo B acierta 8 de 10 y el modo A, 3 de 10. Las 2 «incorrectas» del modo B son
falsos positivos del filtro causal (ver la sección 3). Con la revisión manual, el modo B da **las 10 respuestas con las
cifras correctas**.

| Pregunta | Tipo | Modo A | Modo B (automático) | Modo B (revisión manual) | Herramientas del modo B |
|---|---|---|---|---|---|
| b1 Inflación, dic. 2024 | BCRP | correcta | correcta | correcta | `buscar_series`, `serie` |
| b2 Tasa de referencia, dic. 2024 | BCRP | correcta | correcta | correcta | `buscar_series`, `serie` |
| b3 Inversión de los gobiernos regionales, 2024 | BCRP | no responde | correcta | correcta | `buscar_series`, `resumen`, `serie` |
| b4 Inversión del gobierno regional de Cajamarca, 2024 | BCRP | no responde | correcta | correcta | `buscar_series`, `serie`, `resumen` |
| e1 Pobreza nacional | ENAHO | correcta | correcta | correcta | `Grep` (salidas) |
| e2 Pobreza rural | ENAHO | no responde | correcta | correcta | `Grep`, `Bash` |
| e3 Pobreza extrema | ENAHO | no responde | correcta | correcta | `Grep`, `Read` |
| e4 Pobreza de Cusco | ENAHO | no responde | correcta | correcta, pero con un dato falso en la explicación | `Grep` |
| c1 Cajamarca: pobreza e inversión | Combinada | no responde | incorrecta | correcta | `Grep`, `Glob`, `Bash`, `Read` |
| c2 Puno: crecimiento y pobreza | Combinada | no responde | incorrecta | correcta | `buscar_series`, `Grep`, `resumen` |

## 3. Revisión manual de las preguntas combinadas

El filtro buscaba palabras como *causa* para detectar afirmaciones causales. No distingue cuando esa palabra aparece
negada:

| Pregunta | Frase que marcó el filtro | Lectura |
|---|---|---|
| c1 | «Son dos cifras de fuentes distintas y no se afirma ninguna relación **causal** entre ellas.» | La interpretación es correcta: niega la causalidad |
| c2 | «Los datos no muestran una relación **causal** entre ambas cifras.» | La interpretación es correcta |

En las dos preguntas las cifras están dentro de la tolerancia: 45.01 % y 838.27 millones en c1; 152.43 % y 39.94 % en
c2. También nombran lo pedido. No cambié el filtro después de ver los resultados, para no ajustar el criterio a
posteriori. El problema queda documentado aquí, y la mejora propuesta es que el filtro ignore las frases negadas.

## 4. Qué preguntas mejoraron o empeoraron

- **Mejoraron 7 de 10** (de «no responde» a cifras correctas): b3, b4, e2, e3, e4, c1 y c2.
  - Son los datos que el modelo no recuerda: la inversión por departamento, la pobreza rural, la extrema y la de
    Cusco, y todas las combinadas.
- **Iguales 3 de 10**: b1, b2 y e1. Las acierta en ambos modos porque son cifras muy difundidas.
  - En el modo A, el modelo aclara que las da «de memoria» y sin verificar.
  - En el modo B salen de la serie oficial del BCRP, con su código y su URL, o de los microdatos procesados
    (27.58 %).
- **Ninguna empeoró.**
  - Las 2 «incorrectas» automáticas de las combinadas pasan de «no responde» a cifras correctas; solo el filtro las
    marcó mal.

## 5. Principales errores encontrados

1. **El modo A no inventa, pero se abstiene mucho.** No dio ninguna cifra equivocada: en 7 preguntas dijo que no
   podía verificarla, tal como pedía la instrucción. Sin herramientas, el riesgo no fue alucinar, sino no poder
   responder.
2. **Un dato falso en la explicación del modo B (e4, en las dos corridas).** La cifra de Cusco fue correcta, 18.54 %.
   Pero agregó «error estándar de 2.1 puntos». Ese 2.1 es en realidad la pobreza extrema de Cusco (columna
   `pobreza_extrema_pct`): leyó con `Grep` la fila de `indicadores.csv` sin el encabezado y confundió la columna. Las
   salidas del proyecto no calculan errores estándar. El criterio automático no lo detecta, porque solo mira las
   cifras.
3. **El filtro causal da falsos positivos** con las negaciones (sección 3).
4. **Corrida 1: el modo B podía ver las respuestas esperadas.** En la pregunta rural buscó «rural» con `Grep` en todo
   el proyecto y le apareció `evaluacion/preguntas.csv`. Al final tomó el 39.3 de `salidas/indicadores.csv`, pero el
   aislamiento no era suficiente. Para la corrida 2 hice dos cambios:
   - bloqueé la lectura de `evaluacion/` y `evidencias_ia/`;
   - limité la terminal a los scripts de las Skills.

   En la corrida 2, ningún registro del modo B contiene el texto de `preguntas.csv`.
5. **En el modo B no se activó ninguna Skill.** En las preguntas de la ENAHO el modelo leyó las salidas que las Skills
   ya habían generado (`salidas/indicadores.csv`) en lugar de volver a correrlas. Es más rápido y la cifra es la
   misma. Pero significa que esta evaluación mide el MCP más los resultados de las Skills, no su activación en vivo.
   La activación de las Skills está probada aparte, en `evidencias_ia/skills/` y `evidencias_ia/integracion/`.

## 6. Corrida 1 frente a corrida 2

| | Corrida 1 (sin bloqueo) | Corrida 2 (con bloqueo) |
|---|---|---|
| Modo A: correctas, incorrectas, no responde | 3, 0, 7 | 3, 0, 7 |
| Modo B: correctas, incorrectas, no responde (automático) | 9, 1, 0 | 8, 2, 0 |
| Modo B con revisión manual: cifras correctas | 10 de 10 | 10 de 10 |
| Tiempo promedio A / B | 5.4 s / 14.7 s | 6.2 s / 19.4 s |
| Llamadas a herramientas en B | 25 | 27 |

El resultado es estable entre corridas. El modo B tardó en promedio 4.8 s más en la corrida 2. Solo un comando fue
rechazado por la restricción de la terminal: un `head` sobre `salidas/`, en c1. Por eso la diferencia parece deberse
sobre todo a la variación entre llamadas. La única «incorrecta» de la corrida 1 (c2) es el mismo falso positivo del
filtro.

## 7. Conclusión

En este experimento, el MCP y las Skills mejoran sobre todo la **cobertura** de las respuestas, más que su exactitud
sobre cifras conocidas.

- Sin ellos, Claude Code solo respondió 3 de 10 preguntas. Las tres son cifras muy difundidas, que recordaba de memoria
  y no podía verificar.
- Con ellos respondió las 10 con las cifras correctas:
  - cada cifra del BCRP con su código de serie y la URL de la API;
  - cada cifra de la ENAHO con el cálculo ponderado del proyecto;
  - en las combinadas, sin afirmar causalidad.
- El costo es de unas 3 veces más tiempo (19.4 s frente a 6.2 s) y más llamadas.
- Las herramientas no eliminan los errores de lectura: en e4 la cifra fue correcta, pero se inventó un error
  estándar. Esto muestra que hay que revisar las explicaciones, no solo los números.

**Mejoras propuestas:**

- que `indicadores.csv` y las Skills indiquen explícitamente que no hay errores estándar;
- que el filtro causal reconozca las negaciones;
- una tercera condición que borre `salidas/`, para obligar a activar las Skills en vivo.

## 8. Cómo reproducir

```bash
uv run evaluacion/evaluar.py                          # 10 preguntas x 2 modos -> resultados.csv y resumen_modos.csv
uv run evaluacion/evaluar.py --modos B --ids e4_pobreza_cusco   # una sola pregunta
```

Se necesita Claude Code (`claude`) con sesión iniciada y, para el modo B, los datos de la ENAHO en `datos/` (ver el
README).

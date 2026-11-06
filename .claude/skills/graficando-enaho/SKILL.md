---
name: graficando-enaho
description: Hace gráficos de barras de la pobreza monetaria o la pobreza extrema de la ENAHO 2024 del INEI por área urbana y rural, sexo, grupos de edad o departamento, con estimaciones ponderadas, título analítico, unidad y fuente, y los guarda en figuras/. Úsala cuando pidan graficar, visualizar o comparar en un gráfico la pobreza de la ENAHO entre grupos, áreas o departamentos.
argument-hint: "[area|sexo|edad|departamento] [pobreza|extrema]"
---

# Graficar la ENAHO

1. Si no existen `salidas/hogares_2024.parquet` y `salidas/personas_2024.parquet`, usa primero la skill
   `limpiando-enaho` y sigue solo si su validación aprueba.
2. Elige según el pedido `--por` (`area`, `sexo`, `edad`, `departamento`; puedes poner varios) y `--indicador`
   (`pobreza` o `extrema`). Desde la raíz del proyecto, por ejemplo:

   ```bash
   uv run .claude/skills/graficando-enaho/scripts/graficar.py --por area sexo --indicador pobreza
   ```

3. El script imprime las cifras de cada gráfico. Úsalas tal como salen: no las recalcules ni las redondees de
   otra forma.
4. Abre cada PNG y revisa que se lea bien el título, las etiquetas y la fuente. Responde con la ruta del archivo,
   las cifras y una lectura descriptiva, sin causas.
5. Si piden un grupo que el script no tiene (por ejemplo, nivel educativo), dilo y propone agregarlo. No inventes
   cifras ni hagas el gráfico con datos sin ponderar.

Reglas que el script ya cumple, para no romperlas si lo modificas:

- Pondera siempre: `peso_personas` (factor07 × mieperho) para área y departamento, y `facpob07` para sexo y edad.
- Usa barras horizontales que empiezan en cero, de un solo color, con el valor escrito en cada barra y una línea
  con el promedio de Perú.
- Los departamentos van ordenados de mayor a menor. Las categorías con orden natural (edad) conservan ese orden.
- El título dice qué muestra el gráfico y se arma con las cifras calculadas. El subtítulo da la unidad y el año.
- Lleva una nota al pie con la fuente y el ponderador: «Fuente: INEI, ENAHO 2024 …».
- Se guarda en PNG a 200 dpi en `figuras/enaho_<indicador>_<por>.png`.

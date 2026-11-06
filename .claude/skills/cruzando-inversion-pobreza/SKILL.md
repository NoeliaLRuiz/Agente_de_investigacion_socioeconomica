---
name: cruzando-inversion-pobreza
description: Cruza la inversión de los gobiernos regionales y locales por departamento (series del BCRP, descargadas con el MCP bcrp) con la pobreza monetaria y la población de la ENAHO 2024 del INEI. Calcula la inversión real por habitante, su correlación con la pobreza, un gráfico nacional, un gráfico de dispersión y un mapa. Úsala cuando pregunten si la inversión pública regional o local fue mayor en los departamentos más pobres, o cuando pidan relacionar inversión, gasto público o presupuesto por departamento con la pobreza.
argument-hint: "[desde] [hasta]"
---

# Cruzar inversión (BCRP) y pobreza (ENAHO)

El periodo por defecto es 2020-2024. La pobreza y la población son de la ENAHO 2024, que es la única preparada.

1. **ENAHO.** Si no existe `salidas/indicadores.csv`, usa primero la skill `limpiando-enaho` y sigue solo si su
   validación aprueba.
2. **BCRP con el MCP.** Si faltan `salidas/bcrp_inversion_2020_2024.csv` o `salidas/bcrp_ipc_2020_2024.csv`:
   - Corre `uv run .claude/skills/cruzando-inversion-pobreza/scripts/cruzar.py --codigos`. Imprime las dos
     llamadas que debes hacer, con sus códigos, fechas y nombre de archivo.
   - Haz esas dos llamadas a la herramienta `exportar_series` del MCP `bcrp`, tal como salen. Son 53 series de
     inversión bruta fija (26 de gobiernos locales, 25 departamentos más el total; 27 de gobiernos regionales, con
     la Municipalidad Metropolitana de Lima y el total) y el IPC de Lima PN38705PM, mensual.
   - Si `exportar_series` lista series en «faltantes», detente e informa cuáles. No las reemplaces por otras.
   - No copies cifras a mano en los CSV.
3. **Cruce.** Desde la raíz del proyecto corre:

   ```bash
   uv run .claude/skills/cruzando-inversion-pobreza/scripts/cruzar.py
   ```

4. Lee `salidas/cruce_resultados.txt`. Si hay `[FALLÓ]` o el script termina con error, detente y explica qué
   falló. Comprueba, entre otras cosas, que los departamentos sumen el total del BCRP y que la unión por código dé
   25 de 25.
5. Abre las tres figuras y responde con las cifras tal como salen en `cruce_resultados.txt`:
   `figuras/bcrp_inversion_gr_gl.png`, `figuras/cruce_inversion_pobreza.png` y `mapas/inversion_por_habitante.png`.
   La tabla por departamento está en `salidas/cruce_inversion_pobreza.csv`.

Cómo leer el resultado:

- La inversión está en soles de 2024: cada año se deflacta con el promedio anual del IPC de Lima. Por habitante
  significa la inversión real de 2020 a 2024 dividida entre la población expandida de la ENAHO 2024 y entre 5 años.
- Lima suma el gobierno regional de Lima, la Municipalidad Metropolitana de Lima y los gobiernos locales de Lima.
  No incluye la inversión del gobierno nacional, que se concentra en Lima. Lo mismo vale para todos los
  departamentos.
- Una correlación negativa significa que los departamentos más pobres tuvieron menos inversión por habitante.
  Con 25 departamentos, el valor p por permutaciones indica si la asociación podría deberse al azar.
- Es una asociación descriptiva: no muestra que la inversión cause más o menos pobreza. La causalidad también
  puede ir al revés, y hay factores que no se miden aquí, como el canon minero o la capacidad de gasto de cada
  gobierno.

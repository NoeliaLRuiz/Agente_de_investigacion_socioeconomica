---
name: mapeando-enaho
description: Hace el mapa coroplético de la pobreza monetaria o la pobreza extrema por departamento del Perú con la ENAHO 2024 del INEI. Une las cifras con los límites departamentales por código (ubigeo y FIRST_IDDP), con 25 departamentos y Lima y Callao por separado, y valida el resultado contra la referencia de la Sesión 16. Úsala cuando pidan un mapa de la pobreza por departamento o región, o su distribución territorial.
argument-hint: "[pobreza|extrema]"
---

# Mapear la ENAHO

1. Si no existe `salidas/hogares_2024.parquet`, usa primero la skill `limpiando-enaho` y sigue solo si su
   validación aprueba.
2. Si falta `datos/peru_departamental_simple.geojson`, pide al usuario que lo baje de
   https://raw.githubusercontent.com/d2cml-ai/Data-Science-Python/main/sessions/06-geoespacial/lab/Data/peru_departamental_simple.geojson
   y detente.
3. Desde la raíz del proyecto corre:

   ```bash
   uv run .claude/skills/mapeando-enaho/scripts/mapear.py --indicador pobreza
   ```

4. Lee lo que imprime el script. Si dice `ERROR` (unión incompleta, departamentos sin dato o cifras distintas de
   la referencia), detente e informa el problema. No unas por nombre ni corrijas las cifras a mano.
5. Abre `mapas/pobreza_departamento.png` y compáralo con
   [referencia/mapa_pobreza_2024.png](referencia/mapa_pobreza_2024.png): los departamentos más oscuros deben ser
   los mismos. Responde con la ruta del mapa, los 3 departamentos con más pobreza y el de menos, y la línea de
   comparación con la referencia (`salidas/comparacion_mapa.csv`).

Reglas que el script ya cumple:

- Une por código y nunca por nombre: `ubigeo[:2]` con `FIRST_IDDP`, los dos como texto de 2 dígitos y con
  `validate="1:1"`. «APURIMAC» no es «Apurímac».
- Exige 25 departamentos con dato. Lima (15) y Callao (07) van separados, y Callao se rotula fuera del mapa
  porque es muy pequeño.
- Usa un solo color, de claro a oscuro y desde 0. Nunca arcoíris. La leyenda dice la unidad: «% de personas en
  pobreza monetaria».
- Pondera con `factor07 × mieperho`. La referencia de la Sesión 16 usa el mismo método, así que la diferencia
  debe ser de 0.0 puntos.

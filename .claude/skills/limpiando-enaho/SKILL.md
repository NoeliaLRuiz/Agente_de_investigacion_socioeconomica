---
name: limpiando-enaho
description: Limpia, une y valida los microdatos de la ENAHO 2024 del INEI (módulo 34 sumaria y módulo 02 miembros del hogar) y arma las bases de hogares y personas con pobreza monetaria, pobreza extrema, departamento, área urbana o rural, sexo, edad y factores de expansión. Úsala cuando pidan limpiar, unir, validar o procesar la ENAHO, o calcular la pobreza nacional, por departamento, por área, por sexo o por edad, y antes de graficar o mapear la ENAHO si todavía no existe la base limpia.
argument-hint: "[año]"
---

# Limpiar la ENAHO

1. Comprueba que existan `datos/966-Modulo34.zip` y `datos/966-Modulo02.zip` (966 = ENAHO 2024). Si faltan, pide
   al usuario que los baje del INEI y detente. No busques otros archivos ni inventes cifras:
   - https://proyectos.inei.gob.pe/iinei/srienaho/descarga/STATA/966-Modulo34.zip
   - https://proyectos.inei.gob.pe/iinei/srienaho/descarga/STATA/966-Modulo02.zip
2. Desde la raíz del proyecto corre exactamente este comando (hoy solo está preparado 2024):

   ```bash
   uv run .claude/skills/limpiando-enaho/scripts/limpiar.py --anio 2024
   ```

3. Lee `salidas/validacion.txt`. Si el script terminó con error o hay alguna línea `[FALLÓ]`, detente y
   muestra las verificaciones fallidas. No cambies filtros, llaves ni ponderadores para que las cifras
   coincidan con la referencia.
4. Responde con las cifras de `salidas/indicadores.csv` o calculadas sobre las bases, siempre ponderadas:
   - Nacional, área y departamento: `salidas/hogares_2024.parquet`, ponderador `peso_personas`
     (= `factor07 × mieperho`, el método del INEI).
   - Sexo y edad: `salidas/personas_2024.parquet`, ponderador `facpob07`.
   - Nunca uses un promedio simple ni cuentes filas de la muestra como si fueran personas.
5. Cita cada cifra así: «INEI, ENAHO 2024; cálculo propio con <ponderador>». Si mezclas hogares y personas,
   dilo (27.58 % por hogares frente a 27.53 % por personas).
6. Antes de usar una variable que no está en las bases, lee [reference.md](reference.md).
7. Las diferencias entre grupos son descriptivas: no afirmes que una característica causa la pobreza.

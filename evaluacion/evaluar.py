"""¿Mejoran el MCP y las Skills las respuestas de Claude Code? Las mismas 10 preguntas en dos modos.

    uv run evaluacion/evaluar.py                       # los dos modos, las 10 preguntas, con Sonnet
    uv run evaluacion/evaluar.py --modos B --ids e1_pobreza_nacional --modelo sonnet

Modo A: sin herramientas. Claude Code corre en una carpeta temporal vacía, fuera del repositorio, sin MCP
        (--strict-mcp-config sin servidores) y sin ninguna herramienta (--tools ""): ni archivos, ni terminal,
        ni web, ni Skills. Responde solo con lo que sabe y no puede leer las respuestas ya calculadas.
Modo B: con el MCP bcrp de .mcp.json y las Skills de .claude/skills, en la raíz del proyecto. Puede usar Skill,
        Read, Glob y Grep, y la terminal solo para `uv run .claude/skills/...` (más cd y ls). No tiene web. No puede
        leer evaluacion/ (las respuestas esperadas) ni evidencias_ia/ (los registros de otras preguntas).
        Corrida 1 (06-11-2026): sin ese bloqueo, Grep llegó a mostrar preguntas.csv; por eso se repitió todo.

Cada pregunta es una llamada independiente a `claude -p`, sin guardar la sesión. Las dos usan el mismo modelo
y la misma instrucción. Las respuestas esperadas están en preguntas.csv con su fuente: se fijaron antes de correr.
Escribe evaluacion/resultados.csv, evaluacion/resumen_modos.csv y el registro de cada llamada en
evidencias_ia/evaluacion/<modo>_<id>.jsonl.
"""
import argparse
import json
import re
import subprocess
import tempfile
import time
import unicodedata
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
EVAL = RAIZ / "evaluacion"
REGISTROS = RAIZ / "evidencias_ia" / "evaluacion"
ESQUEMA = {"type": "object", "required": ["valor", "respuesta", "fuente"],
           "properties": {"valor": {"type": ["number", "null"]}, "valor_2": {"type": ["number", "null"]},
                          "respuesta": {"type": "string"}, "fuente": {"type": "string"}}}
INSTRUCCION = ("Responde la pregunta. En «valor» pon la cifra que pide, en la unidad que indica, y en «valor_2» la "
               "segunda cifra si pide dos. En «respuesta» explica en una o dos oraciones, sin afirmar causas que los "
               "datos no muestran. En «fuente» di de dónde sale cada cifra. Si no puedes saberlo con certeza, pon "
               "null en la cifra: no estimes.\n\nPregunta: ")
MODOS = {
    "A": ["--tools", "", "--strict-mcp-config"],
    # En B la terminal solo puede correr los scripts de las Skills, y Read, Glob y Grep no pueden abrir
    # evaluacion/ (las respuestas esperadas) ni evidencias_ia/ (los registros de otras preguntas).
    "B": ["--tools", "Skill,Bash,PowerShell,Read,Glob,Grep", "--strict-mcp-config",
          "--mcp-config", str(RAIZ / ".mcp.json"),
          "--allowedTools", "mcp__bcrp", "Skill", "Read", "Glob", "Grep", "Bash(uv run .claude/skills/*)",
          "PowerShell(uv run .claude/skills/*)", "Bash(cd *)", "Bash(ls *)",
          "--disallowedTools", "Read(./evaluacion/**)", "Read(./evidencias_ia/**)"],
}
CAUSAL = re.compile(r"\b(caus\w*|provoc\w*|gracias a|se debe a|debido a (la|su) inversi|reduj\w+ la pobreza|"
                    r"explica la pobreza)\b", re.I)


def sin_tildes(s):
    return unicodedata.normalize("NFD", str(s).lower()).encode("ascii", "ignore").decode()


def preguntar(fila, modo, modelo, carpeta_a):
    cmd = ["claude", "-p", INSTRUCCION + fila.pregunta, "--output-format", "stream-json", "--verbose",
           "--json-schema", json.dumps(ESQUEMA), "--no-session-persistence", "--model", modelo, *MODOS[modo]]
    t = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
                          cwd=carpeta_a if modo == "A" else RAIZ)
    segundos = round(time.time() - t, 1)
    herramientas, final, lineas = [], {}, []
    for linea in proc.stdout.splitlines():
        try:
            ev = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "rate_limit_event":
            continue                                    # uso de la cuenta: no aporta a la evaluación
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            # el evento inicial trae datos de la cuenta y de la máquina: se guarda solo lo que sirve para auditar
            ev = {k: ev.get(k) for k in ("type", "subtype", "model", "tools", "mcp_servers", "permissionMode")}
        if ev.get("type") == "assistant":
            # StructuredOutput es como Claude entrega el JSON final: no cuenta como herramienta
            herramientas += [c["name"] for c in ev["message"].get("content", [])
                             if c.get("type") == "tool_use" and c["name"] != "StructuredOutput"]
        if ev.get("type") == "result":
            final = ev
        lineas.append(json.dumps(ev, ensure_ascii=False))
    REGISTROS.mkdir(parents=True, exist_ok=True)
    (REGISTROS / f"{modo}_{fila.id}.jsonl").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    r = final.get("structured_output") or {}
    return {"valor": r.get("valor"), "valor_2": r.get("valor_2"),
            "respuesta": r.get("respuesta") or final.get("result", "") or proc.stderr[-300:],
            "fuente": r.get("fuente", ""), "herramientas": ";".join(dict.fromkeys(herramientas)),
            "n_llamadas": len(herramientas), "segundos": segundos, "turnos": final.get("num_turns"),
            "costo_usd": final.get("total_cost_usd"),
            "error": "" if final and not final.get("is_error") else (final.get("subtype") or "sin respuesta")}


def calificar(fila, r):
    """Correcta si todas las cifras caen dentro de la tolerancia fijada antes y, en las combinadas, si además
    nombra lo esperado y no afirma causas. «No responde» si no da ninguna cifra."""
    if r["valor"] is None and r["valor_2"] is None:
        return pd.Series({"datos_ok": False, "interpretacion_ok": None, "resultado": "no responde"})
    ok = r["valor"] is not None and abs(r["valor"] - fila.esperado) <= fila.tolerancia
    if pd.notna(fila.esperado_2):
        ok &= r["valor_2"] is not None and abs(r["valor_2"] - fila.esperado_2) <= fila.tolerancia_2
    if pd.notna(fila.esperado_texto):
        ok &= sin_tildes(fila.esperado_texto) in sin_tildes(r["respuesta"])
    interpretacion = None
    if fila.tipo == "combinada":
        interpretacion = not CAUSAL.search(r["respuesta"])
    resultado = "correcta" if ok and interpretacion is not False else "incorrecta"
    return pd.Series({"datos_ok": bool(ok), "interpretacion_ok": interpretacion, "resultado": resultado})


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--modos", nargs="+", default=["A", "B"], choices=list(MODOS))
    p.add_argument("--modelo", default="sonnet")
    p.add_argument("--ids", nargs="*", help="solo estas preguntas (por defecto, las 10)")
    a = p.parse_args()
    preguntas = pd.read_csv(EVAL / "preguntas.csv")
    if a.ids:
        preguntas = preguntas[preguntas.id.isin(a.ids)]
    carpeta_a = tempfile.mkdtemp(prefix="eval_modo_A_")        # vacía y fuera del repositorio
    filas = []
    for q in preguntas.itertuples():
        for modo in a.modos:
            print(f"[{modo}] {q.id} ...", end=" ", flush=True)
            r = preguntar(q, modo, a.modelo, carpeta_a)
            nota = calificar(q, r)
            print(f"{nota.resultado} ({r['segundos']} s; {r['herramientas'] or 'sin herramientas'})")
            filas.append({"id": q.id, "tipo": q.tipo, "modo": modo, "modelo": a.modelo, "pregunta": q.pregunta,
                          "esperado": q.esperado, "esperado_2": q.esperado_2, "esperado_texto": q.esperado_texto,
                          **r, **nota.to_dict()})
    res = pd.DataFrame(filas)
    archivo = EVAL / "resultados.csv"
    if a.ids and archivo.exists():                      # corrida parcial: reemplaza solo esas filas
        viejo = pd.read_csv(archivo)
        viejo = viejo[~(viejo.id.isin(res.id) & viejo.modo.isin(res.modo))]
        res = pd.concat([viejo, res], ignore_index=True)
    res.to_csv(archivo, index=False, encoding="utf-8")
    resumen = res.groupby("modo").agg(
        preguntas=("id", "size"), correctas=("resultado", lambda s: (s == "correcta").sum()),
        incorrectas=("resultado", lambda s: (s == "incorrecta").sum()),
        no_responde=("resultado", lambda s: (s == "no responde").sum()),
        segundos_promedio=("segundos", "mean"), llamadas_herramientas=("n_llamadas", "sum"),
        costo_usd=("costo_usd", "sum")).round(2)
    resumen.to_csv(EVAL / "resumen_modos.csv", encoding="utf-8")
    print("\n" + res.pivot_table(index="id", columns="modo", values="resultado", aggfunc="first").to_string())
    print("\n" + resumen.to_string())


if __name__ == "__main__":
    main()

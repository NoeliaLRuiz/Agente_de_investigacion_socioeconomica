"""El contrato del servidor: si estas pruebas pasan, Claude Code y evaluar.py pueden usarlo.

    uv run pytest -q

Llaman al servidor en memoria, igual que lo haría Claude Code, y piden datos reales al BCRP.
"""
import asyncio

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from server import mcp


async def _con_cliente(f):
    async with Client(mcp) as c:
        return await f(c)


def llamar(herramienta, **args):
    return asyncio.run(_con_cliente(lambda c: c.call_tool(herramienta, args))).data


def test_buscar_encuentra_el_ipc():
    r = llamar("buscar_series", texto="ipc 12 meses", limite=5)
    assert "PN01273PM" in [x["codigo"] for x in r]
    assert {"codigo", "nombre", "frecuencia"} <= r[0].keys()


def test_cuatro_herramientas_como_minimo():
    nombres = {t.name for t in asyncio.run(_con_cliente(lambda c: c.list_tools()))}
    assert {"buscar_series", "serie", "resumen"} <= nombres
    assert len(nombres) >= 4, "falta su herramienta propia"


def test_serie_mensual():
    r = llamar("serie", codigo="PN01271PM", desde="2025-01", hasta="2025-12")
    assert len(r["datos"]) == 12
    assert r["datos"][0]["periodo"] == "2025-01"
    assert r["datos"][2]["valor"] == pytest.approx(0.81, abs=0.01)   # IPC de Lima, marzo de 2025
    assert r["fuente"].startswith("https://estadisticas.bcrp.gob.pe")


def test_serie_diaria():
    r = llamar("serie", codigo="PD04638PD", desde="2026-10-01", hasta="2026-10-15")
    assert r["datos"][0]["periodo"] == "2026-10-01"
    assert r["datos"][-1] == {"periodo": "2026-10-15", "valor": pytest.approx(3.428, abs=0.001)}


def test_resumen_sin_cuentas_a_mano():
    r = llamar("resumen", codigo="PN01273PM", desde="2025-12", hasta="2026-09")
    assert r["primero"]["valor"] == pytest.approx(1.51, abs=0.01)
    assert r["ultimo"]["valor"] == pytest.approx(4.55, abs=0.01)
    assert r["maximo"]["periodo"] == "2026-09"
    assert {"cambio", "variacion_pct", "promedio", "minimo"} <= r.keys()


def test_codigo_inexistente_da_un_error_claro():
    with pytest.raises(ToolError, match="XX999"):
        llamar("serie", codigo="XX999", desde="2025-01", hasta="2025-02")


def test_un_recurso():
    async def contar(c):
        return len(await c.list_resources()) + len(await c.list_resource_templates())
    assert asyncio.run(_con_cliente(contar)) >= 1


def test_un_prompt():
    assert len(asyncio.run(_con_cliente(lambda c: c.list_prompts()))) >= 1


# --- Pruebas propias (Tarea 4): la herramienta comparar_periodos ---

def test_comparar_periodos_hace_bien_las_cuentas():
    """Los promedios y su diferencia coinciden con los que se calculan a mano desde serie."""
    r = llamar("comparar_periodos", codigo="PN01273PM", desde_1="2017-01", hasta_1="2019-12",
               desde_2="2022-01", hasta_2="2024-12")
    antes = [d["valor"] for d in llamar("serie", codigo="PN01273PM", desde="2017-01", hasta="2019-12")["datos"]]
    despues = [d["valor"] for d in llamar("serie", codigo="PN01273PM", desde="2022-01", hasta="2024-12")["datos"]]
    assert r["intervalo_1"]["n"] == r["intervalo_2"]["n"] == 36
    assert r["intervalo_1"]["promedio"] == pytest.approx(sum(antes) / 36, abs=1e-4)
    assert r["intervalo_2"]["promedio"] == pytest.approx(sum(despues) / 36, abs=1e-4)
    assert r["diferencia_promedios"] == pytest.approx(sum(despues) / 36 - sum(antes) / 36, abs=1e-4)
    assert r["intervalo_2"]["ultimo"] == {"periodo": "2024-12", "valor": pytest.approx(1.97, abs=0.01)}
    assert r["advertencias"] == []
    assert all(f.startswith("https://estadisticas.bcrp.gob.pe") for f in r["fuentes"])


def test_comparar_periodos_superpuestos_da_error_claro():
    """Si los intervalos comparten meses, la comparación no tiene sentido: debe avisar, no calcular."""
    with pytest.raises(ToolError, match="superponen"):
        llamar("comparar_periodos", codigo="PN01273PM", desde_1="2020-01", hasta_1="2022-12",
               desde_2="2022-01", hasta_2="2024-12")

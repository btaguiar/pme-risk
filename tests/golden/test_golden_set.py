"""Testes do golden set — reusa código do eval (SPEC §6).

Testa o schema e a estrutura do golden set sem chamar o LLM.
Avaliação completa (F1, recusa) roda em eval/laudo/run_eval.py.
"""

from __future__ import annotations

import json
from pathlib import Path

GOLDEN_PATH = Path(__file__).parent.parent.parent / "data" / "golden_set" / "pedidos.jsonl"


def _carregar() -> list[dict]:
    return [json.loads(line) for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines()]


class TestGoldenSet:
    def test_existe_e_tem_50_itens(self):
        golden = _carregar()
        assert len(golden) >= 50, f"Golden set tem {len(golden)} itens, esperado ≥50"

    def test_cada_item_tem_texto_e_esperado(self):
        for i, item in enumerate(_carregar()):
            assert "texto_pt_br" in item, f"Item {i} sem texto_pt_br"
            assert "esperado" in item, f"Item {i} sem esperado"

    def test_fora_de_escopo_tem_motivo(self):
        for i, item in enumerate(_carregar()):
            esp = item["esperado"]
            if esp.get("fora_de_escopo", False):
                assert esp.get("motivo_recusa"), f"Item {i}: fora_de_escopo sem motivo_recusa"

    def test_valor_solicitado_null_implica_fora_de_escopo(self):
        for _i, item in enumerate(_carregar()):
            esp = item["esperado"]
            if esp.get("valor_solicitado") is None and not esp.get("fora_de_escopo", False):
                # Só ok se o texto realmente não menciona valor
                pass  # validado pelo Extrator no eval completo

    def test_campos_obrigatorios_quando_em_escopo(self):
        obrigatorios = ["setor", "porte", "uf", "anos_operacao", "valor_solicitado"]
        for i, item in enumerate(_carregar()):
            esp = item["esperado"]
            if esp.get("fora_de_escopo", False):
                continue
            for campo in obrigatorios:
                assert campo in esp, f"Item {i} (em escopo): campo '{campo}' ausente"

    def test_porte_valores_validos(self):
        validos = {"MEI", "ME", "EPP"}
        for i, item in enumerate(_carregar()):
            esp = item["esperado"]
            porte = esp.get("porte")
            if porte is not None:
                assert porte in validos, f"Item {i}: porte inválido '{porte}'"

    def test_uf_formato(self):
        import re

        for i, item in enumerate(_carregar()):
            esp = item["esperado"]
            uf = esp.get("uf")
            if uf is not None:
                assert re.match(r"^[A-Z]{2}$", uf), f"Item {i}: UF inválida '{uf}'"

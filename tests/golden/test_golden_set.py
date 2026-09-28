"""Testes do golden set — estrutura e anotação, sem chamar o LLM.

A métrica (F1, recusa) é testada em tests/unit/test_eval_laudo.py e roda
contra o Extrator em eval/laudo/run_eval.py.
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

    def test_item_em_escopo_anota_todos_os_campos(self):
        """null explícito = "não mencionado" — é o que permite medir alucinação."""
        from eval.laudo.run_eval import CAMPOS

        for i, item in enumerate(_carregar()):
            esp = item["esperado"]
            if esp.get("fora_de_escopo", False):
                continue
            faltando = [c for c in CAMPOS if c not in esp]
            assert not faltando, f"Item {i}: campos sem anotação {faltando}"

    def test_campos_essenciais_quando_em_escopo(self):
        """Sem setor, valor ou finalidade o pedido deve ser recusado (prompt do Extrator)."""
        for i, item in enumerate(_carregar()):
            esp = item["esperado"]
            if esp.get("fora_de_escopo", False):
                continue
            for campo in ("setor", "valor_solicitado", "finalidade"):
                assert esp.get(campo) is not None, f"Item {i}: '{campo}' essencial é None"

    def test_setor_e_secao_cnae(self):
        from agents.setores import SETORES_CNAE

        for i, item in enumerate(_carregar()):
            setor = item["esperado"].get("setor")
            if setor is None:
                continue
            aceitos = setor if isinstance(setor, list) else [setor]
            assert aceitos, f"Item {i}: lista de setores vazia"
            for s in aceitos:
                assert s in SETORES_CNAE, f"Item {i}: setor fora da CNAE '{s}'"

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

"""Baseline do laudo — uma chamada única ao Gemini, sem agentes (PLANO §5).

"Laudo: uma chamada única ao Gemini (recebe PD + dados, redige o laudo), sem
agentes. A arquitetura multi-agente só se justifica se superar o baseline."

Recebe o texto bruto do pedido + o resultado do modelo — sem Extrator (dados
estruturados) nem Pesquisador (fonte_por_campo). Mesmo prompt de regras, modelo,
temperatura e schema de saída do Redator (`chamar_redator`): muda só a entrada.

A PD vem do mesmo modelo nos dois braços — calcular PD exige features
estruturadas em qualquer arquitetura; o que o baseline testa é a redação.
"""

from __future__ import annotations

import json

from agents.redator.redator import ResultadoRedacao, _carregar_prompt, chamar_redator
from agents.schemas import ResultadoModelo


def montar_prompt_baseline(texto_pedido: str, resultado_modelo: ResultadoModelo) -> str:
    return f"""{_carregar_prompt()}

---

Redija o laudo com base no pedido original e no resultado do modelo.
Todos os dados do pedido foram DECLARADOS pelo solicitante — nenhum foi verificado.

Pedido original:
{texto_pedido}

Resultado do modelo:
{json.dumps(resultado_modelo.model_dump(), indent=2, ensure_ascii=False)}

IMPORTANTE: A PD é {resultado_modelo.pd:.4f}. Use exatamente este valor.
"""


def redigir_baseline(
    texto_pedido: str, resultado_modelo: ResultadoModelo, project_id: str | None = None
) -> ResultadoRedacao:
    return chamar_redator(montar_prompt_baseline(texto_pedido, resultado_modelo), project_id)

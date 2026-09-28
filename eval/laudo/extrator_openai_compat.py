"""Extrator via API compatível com OpenAI — SÓ para o eval comparativo de modelos.

Mesmo prompt (`montar_prompt`) e mesmo schema (`DadosExtraidos`, JSON Schema
strict) do Extrator de produção; muda só o modelo. A API em produção segue no
Gemini/Vertex AI: levar outro provedor para lá exige análise de LGPD
(transferência internacional, retenção, uso para treino) — o golden set é
sintético, então o eval não expõe dado real.

Só entram modelos que IMPÕEM o schema: com JSON livre, um setor fora da lista
CNAE vira erro de validação e o eval mediria formato, não extração
(verificado em 2026-09-28: glm-5.3 aceita o schema e o ignora;
deepseek-v4.1-flash o rejeita).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

import httpx

from agents.extractor.extractor import montar_prompt
from agents.schemas import DadosExtraidos

BASE_URL_PADRAO = "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"

# Mesma política de retry do Gemini (agents/gemini.py)
_STATUS_RETRY = {429, 500, 502, 503, 504}
_TENTATIVAS = 5


def schema_strict(schema: dict) -> dict:
    """Todo campo de todo objeto vira `required` (semântica strict da API OpenAI).

    Campos com default (fora_de_escopo, motivo_recusa) ficam fora de `required`
    no schema Pydantic; em 2026-09-28 o deepseek-v4-pro recusava devolvendo só
    {"pedido": null} e a validação falhava. Opcionais continuam aceitando null.
    """
    if isinstance(schema, dict):
        novo = {k: schema_strict(v) for k, v in schema.items()}
        if isinstance(novo.get("properties"), dict):
            novo["required"] = list(novo["properties"])
        return novo
    if isinstance(schema, list):
        return [schema_strict(v) for v in schema]
    return schema


@dataclass
class ExtratorOpenAICompat:
    """Callable com a assinatura de `extrair` — plugável em executar_golden_set."""

    modelo: str
    base_url: str = field(
        default_factory=lambda: os.environ.get("DASHSCOPE_BASE_URL", BASE_URL_PADRAO)
    )
    api_key_env: str = "DASHSCOPE_API_KEY"
    timeout_s: float = 180.0
    cliente: httpx.Client | None = None
    uso: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.cliente is None:
            self.cliente = httpx.Client(timeout=self.timeout_s)

    def _headers(self) -> dict[str, str]:
        chave = os.environ.get(self.api_key_env)
        if not chave:
            raise RuntimeError(f"{self.api_key_env} não definida (.env)")
        return {"Authorization": f"Bearer {chave}"}

    def __call__(self, texto: str, project_id: str | None = None) -> DadosExtraidos:
        corpo = {
            "model": self.modelo,
            "messages": [{"role": "user", "content": montar_prompt(texto)}],
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "DadosExtraidos",
                    "strict": True,
                    "schema": schema_strict(DadosExtraidos.model_json_schema()),
                },
            },
        }
        assert self.cliente is not None
        for tentativa in range(_TENTATIVAS):
            resposta = self.cliente.post(
                f"{self.base_url}/chat/completions", headers=self._headers(), json=corpo
            )
            if resposta.status_code not in _STATUS_RETRY or tentativa == _TENTATIVAS - 1:
                break
            time.sleep(min(2.0 * 2**tentativa, 30.0))
        resposta.raise_for_status()
        dados = resposta.json()
        uso = dados.get("usage") or {}
        self.uso.append(
            {
                "entrada": uso.get("prompt_tokens"),
                "saida": uso.get("completion_tokens"),
            }
        )
        conteudo = dados["choices"][0]["message"]["content"]
        return DadosExtraidos.model_validate_json(conteudo)

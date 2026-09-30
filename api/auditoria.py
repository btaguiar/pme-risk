"""Trilha de auditoria — registro append-only de cada laudo.

Referência: SPEC §4.4
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from google.cloud import bigquery


class TrilhaAuditoria:
    """Grava trilha de auditoria no BigQuery (append-only)."""

    def __init__(self, project_id: str, dataset: str) -> None:
        self.client = bigquery.Client(project=project_id)
        self.table_id = f"{project_id}.{dataset}.trilha_auditoria"

    @staticmethod
    def hash_prompt(prompt_text: str) -> str:
        """Hash SHA-256 do prompt — evita duplicar texto grande."""
        return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:16]

    def registrar(
        self,
        laudo_id: str,
        pedido_bruto: str,
        model_version: str,
        prompts_usados: dict[str, str],
        decisao_humana: str | None,
        etapas: list[dict],
    ) -> None:
        """Registra uma entrada na trilha de auditoria.

        Args:
            laudo_id: identificador do laudo
            pedido_bruto: texto original do pedido
            model_version: versão do modelo usada
            prompts_usados: {nome_prompt: hash_do_prompt}
            decisao_humana: decisão do analista (se houver)
            etapas: lista de {etapa, timestamp, detalhe}
        """
        row = {
            "laudo_id": laudo_id,
            "pedido_bruto": pedido_bruto,
            "model_version": model_version,
            "prompts_usados": json.dumps(prompts_usados),
            "decisao_humana": decisao_humana,
            "etapas_json": json.dumps(etapas),
            "criado_em": datetime.now(UTC).isoformat(),
        }
        errors = self.client.insert_rows_json(self.table_id, [row])
        if errors:
            raise RuntimeError(f"Erro ao registrar auditoria: {errors}")

    def contar_pedidos_desde(self, inicio: datetime) -> int:
        """Pedidos (laudos e recusas) registrados desde `inicio`.

        Decisões humanas também entram na trilha, mas não são pedidos: ficam
        de fora (`decisao_humana IS NULL`). Base do teto global da demo aberta
        (api/limites.py).
        """
        query = f"""
            SELECT COUNT(DISTINCT laudo_id) AS n
            FROM `{self.table_id}`
            WHERE criado_em >= @inicio AND decisao_humana IS NULL
        """
        config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("inicio", "TIMESTAMP", inicio)]
        )
        linhas = list(self.client.query(query, job_config=config).result())
        return int(linhas[0]["n"]) if linhas else 0

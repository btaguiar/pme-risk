"""Portão humano — decisão de aprovação/correção/rejeição de laudos.

Referência: SPEC §4.3
"""

from __future__ import annotations

from datetime import UTC, datetime

from google.cloud import bigquery

DECISOES_VALIDAS = ("aprovado", "corrigido", "rejeitado")


class LaudoJaDecididoError(Exception):
    """Decisão sobre laudo que não está mais 'pendente' — decisões são finais."""

    def __init__(self, laudo_id: str, status: str) -> None:
        super().__init__(f"Laudo {laudo_id} já decidido (status={status})")
        self.laudo_id = laudo_id
        self.status = status


class PortaoHumano:
    """Gerencia decisões humanas sobre laudos no BigQuery."""

    def __init__(self, project_id: str, dataset: str) -> None:
        self.client = bigquery.Client(project=project_id)
        self.table_id = f"{project_id}.{dataset}.laudos"

    def obter(self, laudo_id: str) -> dict | None:
        """Retorna o laudo pelo ID."""
        query = f"""
            SELECT * FROM `{self.table_id}`
            WHERE laudo_id = @laudo_id
            LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("laudo_id", "STRING", laudo_id),
            ]
        )
        results = list(self.client.query(query, job_config=job_config).result())
        return dict(results[0]) if results else None

    def decidir(
        self,
        laudo_id: str,
        decisao: str,
        decidido_por: str,
        observacao: str | None = None,
    ) -> dict | None:
        """Registra decisão humana sobre o laudo — só a partir de 'pendente'.

        A transição é atômica: o UPDATE só casa com laudo ainda pendente, então
        duas decisões concorrentes não se sobrescrevem.

        Args:
            laudo_id: identificador do laudo
            decisao: 'aprovado', 'corrigido' ou 'rejeitado'
            decidido_por: identificador do analista
            observacao: observação opcional

        Returns:
            Laudo atualizado, ou None se o laudo não existe.

        Raises:
            LaudoJaDecididoError: o laudo já saiu de 'pendente'.
        """
        if decisao not in DECISOES_VALIDAS:
            raise ValueError(f"Decisão inválida: {decisao}. Use aprovado/corrigido/rejeitado.")

        query = f"""
            UPDATE `{self.table_id}`
            SET status = @decisao,
                decidido_por = @decidido_por,
                decidido_em = @decidido_em,
                decisao = @decisao,
                observacao_humana = @observacao
            WHERE laudo_id = @laudo_id AND status = 'pendente'
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("decisao", "STRING", decisao),
                bigquery.ScalarQueryParameter("decidido_por", "STRING", decidido_por),
                bigquery.ScalarQueryParameter(
                    "decidido_em", "TIMESTAMP", datetime.now(UTC).isoformat()
                ),
                bigquery.ScalarQueryParameter("observacao", "STRING", observacao),
                bigquery.ScalarQueryParameter("laudo_id", "STRING", laudo_id),
            ]
        )
        job = self.client.query(query, job_config=job_config)
        job.result()

        row = self.obter(laudo_id)
        if row is None:
            return None
        if not job.num_dml_affected_rows:
            raise LaudoJaDecididoError(laudo_id, row["status"])
        return row

    def criar(
        self,
        laudo_id: str,
        pedido_bruto: str,
        enriquecidos_json: str,
        resultado_modelo_json: str,
        texto: str,
        evidencias_json: str,
    ) -> dict:
        """Cria um novo laudo com status='pendente'."""
        query = f"""
            INSERT INTO `{self.table_id}`
            (laudo_id, pedido_bruto, enriquecidos_json, resultado_modelo_json,
             texto, evidencias_json, status, criado_em)
            VALUES
            (@laudo_id, @pedido_bruto, @enriquecidos_json, @resultado_modelo_json,
             @texto, @evidencias_json, 'pendente', @criado_em)
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("laudo_id", "STRING", laudo_id),
                bigquery.ScalarQueryParameter("pedido_bruto", "STRING", pedido_bruto),
                bigquery.ScalarQueryParameter("enriquecidos_json", "STRING", enriquecidos_json),
                bigquery.ScalarQueryParameter(
                    "resultado_modelo_json", "STRING", resultado_modelo_json
                ),
                bigquery.ScalarQueryParameter("texto", "STRING", texto),
                bigquery.ScalarQueryParameter("evidencias_json", "STRING", evidencias_json),
                bigquery.ScalarQueryParameter(
                    "criado_em", "TIMESTAMP", datetime.now(UTC).isoformat()
                ),
            ]
        )
        self.client.query(query, job_config=job_config).result()
        return self.obter(laudo_id) or {}

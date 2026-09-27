"""Model Registry — versionamento de modelos no BigQuery.

Referência: SPEC §3.4
Tabela: model_registry (criada por infra/scripts/setup_bq.sh)
"""

from __future__ import annotations

from datetime import datetime

from google.cloud import bigquery

# Schema da tabela model_registry
REGISTRY_SCHEMA = [
    bigquery.SchemaField("model_version", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("algoritmo", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("feature_set_version", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("treinado_em", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("ks", "FLOAT64"),
    bigquery.SchemaField("auc", "FLOAT64"),
    bigquery.SchemaField("brier", "FLOAT64"),
    bigquery.SchemaField("ece", "FLOAT64"),
    bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("nota", "STRING"),
]

# Status possíveis
STATUS_BASELINE = "baseline"
STATUS_PRODUCTION = "production"
STATUS_CANDIDATE = "candidate"
STATUS_CANDIDATE_REJECTED = "candidate_rejected"


class ModelRegistry:
    """CRUD para a tabela model_registry no BigQuery."""

    def __init__(self, project_id: str, dataset: str) -> None:
        self.client = bigquery.Client(project=project_id)
        self.table_id = f"{project_id}.{dataset}.model_registry"

    def registrar(
        self,
        model_version: str,
        algoritmo: str,
        feature_set_version: str,
        ks: float | None = None,
        auc: float | None = None,
        brier: float | None = None,
        ece: float | None = None,
        status: str = STATUS_CANDIDATE,
        nota: str | None = None,
    ) -> None:
        """Registra um modelo no registry."""
        row = {
            "model_version": model_version,
            "algoritmo": algoritmo,
            "feature_set_version": feature_set_version,
            "treinado_em": datetime.utcnow().isoformat(),
            "ks": ks,
            "auc": auc,
            "brier": brier,
            "ece": ece,
            "status": status,
            "nota": nota,
        }
        errors = self.client.insert_rows_json(self.table_id, [row])
        if errors:
            raise RuntimeError(f"Erro ao inserir no registry: {errors}")

    def obter_producao(self) -> dict | None:
        """Retorna o modelo com status='production'."""
        query = f"""
            SELECT * FROM `{self.table_id}`
            WHERE status = @status
            ORDER BY treinado_em DESC
            LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("status", "STRING", STATUS_PRODUCTION),
            ]
        )
        results = list(self.client.query(query, job_config=job_config).result())
        return dict(results[0]) if results else None

    def listar_todos(self) -> list[dict]:
        """Lista todos os modelos registrados."""
        query = f"SELECT * FROM `{self.table_id}` ORDER BY treinado_em DESC"
        return [dict(row) for row in self.client.query(query).result()]

    def promover(self, model_version: str) -> None:
        """Promove um modelo para production (rebaixa o anterior)."""
        # Rebaixa o modelo atual de produção
        query_rebaixar = f"""
            UPDATE `{self.table_id}`
            SET status = @novo_status
            WHERE status = @status_atual
        """
        config_rebaixar = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("novo_status", "STRING", STATUS_CANDIDATE_REJECTED),
                bigquery.ScalarQueryParameter("status_atual", "STRING", STATUS_PRODUCTION),
            ]
        )
        self.client.query(query_rebaixar, job_config=config_rebaixar).result()

        # Promove o novo
        query_promover = f"""
            UPDATE `{self.table_id}`
            SET status = @novo_status
            WHERE model_version = @model_version
        """
        config_promover = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("novo_status", "STRING", STATUS_PRODUCTION),
                bigquery.ScalarQueryParameter("model_version", "STRING", model_version),
            ]
        )
        self.client.query(query_promover, job_config=config_promover).result()

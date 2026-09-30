"""Carrega as tabelas de mapeamento do v3 no BigQuery.

Lê `model/mapeamentos.py` (fonte única de verdade) e cria/substitui:
- `${BQ_DATASET}.naics_para_secao` (prefixo, secao) — casado pelo prefixo
  mais longo em 07_load_features_v3.sql
- `${BQ_DATASET}.business_age_para_faixa` (business_age, faixa)

Uso:
    GCP_PROJECT_ID=<projeto> uv run python -m model.dados.carregar_mapeamentos_bq
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from google.cloud import bigquery

from model.mapeamentos import BUSINESS_AGE_PARA_FAIXA, NAICS_PARA_SECAO


def _carregar_tabela(
    client: bigquery.Client,
    table_id: str,
    colunas: Sequence[tuple[str, str]],
    linhas: Sequence[Sequence[str]],
) -> None:
    schema = [bigquery.SchemaField(nome, tipo) for nome, tipo in colunas]
    config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema=schema,
    )
    nomes = [nome for nome, _ in colunas]
    dados = [dict(zip(nomes, linha, strict=True)) for linha in linhas]
    job = client.load_table_from_json(dados, table_id, job_config=config)
    job.result()
    n = client.get_table(table_id).num_rows
    print(f"{table_id.split('.')[-1]}: {n} linhas")


def carregar(project_id: str, dataset: str) -> None:
    """Cria/substitui as tabelas de mapeamento a partir de mapeamentos.py."""
    client = bigquery.Client(project=project_id)
    _carregar_tabela(
        client,
        f"{project_id}.{dataset}.naics_para_secao",
        [("prefixo", "STRING"), ("secao", "STRING")],
        sorted(NAICS_PARA_SECAO.items()),
    )
    _carregar_tabela(
        client,
        f"{project_id}.{dataset}.business_age_para_faixa",
        [("business_age", "STRING"), ("faixa", "STRING")],
        sorted(BUSINESS_AGE_PARA_FAIXA.items()),
    )


def main() -> None:
    carregar(
        os.environ["GCP_PROJECT_ID"],
        os.environ.get("BQ_DATASET", "pme_risk"),
    )


if __name__ == "__main__":
    main()

"""Ingestão SBA 7(a) FOIA → BigQuery (`sba_7a_raw`).

Fonte: SBA Open Data, "7(a) & 504 FOIA" — empréstimos reais a pequenas empresas
dos EUA, com desfecho (`LoanStatus`). Base do modelo v3; a escolha e os limites
estão em docs/dados/levantamento-bases-pme-2026-09-29.md.

**Lista branca de colunas:** só entra o que o treino, o eval ou a análise de
vazamento usam. Nome, endereço e CEP do tomador e os dados do banco nunca são
lidos — uma versão futura do arquivo com colunas novas também não vaza PII.

`TermInMonths` fica na tabela bruta para o achado de vazamento ser
reproduzível; o teste de features do v3 impede que ele entre no treino.

Carga por CSV com schema explícito (sem pyarrow).

Uso:
    GCP_PROJECT_ID=<projeto> uv run python -m model.dados.ingest_sba
"""

from __future__ import annotations

import argparse
import io
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import IO

import pandas as pd

VERSAO = "asof_260630"
URL = (
    "https://data.sba.gov/sites/default/files/uploaded_resources/"
    f"FOIA_7a_FY2010_FY2019_{VERSAO}.csv"
)
TABELA = "sba_7a_raw"
DESTINO_LOCAL = Path(__file__).parents[2] / "data" / "raw" / "sba"  # gitignored


@dataclass(frozen=True)
class Coluna:
    nome_sba: str
    nome_bq: str
    tipo: str  # tipo BigQuery


COLUNAS: tuple[Coluna, ...] = (
    Coluna("ApprovalFY", "approval_fy", "INT64"),
    Coluna("ApprovalDate", "approval_date", "DATE"),
    Coluna("LoanStatus", "loan_status", "STRING"),
    Coluna("RevolverStatus", "revolver_status", "STRING"),
    Coluna("GrossApproval", "gross_approval", "FLOAT64"),
    Coluna("NaicsCode", "naics_code", "STRING"),
    Coluna("BusinessAge", "business_age", "STRING"),
    Coluna("BusinessType", "business_type", "STRING"),
    Coluna("JobsSupported", "jobs_supported", "INT64"),
    Coluna("TermInMonths", "term_in_months", "INT64"),
    Coluna("PaidInFullDate", "paid_in_full_date", "DATE"),
    Coluna("ChargeOffDate", "charge_off_date", "DATE"),
)

_DATAS = [c.nome_bq for c in COLUNAS if c.tipo == "DATE"]


def ler_csv(fonte: str | Path | IO[str]) -> pd.DataFrame:
    """Lê só as colunas da lista branca, tudo como texto (tipagem em `limpar`)."""
    return pd.read_csv(
        fonte,
        usecols=[c.nome_sba for c in COLUNAS],
        dtype=str,
        keep_default_na=False,
        encoding="latin-1",
    )


def limpar(df: pd.DataFrame) -> pd.DataFrame:
    """Renomeia, normaliza o status e tipa. Função pura (testável sem rede)."""
    out = df[[c.nome_sba for c in COLUNAS]].rename(columns={c.nome_sba: c.nome_bq for c in COLUNAS})
    out = out.apply(lambda s: s.str.strip())
    # O arquivo escreve "P I F"; os demais status vêm sem espaço
    out["loan_status"] = out["loan_status"].str.replace(" ", "", regex=False)
    for c in COLUNAS:
        col = out[c.nome_bq].replace("", None)
        if c.tipo == "INT64":
            out[c.nome_bq] = pd.to_numeric(col, errors="coerce").astype("Int64")
        elif c.tipo == "FLOAT64":
            out[c.nome_bq] = pd.to_numeric(col, errors="coerce")
        elif c.tipo == "DATE":
            out[c.nome_bq] = pd.to_datetime(col, errors="coerce").dt.strftime("%Y-%m-%d")
        else:
            out[c.nome_bq] = col
    return out


def baixar(destino: Path = DESTINO_LOCAL) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / Path(URL).name
    if not arquivo.exists():
        req = urllib.request.Request(URL, headers={"User-Agent": "pme-risk/0.1"})
        with urllib.request.urlopen(req, timeout=600) as resp, open(arquivo, "wb") as f:
            while bloco := resp.read(1 << 20):
                f.write(bloco)
    return arquivo


def carregar_bq(df: pd.DataFrame, project_id: str, dataset: str) -> str:
    """Substitui a tabela, particionada por safra (approval_fy)."""
    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)
    table_id = f"{project_id}.{dataset}.{TABELA}"
    config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        schema=[bigquery.SchemaField(c.nome_bq, c.tipo) for c in COLUNAS],
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        range_partitioning=bigquery.RangePartitioning(
            field="approval_fy", range_=bigquery.PartitionRange(start=2000, end=2030, interval=1)
        ),
    )
    csv = df.to_csv(index=False)
    job = client.load_table_from_file(io.BytesIO(csv.encode("utf-8")), table_id, job_config=config)
    job.result()
    return table_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", default=os.environ.get("BQ_DATASET", "pme_risk"))
    args = parser.parse_args()

    arquivo = baixar()
    df = limpar(ler_csv(arquivo))
    table_id = carregar_bq(df, os.environ["GCP_PROJECT_ID"], args.dataset)
    print(f"{len(df)} linhas -> {table_id.split('.', 1)[1]}")
    print(df["loan_status"].value_counts().to_string())


if __name__ == "__main__":
    main()

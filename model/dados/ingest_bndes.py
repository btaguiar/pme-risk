"""Ingestão BNDES → referência agregada (`bndes_agregado` → `bndes_referencia`).

Operações indiretas automáticas (1,2 GB): lê em streaming (chunks) e grava
SÓ O AGREGADO — MICRO/PEQUENA, contratações 2018–2022, sem cooperativas de
crédito, decis de valor e de prazo (carência + amortização) por porte e seção
CNAE. O nome do cliente é
dado pessoal em PF/MEI (decisão D8): a coluna `cliente` nem é lida.

O BNDES não tem rótulo de inadimplência (levantamento §3) — serve de
referência de distribuição (drift) e de prazo padrão, nunca de treino.

Limite registrado: o arquivo cobre contratações 2002–2022; o recurso
"não automáticas" do mesmo conjunto também termina em 2022 (verificado com
`--checar-janela` na ingestão de 2026-09-29). Não há contratação posterior
no conjunto.

Uso:
    GCP_PROJECT_ID=<projeto> uv run python -m model.dados.ingest_bndes
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

import pandas as pd

from agents.setores import SETORES_CNAE

URL = (
    "https://dadosabertos.bndes.gov.br/dataset/10e21ad1-568e-45e5-a8af-43f2c05ef1a2/"
    "resource/612faa0b-b6be-4b2c-9317-da5dc2c0b901/download/"
    "operacoes-financiamento-operacoes-indiretas-automaticas.csv"
)
URL_NAO_AUTOMATICAS = (
    "https://dadosabertos.bndes.gov.br/dataset/10e21ad1-568e-45e5-a8af-43f2c05ef1a2/"
    "resource/6f56b78c-510f-44b6-8274-78a5b7e931f4/download/"
    "operacoes-financiamento-operacoes-nao-automaticas.csv"
)

TABELA_STAGING = "bndes_agregado"
DESTINO_LOCAL = Path(__file__).parents[2] / "data" / "raw" / "bndes"  # gitignored

ANO_INICIO, ANO_FIM = 2018, 2022
PORTES = ("MICRO", "PEQUENA")
# Cooperativas de crédito (CNAE 6424-7) recebem repasse como MICRO/PEQUENA, mas
# são intermediárias, não a PME que pede crédito — ~19 mil operações 2018–2022
# que levavam a seção K a 16,6% da referência de setor.
SUBCLASSES_EXCLUIDAS = ("K6424",)
QUANTIS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)

# Só o que o agregado usa; `cliente` (nome aberto) e `cpf_cnpj` ficam de fora
COLUNAS = (
    "data_da_contratacao",
    "valor_da_operacao_em_reais",
    "prazo_carencia_meses",
    "prazo_amortizacao_meses",
    "porte_do_cliente",
    "subsetor_cnae_codigo",
)

_LETRA_PARA_SECAO = {letra: slug for slug, (letra, _titulo) in SETORES_CNAE.items()}


def baixar(destino: Path = DESTINO_LOCAL) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / Path(URL).name
    if not arquivo.exists():
        req = urllib.request.Request(URL, headers={"User-Agent": "pme-risk/0.1"})
        with urllib.request.urlopen(req, timeout=3600) as resp, open(arquivo, "wb") as f:
            while bloco := resp.read(1 << 20):
                f.write(bloco)
    return arquivo


def recortar(fonte: Path) -> pd.DataFrame:
    """Streaming do CSV → recorte MICRO/PEQUENA 2018–2022 com valor e prazo."""
    partes: list[pd.DataFrame] = []
    for chunk in pd.read_csv(
        fonte, sep=";", usecols=list(COLUNAS), dtype=str, encoding="latin-1", chunksize=500_000
    ):
        chunk = chunk[chunk["porte_do_cliente"].isin(PORTES)]
        ano = pd.to_numeric(chunk["data_da_contratacao"].str[:4], errors="coerce")
        chunk = chunk[ano.between(ANO_INICIO, ANO_FIM)]
        chunk = chunk[
            ~chunk["subsetor_cnae_codigo"].fillna("").str.startswith(SUBCLASSES_EXCLUIDAS)
        ]
        if chunk.empty:
            continue
        valor = pd.to_numeric(
            chunk["valor_da_operacao_em_reais"]
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False),
            errors="coerce",
        )
        prazo = pd.to_numeric(chunk["prazo_carencia_meses"], errors="coerce") + pd.to_numeric(
            chunk["prazo_amortizacao_meses"], errors="coerce"
        )
        partes.append(
            pd.DataFrame(
                {
                    "porte": chunk["porte_do_cliente"],
                    "secao": chunk["subsetor_cnae_codigo"].str[0].map(_LETRA_PARA_SECAO),
                    "valor": valor,
                    "prazo": prazo,
                }
            )
        )
    return pd.concat(partes, ignore_index=True)


def agregar(recorte: pd.DataFrame) -> pd.DataFrame:
    """Decis de valor e prazo por porte × seção (+ marginais 'todas'/'TODOS')."""
    recorte = recorte.dropna(subset=["porte"])
    recorte["secao"] = recorte["secao"].fillna("desconhecida")

    linhas = []
    grupos = [("TODOS", "todas"), ("MICRO", "todas"), ("PEQUENA", "todas")]
    grupos += sorted({(p, s) for p, s in zip(recorte["porte"], recorte["secao"], strict=True)})
    for porte, secao in grupos:
        g = recorte
        if porte != "TODOS":
            g = g[g["porte"] == porte]
        if secao != "todas":
            g = g[g["secao"] == secao]
        linha: dict = {"porte": porte, "secao": secao, "n": int(len(g))}
        for campo, prefixo in (("valor", "valor"), ("prazo", "prazo")):
            serie = g[campo].dropna()
            for q in QUANTIS:
                chave = f"{prefixo}_q{int(q * 100):02d}"
                linha[chave] = float(serie.quantile(q)) if len(serie) else None
        linhas.append(linha)
    return pd.DataFrame(linhas)


def carregar_bq(df: pd.DataFrame, project_id: str, dataset: str) -> str:
    """Substitui a staging `bndes_agregado` (11_bndes_referencia.sql faz a final).

    Carga por CSV com schema explícito (sem pyarrow, como ingest_sba).
    """
    import io

    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)
    table_id = f"{project_id}.{dataset}.{TABELA_STAGING}"
    schema = [
        bigquery.SchemaField("porte", "STRING"),
        bigquery.SchemaField("secao", "STRING"),
        bigquery.SchemaField("n", "INT64"),
    ] + [
        bigquery.SchemaField(f"{campo}_q{int(q * 100):02d}", "FLOAT64")
        for campo in ("valor", "prazo")
        for q in QUANTIS
    ]
    config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    csv = df.to_csv(index=False)
    job = client.load_table_from_file(io.BytesIO(csv.encode("utf-8")), table_id, job_config=config)
    job.result()
    return table_id


def checar_janela() -> None:
    """Confere se há contratação posterior a 2022 em outro recurso do conjunto."""
    destino = DESTINO_LOCAL / Path(URL_NAO_AUTOMATICAS).name
    if not destino.exists():
        req = urllib.request.Request(URL_NAO_AUTOMATICAS, headers={"User-Agent": "pme-risk/0.1"})
        with urllib.request.urlopen(req, timeout=600) as resp, open(destino, "wb") as f:
            while bloco := resp.read(1 << 20):
                f.write(bloco)
    datas = pd.read_csv(
        destino, sep=";", usecols=["data_da_contratacao"], dtype=str, encoding="latin-1"
    )["data_da_contratacao"]
    print(f"não automáticas: última contratação {datas.max()}")


def main() -> None:
    arquivo = baixar()
    agregado = agregar(recortar(arquivo))
    table_id = carregar_bq(
        agregado, os.environ["GCP_PROJECT_ID"], os.environ.get("BQ_DATASET", "pme_risk")
    )
    print(f"{len(agregado)} grupos -> {table_id.split('.', 1)[1]}")
    total = agregado[(agregado["porte"] == "TODOS") & (agregado["secao"] == "todas")]["n"].iloc[0]
    print(f"operações MICRO/PEQUENA {ANO_INICIO}-{ANO_FIM}: {total}")


if __name__ == "__main__":
    main()

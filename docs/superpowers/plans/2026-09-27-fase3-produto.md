# Fase 3 — Produto (API, drift, deploy) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar a Fase 3 do pme-risk (SPEC §5): API FastAPI com pipeline completo via adapter, job de drift (PSI), Dockerfile e scripts de deploy Cloud Run — sem tocar em nenhum arquivo da Fase 2.

**Architecture:** `api/pipeline.py` é o único módulo que importa código da Fase 2 (`agents.*`, `PortaoHumano`, `TrilhaAuditoria`) e `model.predict`. Rotas finas recebem o `Pipeline` por injeção de dependência do FastAPI; o `Pipeline` aceita callables injetados (`extrair_fn`, `prever_fn`, ...) para testes sem GCP. Drift é um script independente (`monitoring/drift_job.py`) que roda como Cloud Run Job.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, google-cloud-bigquery, uv, pytest, ruff, Docker, gcloud.

**Spec:** `docs/superpowers/specs/2026-09-27-fase3-produto-design.md`

**Restrição crítica:** NÃO modificar `agents/**`, `api/routes/portao_humano.py`, `api/auditoria.py`, `tests/unit/test_schemas.py`, `README.md`. Só criar arquivos novos (exceções: `pyproject.toml` dev-deps e `.env.example`, ambos add-only).

**Assinaturas da Fase 2 usadas pelo adapter (já existem, não mudar):**

```python
# agents/extractor/extractor.py
extrair(texto: str, project_id: str | None = None) -> DadosExtraidos
PROMPT_PATH: Path

# agents/pesquisador/pesquisador.py
enriquecer(extraidos: DadosExtraidos) -> DadosEnriquecidos

# agents/redator/redator.py
redigir(enriquecidos, resultado_modelo, project_id=None) -> ResultadoRedacao  # .texto, .evidencias
PROMPT_PATH: Path

# model/predict.py
prever(features: dict[str, float], project_id: str, dataset: str) -> ResultadoPredicao
# ResultadoPredicao(pd: float, faixa_risco: str, fatores: list[tuple[str, float]], model_version: str)

# api/routes/portao_humano.py — PortaoHumano(project_id, dataset)
.criar(laudo_id, pedido_bruto, enriquecidos_json, resultado_modelo_json, texto, evidencias_json) -> dict
.obter(laudo_id) -> dict | None
.decidir(laudo_id, decisao, decidido_por, observacao=None) -> dict

# api/auditoria.py — TrilhaAuditoria(project_id, dataset)
.hash_prompt(prompt_text: str) -> str  # staticmethod
.registrar(laudo_id, pedido_bruto, model_version, prompts_usados, decisao_humana, etapas) -> None
```

---

### Task 1: Mapeamento pedido → features (`api/pipeline.py` parte 1)

**Files:**
- Create: `api/pipeline.py`
- Test: `tests/unit/test_pipeline_features.py`

- [ ] **Step 1: Write the failing test**

```python
"""Testes do mapeamento PedidoCredito → features do modelo (SPEC §3.2)."""

from __future__ import annotations

from agents.schemas import PedidoCredito
from api.pipeline import _fnv1a_64_signed, pedido_para_features


def _pedido(**overrides: object) -> PedidoCredito:
    base = {
        "setor": "saude_odontologica",
        "porte": "ME",
        "uf": "SP",
        "anos_operacao": 5,
        "faturamento_anual_declarado": 2_000_000,
        "valor_solicitado": 300_000,
        "prazo_meses": 36,
        "finalidade": "expansao",
    }
    return PedidoCredito(**{**base, **overrides})  # type: ignore[arg-type]


class TestPedidoParaFeatures:
    def test_mapeamento_direto(self):
        feats = pedido_para_features(_pedido())
        assert feats["amt_income_total"] == 2_000_000.0
        assert feats["amt_credit"] == 300_000.0
        assert feats["prazo_meses_estimado"] == 36.0
        assert feats["amt_annuity"] == 300_000.0 / 36
        assert feats["anos_operacao"] == 5.0
        assert feats["days_employed_abs"] == round(5 * 365.25, 2)
        assert feats["region_rating"] == 2.0

    def test_prazo_ausente_usa_default_36(self):
        feats = pedido_para_features(_pedido(prazo_meses=None))
        assert feats["prazo_meses_estimado"] == 36.0
        assert feats["amt_annuity"] == 300_000.0 / 36

    def test_anos_operacao_limitado_a_60(self):
        feats = pedido_para_features(_pedido(anos_operacao=80))
        assert feats["anos_operacao"] == 60.0
        assert feats["days_employed_abs"] == round(60 * 365.25, 2)

    def test_occupation_encoded_deterministico_e_faixa(self):
        f1 = pedido_para_features(_pedido())
        f2 = pedido_para_features(_pedido())
        assert f1["occupation_type_encoded"] == f2["occupation_type_encoded"]
        assert 0.0 <= f1["occupation_type_encoded"] <= 99.0


class TestFnv1a:
    def test_deterministico(self):
        assert _fnv1a_64_signed("saude") == _fnv1a_64_signed("saude")

    def test_diferente_por_entrada(self):
        assert _fnv1a_64_signed("saude") != _fnv1a_64_signed("comercio")

    def test_valor_assinado_64_bits(self):
        h = _fnv1a_64_signed("x")
        assert -(1 << 63) <= h < (1 << 63)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_pipeline_features.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'api.pipeline'`

- [ ] **Step 3: Write minimal implementation**

`api/pipeline.py`:

```python
"""Adapter de pipeline — único ponto de contato entre a Fase 3 (API) e a Fase 2 (agentes).

Referência: docs/superpowers/specs/2026-09-27-fase3-produto-design.md
Se a Fase 2 for reestruturada, este é o único arquivo a ajustar.

O mapeamento pedido → features segue a HIPÓTESE documentada em
model/features.py (SPEC §3.2) — proxy, não paridade com Home Credit.
"""

from __future__ import annotations

from agents.schemas import PedidoCredito

# Proxy neutro de UF → region_rating. 2 é a moda de REGION_RATING_CLIENT.
# Sem inventar risco por UF (SPEC §3.2: "não geografia real").
_REGION_RATING_DEFAULT = 2

# Prazo default quando o pedido não menciona (mesma base do clip em 01_load_features.sql)
_PRAZO_DEFAULT_MESES = 36


def _fnv1a_64_signed(texto: str) -> int:
    """FNV-1a 64-bit com interpretação assinada — determinístico para `setor`.

    Não exige paridade exata com FARM_FINGERPRINT do BigQuery: o mapeamento
    setor → occupation_type já é aproximação documentada (SPEC §3.2).
    """
    h = 0xcbf29ce484222325
    for byte in texto.encode("utf-8"):
        h ^= byte
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h - (1 << 64) if h >= (1 << 63) else h


def pedido_para_features(pedido: PedidoCredito) -> dict[str, float]:
    """Mapeia PedidoCredito (PME) → vetor de features do modelo (Home Credit)."""
    prazo = min(pedido.prazo_meses or _PRAZO_DEFAULT_MESES, 120)
    anos = min(max(pedido.anos_operacao, 0), 60)
    return {
        "amt_income_total": float(pedido.faturamento_anual_declarado),
        "amt_credit": float(pedido.valor_solicitado),
        "amt_annuity": float(pedido.valor_solicitado) / prazo,
        "prazo_meses_estimado": float(prazo),
        "anos_operacao": float(anos),
        "days_employed_abs": round(anos * 365.25, 2),
        "occupation_type_encoded": float(abs(_fnv1a_64_signed(pedido.setor)) % 100),
        "region_rating": float(_REGION_RATING_DEFAULT),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_pipeline_features.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add api/pipeline.py tests/unit/test_pipeline_features.py
git commit -m "feat: mapeamento pedido->features no adapter de pipeline"
```

---

### Task 2: Classe `Pipeline` com injeção de dependências

**Files:**
- Modify: `api/pipeline.py`
- Test: `tests/unit/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
"""Testes do Pipeline — orquestração com fakes, sem GCP."""

from __future__ import annotations

from agents.redator.redator import ResultadoRedacao
from agents.schemas import DadosEnriquecidos, DadosExtraidos, PedidoCredito
from api.pipeline import LaudoCriado, Pipeline, Recusa

_PEDIDO = PedidoCredito(
    setor="saude_odontologica",
    porte="ME",
    uf="SP",
    anos_operacao=5,
    faturamento_anual_declarado=2_000_000,
    valor_solicitado=300_000,
    prazo_meses=36,
    finalidade="expansao",
)


class FakePortao:
    def __init__(self) -> None:
        self.laudos: dict[str, dict] = {}

    def criar(self, laudo_id, pedido_bruto, enriquecidos_json, resultado_modelo_json, texto, evidencias_json):
        self.laudos[laudo_id] = {
            "laudo_id": laudo_id,
            "pedido_bruto": pedido_bruto,
            "enriquecidos_json": enriquecidos_json,
            "resultado_modelo_json": resultado_modelo_json,
            "texto": texto,
            "evidencias_json": evidencias_json,
            "status": "pendente",
            "criado_em": "2026-09-27T00:00:00Z",
        }

    def obter(self, laudo_id: str) -> dict | None:
        return self.laudos.get(laudo_id)

    def decidir(self, laudo_id, decisao, decidido_por, observacao=None):
        row = self.laudos.get(laudo_id)
        if row is None:
            return None
        row.update(
            status=decisao,
            decisao=decisao,
            decidido_por=decidido_por,
            decidido_em="2026-09-27T01:00:00Z",
            observacao_humana=observacao,
        )
        return row


class FakeAuditoria:
    def __init__(self) -> None:
        self.registros: list[dict] = []

    def registrar(self, **kwargs) -> None:
        self.registros.append(kwargs)


def _pipeline(recusa: bool = False) -> tuple[Pipeline, FakePortao, FakeAuditoria]:
    portao = FakePortao()
    auditoria = FakeAuditoria()

    def extrair_fn(texto: str) -> DadosExtraidos:
        return DadosExtraidos(
            pedido=_PEDIDO,
            fora_de_escopo=recusa,
            motivo_recusa="pessoa física" if recusa else None,
        )

    def enriquecer_fn(extraidos: DadosExtraidos) -> DadosEnriquecidos:
        return DadosEnriquecidos(extraidos=extraidos, fonte_por_campo={"setor": "declarado"})

    def prever_fn(features: dict[str, float], project_id: str, dataset: str):
        from model.predict import ResultadoPredicao

        return ResultadoPredicao(
            pd=0.07, faixa_risco="medio", fatores=[("amt_credit", 0.02)], model_version="logreg_v1"
        )

    def redigir_fn(enriquecidos, resultado_modelo, project_id=None) -> ResultadoRedacao:
        return ResultadoRedacao(texto="Laudo de risco.", evidencias=["LGPD art. 20"])

    pipeline = Pipeline(
        "projeto-teste",
        "dataset_teste",
        extrair_fn=extrair_fn,
        enriquecer_fn=enriquecer_fn,
        prever_fn=prever_fn,
        redigir_fn=redigir_fn,
        portao=portao,
        auditoria=auditoria,
    )
    return pipeline, portao, auditoria


class TestPipelineGerar:
    def test_caminho_feliz_cria_laudo_pendente(self):
        pipeline, portao, _ = _pipeline()
        resultado = pipeline.gerar("texto do pedido")
        assert isinstance(resultado, LaudoCriado)
        assert resultado.status == "pendente"
        row = portao.obter(resultado.laudo_id)
        assert row is not None and row["status"] == "pendente"

    def test_caminho_feliz_registra_auditoria(self):
        pipeline, _, auditoria = _pipeline()
        resultado = pipeline.gerar("texto do pedido")
        assert isinstance(resultado, LaudoCriado)
        assert len(auditoria.registros) == 1
        registro = auditoria.registros[0]
        assert registro["laudo_id"] == resultado.laudo_id
        assert registro["model_version"] == "logreg_v1"
        assert "extrator" in registro["prompts_usados"]
        assert "redator" in registro["prompts_usados"]

    def test_recusa_nao_cria_laudo_mas_audita(self):
        pipeline, portao, auditoria = _pipeline(recusa=True)
        resultado = pipeline.gerar("pedido de pessoa física")
        assert isinstance(resultado, Recusa)
        assert resultado.motivo == "pessoa física"
        assert portao.laudos == {}
        assert len(auditoria.registros) == 1
        assert auditoria.registros[0]["model_version"] is None

    def test_pd_no_laudo_e_a_do_modelo(self):
        import json

        pipeline, portao, _ = _pipeline()
        resultado = pipeline.gerar("texto")
        assert isinstance(resultado, LaudoCriado)
        row = portao.obter(resultado.laudo_id)
        resultado_modelo = json.loads(row["resultado_modelo_json"])
        assert resultado_modelo["pd"] == 0.07
        assert resultado_modelo["model_version"] == "logreg_v1"


class TestPipelineDecisao:
    def test_decidir_encaminha_para_portao(self):
        pipeline, _, _ = _pipeline()
        laudo = pipeline.gerar("texto")
        assert isinstance(laudo, LaudoCriado)
        row = pipeline.decidir(laudo.laudo_id, "aprovado", "analista-1")
        assert row is not None and row["status"] == "aprovado"

    def test_decidir_laudo_inexistente_retorna_none(self):
        pipeline, _, _ = _pipeline()
        assert pipeline.decidir("inexistente", "aprovado", "analista-1") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_pipeline.py -v`
Expected: FAIL com `ImportError: cannot import name 'LaudoCriado'`

- [ ] **Step 3: Write minimal implementation**

Em `api/pipeline.py`: acrescentar os imports abaixo ao TOPO do arquivo (mesclando com os do Task 1, ordem isort: stdlib → third-party → first-party) e o código das classes ao FINAL do arquivo:

```python
import json
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

from agents.extractor.extractor import PROMPT_PATH as _EXTRACTOR_PROMPT_PATH
from agents.extractor.extractor import extrair
from agents.pesquisador.pesquisador import enriquecer
from agents.redator.redator import PROMPT_PATH as _REDACTOR_PROMPT_PATH
from agents.redator.redator import ResultadoRedacao
from agents.redator.redator import redigir
from agents.schemas import DadosEnriquecidos, DadosExtraidos, ResultadoModelo
from api.auditoria import TrilhaAuditoria
from api.routes.portao_humano import PortaoHumano
from model.predict import ResultadoPredicao, prever


@dataclass(frozen=True)
class Recusa:
    motivo: str


@dataclass(frozen=True)
class LaudoCriado:
    laudo_id: str
    status: str = "pendente"


def _hashes_prompt() -> dict[str, str]:
    return {
        "extrator": TrilhaAuditoria.hash_prompt(
            _EXTRACTOR_PROMPT_PATH.read_text(encoding="utf-8")
        ),
        "redator": TrilhaAuditoria.hash_prompt(
            _REDACTOR_PROMPT_PATH.read_text(encoding="utf-8")
        ),
    }


class Pipeline:
    """Orquestra extrator → pesquisador → modelo → redator + persistência.

    Callables e clientes são injetáveis para testes sem GCP.
    """

    def __init__(
        self,
        project_id: str,
        dataset: str,
        *,
        extrair_fn: Callable[..., DadosExtraidos] = extrair,
        enriquecer_fn: Callable[[DadosExtraidos], DadosEnriquecidos] = enriquecer,
        prever_fn: Callable[..., ResultadoPredicao] = prever,
        redigir_fn: Callable[..., ResultadoRedacao] = redigir,
        portao: PortaoHumano | None = None,
        auditoria: TrilhaAuditoria | None = None,
    ) -> None:
        self.project_id = project_id
        self.dataset = dataset
        self._extrair_fn = extrair_fn
        self._enriquecer_fn = enriquecer_fn
        self._prever_fn = prever_fn
        self._redigir_fn = redigir_fn
        self._portao = portao or PortaoHumano(project_id, dataset)
        self._auditoria = auditoria or TrilhaAuditoria(project_id, dataset)

    def gerar(self, texto: str) -> LaudoCriado | Recusa:
        """Roda o pipeline completo até `status='pendente'` (SPEC §5.1)."""
        etapas: list[dict[str, str]] = []
        extraidos = self._extrair_fn(texto)
        etapas.append({"etapa": "extrator", "timestamp": _agora()})

        if extraidos.fora_de_escopo:
            self._auditoria.registrar(
                laudo_id="-",
                pedido_bruto=texto,
                model_version=None,
                prompts_usados=_hashes_prompt(),
                decisao_humana=None,
                etapas=etapas,
            )
            return Recusa(motivo=extraidos.motivo_recusa or "fora de escopo")

        enriquecidos = self._enriquecer_fn(extraidos)
        etapas.append({"etapa": "pesquisador", "timestamp": _agora()})

        features = pedido_para_features(enriquecidos.extraidos.pedido)
        predicao = self._prever_fn(features, project_id=self.project_id, dataset=self.dataset)
        etapas.append({"etapa": "modelo", "timestamp": _agora()})

        resultado = ResultadoModelo(
            pd=predicao.pd,
            faixa_risco=predicao.faixa_risco,
            fatores=[(nome, contrib) for nome, contrib in predicao.fatores],
            model_version=predicao.model_version,
        )
        redacao = self._redigir_fn(enriquecidos, resultado, project_id=self.project_id)
        etapas.append({"etapa": "redator", "timestamp": _agora()})

        laudo_id = str(uuid.uuid4())
        self._portao.criar(
            laudo_id=laudo_id,
            pedido_bruto=texto,
            enriquecidos_json=enriquecidos.model_dump_json(),
            resultado_modelo_json=resultado.model_dump_json(),
            texto=redacao.texto,
            evidencias_json=json.dumps(redacao.evidencias, ensure_ascii=False),
        )
        self._auditoria.registrar(
            laudo_id=laudo_id,
            pedido_bruto=texto,
            model_version=predicao.model_version,
            prompts_usados=_hashes_prompt(),
            decisao_humana=None,
            etapas=etapas,
        )
        return LaudoCriado(laudo_id=laudo_id)

    def obter(self, laudo_id: str) -> dict | None:
        return self._portao.obter(laudo_id)

    def decidir(
        self,
        laudo_id: str,
        decisao: str,
        decidido_por: str,
        observacao: str | None = None,
    ) -> dict | None:
        return self._portao.decidir(laudo_id, decisao, decidido_por, observacao)


def _agora() -> str:
    return datetime.now(UTC).isoformat()


@lru_cache
def get_pipeline() -> Pipeline:
    """Dependência FastAPI — instância real (GCP) para produção."""
    return Pipeline(
        os.environ["GCP_PROJECT_ID"],
        os.environ.get("BQ_DATASET", "pme_risk"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_pipeline.py -v`
Expected: 6 passed

- [ ] **Step 5: Run ruff**

Run: `uv run ruff check api/pipeline.py tests/unit/test_pipeline.py`
Expected: All checks passed (se reclamar de ordem de imports, rodar `uv run ruff check --fix`)

- [ ] **Step 6: Commit**

```bash
git add api/pipeline.py tests/unit/test_pipeline.py
git commit -m "feat: Pipeline com injeção de dependências — orquestração testável sem GCP"
```

---

### Task 3: Rotas FastAPI + healthz

**Files:**
- Create: `api/routes/laudos.py`, `api/routes/decisao.py`, `api/main.py`
- Modify: `pyproject.toml` (dev deps)
- Test: `tests/unit/test_api.py`

- [ ] **Step 1: Add httpx as dev dependency** (necessário para `TestClient`)

```bash
uv add --dev "httpx>=0.27"
```

- [ ] **Step 2: Write the failing test**

```python
"""Testes das rotas da API com pipeline falso — sem GCP."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.pipeline import LaudoCriado, Recusa, get_pipeline
_ROW = {
    "laudo_id": "id-1",
    "status": "pendente",
    "enriquecidos_json": json.dumps({"extraidos": {"pedido": {"porte": "ME"}}}),
    "resultado_modelo_json": json.dumps({"pd": 0.07, "faixa_risco": "medio"}),
    "texto": "Laudo de risco.",
    "evidencias_json": json.dumps(["LGPD art. 20"]),
    "decidido_por": None,
    "decidido_em": None,
    "observacao_humana": None,
    "criado_em": "2026-09-27T00:00:00Z",
}


class FakePipeline:
    def __init__(self) -> None:
        self.laudos: dict[str, dict] = {}
        self.recusa: Recusa | None = None

    def gerar(self, texto: str) -> LaudoCriado | Recusa:
        if self.recusa is not None:
            return self.recusa
        laudo_id = "id-1"
        self.laudos[laudo_id] = {**_ROW}
        return LaudoCriado(laudo_id=laudo_id)

    def obter(self, laudo_id: str) -> dict | None:
        return self.laudos.get(laudo_id)

    def decidir(self, laudo_id, decisao, decidido_por, observacao=None):
        row = self.laudos.get(laudo_id)
        if row is None:
            return None
        row.update(status=decisao, decidido_por=decidido_por, observacao_humana=observacao)
        return row


@pytest.fixture
def client() -> Iterator[tuple[TestClient, FakePipeline]]:
    fake = FakePipeline()
    app.dependency_overrides[get_pipeline] = lambda: fake
    with TestClient(app) as test_client:
        yield test_client, fake
    app.dependency_overrides.clear()


class TestHealthz:
    def test_healthz_200(self, client):
        response, _ = client
        assert response.get("/healthz").status_code == 200
        assert response.get("/healthz").json() == {"status": "ok"}


class TestPostLaudos:
    def test_cria_laudo_201(self, client):
        response, fake = client
        r = response.post("/laudos", json={"texto": "clínica odontológica quer crédito"})
        assert r.status_code == 201
        body = r.json()
        assert body["laudo_id"] == "id-1"
        assert body["status"] == "pendente"
        assert fake.laudos["id-1"]["status"] == "pendente"

    def test_recusa_422(self, client):
        response, fake = client
        fake.recusa = Recusa(motivo="pessoa física")
        r = response.post("/laudos", json={"texto": "quero empréstimo pessoal"})
        assert r.status_code == 422
        assert r.json()["detail"] == {"motivo_recusa": "pessoa física"}

    def test_texto_curto_422(self, client):
        response, _ = client
        r = response.post("/laudos", json={"texto": "curto"})
        assert r.status_code == 422


class TestGetLaudos:
    def test_obtem_laudo_aninhado(self, client):
        response, fake = client
        fake.gerar("clínica odontológica quer crédito de expansão")
        r = response.get("/laudos/id-1")
        assert r.status_code == 200
        body = r.json()
        assert body["laudo_id"] == "id-1"
        assert body["enriquecidos"]["extraidos"]["pedido"]["porte"] == "ME"
        assert body["resultado_modelo"]["pd"] == 0.07
        assert body["evidencias"] == ["LGPD art. 20"]

    def test_laudo_inexistente_404(self, client):
        response, _ = client
        assert response.get("/laudos/nao-existe").status_code == 404


class TestPatchDecisao:
    def test_decide_laudo_200(self, client):
        response, fake = client
        fake.gerar("clínica odontológica quer crédito de expansão")
        r = response.patch(
            "/laudos/id-1/decisao",
            json={"decisao": "aprovado", "decidido_por": "analista-1"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "aprovado"
        assert body["decidido_por"] == "analista-1"

    def test_decisao_invalida_422(self, client):
        response, _ = client
        r = response.patch(
            "/laudos/id-1/decisao",
            json={"decisao": "talvez", "decidido_por": "analista-1"},
        )
        assert r.status_code == 422

    def test_laudo_inexistente_404(self, client):
        response, _ = client
        r = response.patch(
            "/laudos/nao-existe/decisao",
            json={"decisao": "aprovado", "decidido_por": "analista-1"},
        )
        assert r.status_code == 404
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_api.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'api.main'`

- [ ] **Step 4: Write the implementation**

`api/routes/laudos.py`:

```python
"""Rotas de laudos — SPEC §5.1.

Rotas finas: parse → pipeline (adapter) → resposta.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.pipeline import LaudoCriado, Pipeline, Recusa, get_pipeline

router = APIRouter(tags=["laudos"])


class PedidoTexto(BaseModel):
    texto: str = Field(min_length=10, description="Pedido de crédito PME em pt-BR")


@router.post("/laudos", status_code=201)
def criar_laudo(
    pedido: PedidoTexto, pipeline: Pipeline = Depends(get_pipeline)
) -> dict[str, str]:
    resultado = pipeline.gerar(pedido.texto)
    if isinstance(resultado, Recusa):
        raise HTTPException(status_code=422, detail={"motivo_recusa": resultado.motivo})
    assert isinstance(resultado, LaudoCriado)
    return {"laudo_id": resultado.laudo_id, "status": resultado.status}


@router.get("/laudos/{laudo_id}")
def obter_laudo(laudo_id: str, pipeline: Pipeline = Depends(get_pipeline)) -> dict:
    row = pipeline.obter(laudo_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Laudo não encontrado")
    return _serializar(row)


def _serializar(row: dict) -> dict:
    return {
        "laudo_id": row["laudo_id"],
        "status": row["status"],
        "enriquecidos": json.loads(row["enriquecidos_json"]),
        "resultado_modelo": json.loads(row["resultado_modelo_json"]),
        "texto": row["texto"],
        "evidencias": json.loads(row["evidencias_json"]),
        "decidido_por": row.get("decidido_por"),
        "decidido_em": row.get("decidido_em"),
        "observacao_humana": row.get("observacao_humana"),
        "criado_em": row.get("criado_em"),
    }
```

`api/routes/decisao.py`:

```python
"""Portão humano — endpoint de decisão (SPEC §5.1, §4.3)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.pipeline import Pipeline, get_pipeline

router = APIRouter(tags=["laudos"])


class DecisaoRequest(BaseModel):
    decisao: Literal["aprovado", "corrigido", "rejeitado"]
    decidido_por: str = Field(min_length=1, description="Identificador do analista")
    observacao: str | None = None


@router.patch("/laudos/{laudo_id}/decisao")
def decidir_laudo(
    laudo_id: str, body: DecisaoRequest, pipeline: Pipeline = Depends(get_pipeline)
) -> dict:
    row = pipeline.decidir(laudo_id, body.decisao, body.decidido_por, body.observacao)
    if row is None:
        raise HTTPException(status_code=404, detail="Laudo não encontrado")
    return {
        "laudo_id": row["laudo_id"],
        "status": row["status"],
        "decidido_por": row["decidido_por"],
        "decidido_em": row["decidido_em"],
    }
```

`api/main.py`:

```python
"""API pme-risk — SPEC §5.1."""

from __future__ import annotations

from fastapi import FastAPI

from api.routes import decisao, laudos

app = FastAPI(
    title="pme-risk",
    description="Laudo de risco de crédito PME, auditável",
    version="0.1.0",
)
app.include_router(laudos.router)
app.include_router(decisao.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_api.py -v`
Expected: 8 passed

- [ ] **Step 6: Smoke test local do servidor**

Run: `uv run uvicorn api.main:app --port 8000` (em outro terminal) e `curl http://localhost:8000/healthz`
Expected: `{"status":"ok"}` (interromper o servidor depois)

- [ ] **Step 7: Commit**

```bash
git add api/main.py api/routes/laudos.py api/routes/decisao.py tests/unit/test_api.py pyproject.toml uv.lock
git commit -m "feat: API FastAPI — POST/GET laudos, portão humano e healthz"
```

---

### Task 4: PSI puro (`monitoring/drift_job.py` parte 1)

**Files:**
- Create: `monitoring/drift_job.py`
- Test: `tests/unit/test_drift.py`

- [ ] **Step 1: Write the failing test**

```python
"""Testes do cálculo de PSI — função pura, sem GCP."""

from __future__ import annotations

import random

from monitoring.drift_job import LIMIAR_PSI, calcular_drift, psi


def _amostra(n: int, mu: float, sigma: float, seed: int) -> list[float]:
    rng = random.Random(seed)
    return [rng.gauss(mu, sigma) for _ in range(n)]


class TestPsi:
    def test_distribuicoes_identicas_psi_zero(self):
        esp = _amostra(5000, 0, 1, seed=42)
        assert psi(esp, esp) == 0.0

    def test_mesma_distribuicao_sementes_diferentes_psi_baixo(self):
        esp = _amostra(5000, 0, 1, seed=1)
        atu = _amostra(5000, 0, 1, seed=2)
        assert psi(esp, atu) < 0.05

    def test_deslocamento_2_sigma_estoura_limiar(self):
        esp = _amostra(5000, 0, 1, seed=1)
        atu = _amostra(5000, 2, 1, seed=2)
        assert psi(esp, atu) > LIMIAR_PSI

    def test_atual_constante_nao_gera_inf_nem_nan(self):
        esp = _amostra(1000, 0, 1, seed=1)
        v = psi(esp, [0.0] * 100)
        assert v == v and v not in (float("inf"), float("-inf"))

    def test_lista_vazia_retorna_zero(self):
        assert psi([], []) == 0.0


class TestCalcularDrift:
    def test_retorna_psi_por_feature(self):
        esp = _amostra(2000, 0, 1, seed=1)
        desloc = _amostra(2000, 3, 1, seed=2)
        drift = calcular_drift(
            treino={"amt_credit": esp, "anos_operacao": esp},
            atual={"amt_credit": desloc, "anos_operacao": esp},
        )
        assert drift["amt_credit"] > LIMIAR_PSI
        assert drift["anos_operacao"] < 0.05

    def test_feature_sem_dados_atuais_nao_quebra(self):
        esp = _amostra(100, 0, 1, seed=1)
        drift = calcular_drift(treino={"amt_credit": esp}, atual={})
        assert drift["amt_credit"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_drift.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'monitoring'`

- [ ] **Step 3: Write minimal implementation**

`monitoring/drift_job.py`:

```python
"""Job de drift — PSI da entrada (laudos) vs. treino (PLANO §5, SPEC §5.3).

Compara as features NUMÉRICAS com análogo direto entre pedido e treino.
Categóricas (porte, UF, setor) ficam de fora: sem análogo honesto no Home
Credit (SPEC §3.2) — limite documentado, não omissão.

PSI > 0.25 → log estruturado WARNING (log-based alert do free tier).
Roda como Cloud Run Job (deploy_drift.sh), não no processo da API.
"""

from __future__ import annotations

import bisect
import logging
import math
from collections.abc import Sequence

LIMIAR_PSI = 0.25
N_BINS = 10
_EPS = 1e-6

MAPEAMENTO_FEATURE_CAMPO = {
    "amt_credit": "valor_solicitado",
    "amt_income_total": "faturamento_anual_declarado",
    "anos_operacao": "anos_operacao",
    "prazo_meses_estimado": "prazo_meses",
}


def _quantile(valores: Sequence[float], q: float) -> float:
    ordenado = sorted(valores)
    idx = min(int(q * (len(ordenado) - 1)), len(ordenado) - 1)
    return ordenado[idx]


def _proporcoes(valores: Sequence[float], limites: list[float]) -> list[float]:
    contagens = [0] * (len(limites) + 1)
    for v in valores:
        contagens[bisect.bisect_right(limites, v)] += 1
    return [c / len(valores) for c in contagens]


def psi(esperado: Sequence[float], atual: Sequence[float], n_bins: int = N_BINS) -> float:
    """Population Stability Index com bins por quantis da distribuição de treino."""
    if len(esperado) == 0 or len(atual) == 0:
        return 0.0
    limites = sorted({_quantile(esperado, i / n_bins) for i in range(1, n_bins)})
    p_esp = _proporcoes(esperado, limites)
    p_atu = _proporcoes(atual, limites)
    total = 0.0
    for e, a in zip(p_esp, p_atu, strict=True):
        e = max(e, _EPS)
        a = max(a, _EPS)
        total += (a - e) * math.log(a / e)
    return total


def calcular_drift(
    treino: dict[str, list[float]], atual: dict[str, list[float]]
) -> dict[str, float]:
    """PSI por feature; feature sem dados atuais → 0.0 (sem drift mensurável)."""
    return {feat: psi(vals, atual.get(feat, [])) for feat, vals in treino.items()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_drift.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add monitoring/drift_job.py tests/unit/test_drift.py
git commit -m "feat: PSI puro com bins por quantis — base do job de drift"
```

---

### Task 5: Job de drift (BigQuery + logs)

**Files:**
- Modify: `monitoring/drift_job.py`
- Modify: `.env.example` (add-only)

- [ ] **Step 1: Implementar leitura do BigQuery e `main`**

Em `monitoring/drift_job.py`: acrescentar `json`, `os`, `sys` ao bloco stdlib de imports no TOPO, `from google.cloud import bigquery` ao bloco third-party (entre stdlib e as constantes), e as funções abaixo ao FINAL do arquivo:

```python

def _carregar_treino(client: bigquery.Client, dataset: str) -> dict[str, list[float]]:
    colunas = ", ".join(MAPEAMENTO_FEATURE_CAMPO)
    query = f"""
        SELECT {colunas}
        FROM `{client.project}.{dataset}.features`
        WHERE split = 'train'
    """
    rows = list(client.query(query).result())
    return {
        feat: [float(row[feat]) for row in rows if row[feat] is not None]
        for feat in MAPEAMENTO_FEATURE_CAMPO
    }


def _carregar_laudos(
    client: bigquery.Client, dataset: str, n_laudos: int
) -> dict[str, list[float]]:
    query = f"""
        SELECT enriquecidos_json
        FROM `{client.project}.{dataset}.laudos`
        ORDER BY criado_em DESC
        LIMIT {int(n_laudos)}
    """
    atual: dict[str, list[float]] = {feat: [] for feat in MAPEAMENTO_FEATURE_CAMPO}
    for row in client.query(query).result():
        pedido = json.loads(row["enriquecidos_json"])["extraidos"]["pedido"]
        for feat, campo in MAPEAMENTO_FEATURE_CAMPO.items():
            valor = pedido.get(campo)
            if valor is not None:
                atual[feat].append(float(valor))
    return atual


def rodar(project_id: str, dataset: str, n_laudos: int = 100) -> dict:
    """Calcula drift, loga WARNING acima do limiar e devolve o resumo."""
    client = bigquery.Client(project=project_id)
    treino = _carregar_treino(client, dataset)
    atual = _carregar_laudos(client, dataset, n_laudos)
    psis = calcular_drift(treino, atual)
    alertas = {feat: valor for feat, valor in psis.items() if valor > LIMIAR_PSI}
    for feat, valor in alertas.items():
        logging.warning(
            "drift detectado: %s PSI=%.4f > %.2f", feat, valor, LIMIAR_PSI
        )
    return {
        "psis": psis,
        "limiar": LIMIAR_PSI,
        "n_laudos": n_laudos,
        "alertas": alertas,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    resumo = rodar(
        project_id=os.environ["GCP_PROJECT_ID"],
        dataset=os.environ.get("BQ_DATASET", "pme_risk"),
        n_laudos=int(os.environ.get("DRIFT_N_LAUDOS", "100")),
    )
    print(json.dumps(resumo, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verificar que os testes existentes continuam passando**

Run: `uv run pytest tests/unit/test_drift.py -v`
Expected: 7 passed (imports de bigquery não quebram sem credenciais — cliente só é criado em `rodar`)

- [ ] **Step 3: Atualizar `.env.example`** (adicionar ao final):

```
# Cloud Run / deploy (Fase 3)
RUN_REGION=us-central1
RUN_SERVICE=pme-risk-api
RUN_SERVICE_ACCOUNT=
DRIFT_N_LAUDOS=100
```

- [ ] **Step 4: Commit**

```bash
git add monitoring/drift_job.py .env.example
git commit -m "feat: job de drift lê BigQuery e loga WARNING acima de PSI 0.25"
```

---

### Task 6: Docker

**Files:**
- Create: `docker/Dockerfile`, `.dockerignore`

- [ ] **Step 1: Criar `.dockerignore`** (raiz do repo):

```
.git
.venv
.env
data/raw
data/golden_set
docs/
eval/
tests/
infra/
**/__pycache__
.pytest_cache
.ruff_cache
```

- [ ] **Step 2: Criar `docker/Dockerfile`**:

```dockerfile
# API pme-risk — Cloud Run (SPEC §5.2)
# Credenciais: ADC no runtime via service account do Cloud Run (sem API key)
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY agents/ agents/
COPY api/ api/
COPY model/ model/
COPY monitoring/ monitoring/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

- [ ] **Step 3: Smoke test do build** (se Docker estiver disponível localmente)

Run: `docker build -f docker/Dockerfile -t pme-risk-api .`
Expected: build concluído sem erro. Se o Docker não estiver disponível, o build real acontece no `gcloud run deploy --source` (Task 7) — registrar isso e seguir.

- [ ] **Step 4: Commit**

```bash
git add docker/Dockerfile .dockerignore
git commit -m "feat: Dockerfile da API — uv, uvicorn, sem segredos na imagem"
```

---

### Task 7: Scripts de deploy

**Files:**
- Create: `infra/scripts/deploy_api.sh`, `infra/scripts/deploy_drift.sh`

- [ ] **Step 1: Criar `infra/scripts/deploy_api.sh`**:

```bash
#!/usr/bin/env bash
# Deploy da API pme-risk no Cloud Run (SPEC §5.2)
# Idempotente — pode rodar múltiplas vezes. Requer: gcloud autenticado + ADC.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?Defina GCP_PROJECT_ID}"
REGION="${RUN_REGION:-us-central1}"
SERVICE="${RUN_SERVICE:-pme-risk-api}"
SA="${RUN_SERVICE_ACCOUNT:?Defina RUN_SERVICE_ACCOUNT (ex: pme-risk-api@<proj>.iam.gserviceaccount.com)}"

# Papel mínimo para a API ler/escrever BigQuery (idempotente: falha silenciosa se já existe)
for ROLE in roles/bigquery.dataEditor roles/bigquery.jobUser; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA}" \
    --role="${ROLE}" >/dev/null 2>&1 || true
done

# Demo pública (PLANO §6, critério de pronto) — restringir antes de uso real
gcloud run deploy "${SERVICE}" \
  --source=. \
  --region="${REGION}" \
  --service-account="${SA}" \
  --set-env-vars="BQ_DATASET=${BQ_DATASET:-pme_risk}" \
  --min-instances=0 \
  --max-instances=1 \
  --allow-unauthenticated
```

- [ ] **Step 2: Criar `infra/scripts/deploy_drift.sh`**:

```bash
#!/usr/bin/env bash
# Deploy do job de drift: Cloud Run Job + Cloud Scheduler semanal (SPEC §5.3)
# Idempotente — cria ou atualiza. Cron: segundas 12:00 UTC.
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?Defina GCP_PROJECT_ID}"
REGION="${RUN_REGION:-us-central1}"
JOB="${DRIFT_JOB_NAME:-pme-risk-drift}"
SA="${RUN_SERVICE_ACCOUNT:?Defina RUN_SERVICE_ACCOUNT}"
DATASET="${BQ_DATASET:-pme_risk}"
SCHED="${DRIFT_SCHEDULER_NAME:-pme-risk-drift-weekly}"
SCHEDULE="0 12 * * 1"
JOB_URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB}:run"

gcloud run jobs create "${JOB}" \
  --source=. \
  --region="${REGION}" \
  --service-account="${SA}" \
  --set-env-vars="BQ_DATASET=${DATASET}" \
  --command="python" \
  --args="monitoring/drift_job.py" \
  --max-retries=1 2>/dev/null || \
gcloud run jobs update "${JOB}" \
  --source=. \
  --region="${REGION}" \
  --service-account="${SA}" \
  --set-env-vars="BQ_DATASET=${DATASET}" \
  --command="python" \
  --args="monitoring/drift_job.py"

# Scheduler precisa invocar o job em nome da service account
for ROLE in roles/bigquery.dataViewer roles/bigquery.jobUser roles/cloudrun.invoker; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA}" \
    --role="${ROLE}" >/dev/null 2>&1 || true
done

gcloud scheduler jobs create http "${SCHED}" \
  --location="${REGION}" \
  --schedule="${SCHEDULE}" \
  --uri="${JOB_URI}" \
  --oauth-service-account-email="${SA}" 2>/dev/null || \
gcloud scheduler jobs update http "${SCHED}" \
  --location="${REGION}" \
  --schedule="${SCHEDULE}" \
  --uri="${JOB_URI}" \
  --oauth-service-account-email="${SA}"
```

- [ ] **Step 3: Verificar sintaxe bash**

Run: `bash -n infra/scripts/deploy_api.sh && bash -n infra/scripts/deploy_drift.sh`
Expected: sem saída (syntax OK)

- [ ] **Step 4: Commit**

```bash
git add infra/scripts/deploy_api.sh infra/scripts/deploy_drift.sh
git commit -m "feat: scripts de deploy — Cloud Run API, job de drift e scheduler"
```

---

### Task 8: Teste de integração + verificação final

**Files:**
- Create: `tests/integration/test_pipeline_e2e.py`

- [ ] **Step 1: Write the integration test (skipped sem GCP)**

```python
"""Teste de integração — pipeline real, exige ADC + GCP_PROJECT_ID.

Run: GCP_PROJECT_ID=<projeto> uv run pytest tests/integration -v
Custa chamadas Gemini + BigQuery — rodar com parcimônia (PLANO §7).
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("GCP_PROJECT_ID"), reason="GCP_PROJECT_ID não definido"
)

TEXTO_PEDIDO = (
    "Clínica odontológica em São Paulo, ME, com 5 anos de operação, "
    "faturamento anual de R$ 2.000.000, solicita R$ 300.000 para expansão."
)


def test_gerar_laudo_ponta_a_ponta() -> None:
    from api.pipeline import LaudoCriado, Pipeline

    pipeline = Pipeline(
        os.environ["GCP_PROJECT_ID"],
        os.environ.get("BQ_DATASET", "pme_risk"),
    )
    resultado = pipeline.gerar(TEXTO_PEDIDO)
    assert isinstance(resultado, LaudoCriado)
    row = pipeline.obter(resultado.laudo_id)
    assert row is not None and row["status"] == "pendente"
```

- [ ] **Step 2: Rodar suíte completa (unit) + ruff**

Run: `uv run pytest tests/unit -v && uv run ruff check .`
Expected: todos passed, ruff limpo

- [ ] **Step 3: Rodar integração (se ADC disponível)**

Run: `$env:GCP_PROJECT_ID="<projeto>"; uv run pytest tests/integration -v` (PowerShell)
Expected: 1 passed (ou SKIPPED sem credenciais — deixar para o momento do deploy)

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_pipeline_e2e.py
git commit -m "test: integração ponta a ponta do pipeline (skip sem GCP_PROJECT_ID)"
```

---

## Verificação final (critério de pronto do spec)

- [ ] `uv run pytest tests/unit` — tudo passa sem GCP
- [ ] `uv run ruff check .` — limpo
- [ ] `uvicorn api.main:app` sobe e `GET /healthz` responde `{"status":"ok"}`
- [ ] Nenhum arquivo da Fase 2 modificado: `git diff --name-only main..HEAD` não contém `agents/`, `api/routes/portao_humano.py`, `api/auditoria.py`, `tests/unit/test_schemas.py`, `README.md`
- [ ] Deploy real (`deploy_api.sh`) fica como passo manual do desenvolvedor — exige `gcloud` autenticado e service account criada no console

## Riscos conhecidos

- `TestClient` exige `httpx` em dev deps (Task 3 adiciona)
- Paridade Python ↔ `FARM_FINGERPRINT` não é garantida — aceitável: o mapeamento setor→occupation já é aproximação (SPEC §3.2)
- Drift compara escalas diferentes (pedido PME em BRL vs Home Credit) — PSI alto é sinal honesto do limite do mapeamento, documentado no módulo

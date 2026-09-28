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

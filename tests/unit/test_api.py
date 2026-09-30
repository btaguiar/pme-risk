"""Testes das rotas da API com pipeline falso — sem GCP."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.pipeline import LaudoCriado, Recusa, get_pipeline
from api.routes.portao_humano import LaudoJaDecididoError

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

PEDIDO = {"texto": "clínica odontológica quer crédito", "prazo_meses": 24}


class FakePipeline:
    def __init__(self) -> None:
        self.laudos: dict[str, dict] = {}
        self.recusa: Recusa | None = None
        self.prazos: list[int | None] = []
        self.pedidos_hoje = 0

    def gerar(self, texto: str, prazo_meses: int | None = None) -> LaudoCriado | Recusa:
        self.prazos.append(prazo_meses)
        if self.recusa is not None:
            return self.recusa
        laudo_id = "id-1"
        self.laudos[laudo_id] = {**_ROW}
        return LaudoCriado(laudo_id=laudo_id)

    def obter(self, laudo_id: str) -> dict | None:
        return self.laudos.get(laudo_id)

    def contar_pedidos_hoje(self) -> int:
        return self.pedidos_hoje

    def listar(self, limite: int = 20) -> list[dict]:
        rows = sorted(self.laudos.values(), key=lambda r: r.get("criado_em") or "", reverse=True)
        return rows[:limite]

    def decidir(self, laudo_id, decisao, decidido_por, observacao=None):
        row = self.laudos.get(laudo_id)
        if row is None:
            return None
        if row["status"] != "pendente":
            raise LaudoJaDecididoError(laudo_id, row["status"])
        row.update(status=decisao, decidido_por=decidido_por, observacao_humana=observacao)
        return row


@pytest.fixture
def client() -> Iterator[tuple[TestClient, FakePipeline]]:
    from api import limites

    limites.POR_IP.zerar()
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

    def test_health_200_cloud_run(self, client):
        response, _ = client
        assert response.get("/health").json() == {"status": "ok"}


class TestPostLaudos:
    def test_cria_laudo_201(self, client):
        response, fake = client
        r = response.post("/laudos", json=PEDIDO)
        assert r.status_code == 201
        body = r.json()
        assert body["laudo_id"] == "id-1"
        assert body["status"] == "pendente"
        assert fake.laudos["id-1"]["status"] == "pendente"

    def test_recusa_422(self, client):
        response, fake = client
        fake.recusa = Recusa(motivo="pessoa física")
        r = response.post("/laudos", json={"texto": "quero empréstimo pessoal", "prazo_meses": 12})
        assert r.status_code == 422
        assert r.json()["detail"] == {"motivo_recusa": "pessoa física"}

    def test_texto_curto_422(self, client):
        response, _ = client
        r = response.post("/laudos", json={"texto": "curto", "prazo_meses": 12})
        assert r.status_code == 422

    def test_prazo_repassado_ao_pipeline(self, client):
        response, fake = client
        response.post("/laudos", json=PEDIDO)
        assert fake.prazos == [24]

    @pytest.mark.parametrize("prazo", [None, 0, 121])
    def test_prazo_obrigatorio_entre_1_e_120(self, client, prazo):
        response, fake = client
        corpo = {"texto": PEDIDO["texto"]}
        if prazo is not None:
            corpo["prazo_meses"] = prazo
        r = response.post("/laudos", json=corpo)
        assert r.status_code == 422
        assert fake.laudos == {}


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


class TestLlmIndisponivel:
    def test_cota_gemini_esgotada_vira_503(self, client):
        from google.genai import errors as genai_errors

        response, fake = client

        def gerar(texto: str, prazo_meses: int | None = None):
            raise genai_errors.ClientError(
                429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "x"}}
            )

        fake.gerar = gerar
        r = response.post("/laudos", json=PEDIDO)
        assert r.status_code == 503
        assert r.headers["Retry-After"] == "30"

    def test_resposta_fora_do_schema_vira_502(self, client):
        from agents.gemini import RespostaInvalidaError

        response, fake = client

        def gerar(texto: str, prazo_meses: int | None = None):
            raise RespostaInvalidaError("vazia")

        fake.gerar = gerar
        r = response.post("/laudos", json=PEDIDO)
        assert r.status_code == 502


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

    def test_redecisao_409(self, client):
        response, fake = client
        fake.gerar("clínica odontológica quer crédito de expansão")
        body = {"decisao": "aprovado", "decidido_por": "analista-1"}
        assert response.patch("/laudos/id-1/decisao", json=body).status_code == 200
        r = response.patch(
            "/laudos/id-1/decisao",
            json={"decisao": "rejeitado", "decidido_por": "outra-pessoa"},
        )
        assert r.status_code == 409
        assert fake.laudos["id-1"]["status"] == "aprovado"

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


class TestApiKey:
    """POST /laudos exige X-API-Key quando API_KEY_SECRET está definido (demo pública)."""

    def test_sem_env_endereco_aberto(self, client, monkeypatch):
        monkeypatch.delenv("API_KEY_SECRET", raising=False)
        response, _ = client
        r = response.post("/laudos", json=PEDIDO)
        assert r.status_code == 201

    def test_com_env_sem_key_401(self, client, monkeypatch):
        monkeypatch.setenv("API_KEY_SECRET", "s3gredo-demo")
        response, _ = client
        r = response.post("/laudos", json=PEDIDO)
        assert r.status_code == 401

    def test_com_env_key_errada_401(self, client, monkeypatch):
        monkeypatch.setenv("API_KEY_SECRET", "s3gredo-demo")
        response, _ = client
        r = response.post(
            "/laudos",
            json=PEDIDO,
            headers={"X-API-Key": "errada"},
        )
        assert r.status_code == 401

    def test_com_env_key_certa_201(self, client, monkeypatch):
        monkeypatch.setenv("API_KEY_SECRET", "s3gredo-demo")
        response, fake = client
        r = response.post(
            "/laudos",
            json=PEDIDO,
            headers={"X-API-Key": "s3gredo-demo"},
        )
        assert r.status_code == 201
        assert fake.laudos["id-1"]["status"] == "pendente"

    def test_get_continua_aberto_com_env(self, client, monkeypatch):
        monkeypatch.setenv("API_KEY_SECRET", "s3gredo-demo")
        response, fake = client
        fake.gerar("clínica odontológica quer crédito de expansão")
        r = response.get("/laudos/id-1")
        assert r.status_code == 200


class TestDemoAberta:
    """CRIACAO_PUBLICA=1: cria sem chave dentro dos limites; só analista decide."""

    @pytest.fixture(autouse=True)
    def _env(self, monkeypatch):
        monkeypatch.setenv("API_KEY_SECRET", "s3gredo-demo")
        monkeypatch.setenv("CRIACAO_PUBLICA", "1")
        monkeypatch.setenv("LIMITE_POR_IP_DIA", "2")
        monkeypatch.setenv("LIMITE_GLOBAL_DIA", "5")

    def test_cria_sem_chave(self, client):
        response, _ = client
        assert response.post("/laudos", json=PEDIDO).status_code == 201

    def test_limite_por_ip_429_com_retry_after(self, client):
        response, _ = client
        ip = {"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}
        assert response.post("/laudos", json=PEDIDO, headers=ip).status_code == 201
        assert response.post("/laudos", json=PEDIDO, headers=ip).status_code == 201
        r = response.post("/laudos", json=PEDIDO, headers=ip)
        assert r.status_code == 429
        assert int(r.headers["Retry-After"]) > 0
        # outro IP ainda cabe
        outro = {"X-Forwarded-For": "198.51.100.9"}
        assert response.post("/laudos", json=PEDIDO, headers=outro).status_code == 201

    def test_pedido_invalido_nao_gasta_cota(self, client):
        response, _ = client
        ip = {"X-Forwarded-For": "203.0.113.50"}
        for _ in range(5):
            assert response.post("/laudos", json={"texto": "x"}, headers=ip).status_code == 422
        assert response.post("/laudos", json=PEDIDO, headers=ip).status_code == 201

    def test_teto_global_429(self, client):
        response, fake = client
        fake.pedidos_hoje = 5
        r = response.post("/laudos", json=PEDIDO)
        assert r.status_code == 429
        assert "limite diário" in r.json()["detail"]

    def test_chave_de_analista_ignora_limites(self, client):
        response, fake = client
        fake.pedidos_hoje = 999
        r = response.post("/laudos", json=PEDIDO, headers={"X-API-Key": "s3gredo-demo"})
        assert r.status_code == 201

    def test_chave_errada_e_401_nao_cai_no_limite(self, client):
        response, _ = client
        r = response.post("/laudos", json=PEDIDO, headers={"X-API-Key": "errada"})
        assert r.status_code == 401

    def test_decisao_sem_chave_401(self, client):
        response, fake = client
        fake.gerar("clínica odontológica quer crédito de expansão")
        body = {"decisao": "aprovado", "decidido_por": "visitante"}
        r = response.patch("/laudos/id-1/decisao", json=body)
        assert r.status_code == 401
        assert fake.laudos["id-1"]["status"] == "pendente"

    def test_decisao_com_chave_200(self, client):
        response, fake = client
        fake.gerar("clínica odontológica quer crédito de expansão")
        body = {"decisao": "aprovado", "decidido_por": "analista-1"}
        r = response.patch("/laudos/id-1/decisao", json=body, headers={"X-API-Key": "s3gredo-demo"})
        assert r.status_code == 200


class TestListarLaudos:
    def test_lista_vazia(self, client):
        response, _ = client
        r = response.get("/laudos")
        assert r.status_code == 200
        assert r.json() == []

    def test_lista_com_resumo(self, client):
        response, fake = client
        fake.gerar("clínica odontológica quer crédito de expansão")
        r = response.get("/laudos")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        item = body[0]
        assert item["laudo_id"] == "id-1"
        assert item["status"] == "pendente"
        assert item["pd"] == 0.07
        assert item["faixa_risco"] == "medio"
        assert item["pedido"]["porte"] == "ME"
        assert "texto" not in item

    def test_respeita_limite(self, client):
        response, fake = client
        for i in range(3):
            fake.gerar(f"pedido numero {i}")
            fake.laudos[f"id-{i}"] = {**_ROW, "laudo_id": f"id-{i}"}
        r = response.get("/laudos?limite=2")
        assert r.status_code == 200
        assert len(r.json()) == 2


class TestFrontend:
    """Navegador recebe a casca do SPA; cliente de API recebe JSON.

    URLs de página são reais (/laudos, /laudos/{id}) para serem compartilháveis —
    a negociação de conteúdo decide HTML vs JSON pelo header Accept.
    """

    HTML = {"Accept": "text/html,application/xhtml+xml"}

    @pytest.fixture(autouse=True)
    def dist_falso(self, tmp_path, monkeypatch):
        """Build do Vite simulado — os testes não dependem de Node."""
        dist = tmp_path / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<title>Aval · pme-risk</title>", encoding="utf-8")
        (dist / "assets" / "index-abc.js").write_text("console.log(1)", encoding="utf-8")
        (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
        (tmp_path / "segredo.txt").write_text("nao deve vazar", encoding="utf-8")
        monkeypatch.setattr("api.frontend.DIST_DIR", dist.resolve())

    def test_index_html_servido(self, client):
        response, _ = client
        r = response.get("/")
        assert r.status_code == 200
        assert "pme-risk" in r.text
        assert "text/html" in r.headers["content-type"]

    def test_assets_estaticos(self, client):
        response, _ = client
        assert response.get("/assets/index-abc.js").status_code == 200

    def test_rota_do_spa_devolve_casca(self, client):
        response, _ = client
        r = response.get("/novo", headers=self.HTML)
        assert r.status_code == 200
        assert "pme-risk" in r.text

    def test_path_traversal_nao_sai_do_dist(self, client):
        response, _ = client
        r = response.get("/..%2Fsegredo.txt")
        assert "nao deve vazar" not in r.text

    def test_lista_html_para_navegador(self, client):
        response, _ = client
        r = response.get("/laudos", headers=self.HTML)
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "pme-risk" in r.text

    def test_laudo_html_para_navegador_mesmo_inexistente(self, client):
        response, _ = client
        r = response.get("/laudos/qualquer-id", headers=self.HTML)
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "pme-risk" in r.text

    def test_casca_varia_por_accept(self, client):
        """Sem Vary: Accept, o cache do navegador serve HTML ao fetch() que pede JSON."""
        response, _ = client
        r = response.get("/laudos/qualquer-id", headers=self.HTML)
        assert "accept" in r.headers["vary"].lower()

    def test_barra_final_nao_e_mais_404(self, client):
        response, _ = client
        r = response.get("/laudos/", headers=self.HTML)
        assert r.status_code == 200
        assert "pme-risk" in r.text

    def test_json_continua_json(self, client):
        response, fake = client
        fake.gerar("clínica odontológica quer crédito de expansão")
        r = response.get("/laudos", headers={"Accept": "application/json"})
        assert r.headers["content-type"].startswith("application/json")
        r2 = response.get("/laudos/id-1", headers={"Accept": "application/json"})
        assert r2.json()["laudo_id"] == "id-1"

    def test_favicon_svg(self, client):
        response, _ = client
        assert response.get("/favicon.svg").status_code == 200

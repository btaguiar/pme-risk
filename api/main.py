"""API pme-risk — SPEC §5.1."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from api import frontend
from api.routes import decisao, laudos

app = FastAPI(
    title="pme-risk",
    description="Laudo de risco de crédito PME, auditável",
    version="0.1.0",
)
app.include_router(laudos.router)
app.include_router(decisao.router)


# Cloud Run reserva caminhos terminados em "z" (/healthz dá 404 no front-end do
# Google) — /health é o que funciona lá; /healthz fica para uso local.
@app.get("/health")
@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}

# Frontend (Vite → frontend/dist): assets estáticos e fallback do SPA por caminho.
# Rotas da API (acima) sempre vencem; o catch-all devolve index.html para
# navegação de página (/novo, /laudos, /laudos/{id}) — URLs compartilháveis.
@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    alvo = frontend.arquivo_estatico(full_path)
    if alvo is not None:
        return FileResponse(alvo)
    if frontend.index().is_file():
        return frontend.casca_spa()
    raise HTTPException(status_code=404, detail="Not Found")

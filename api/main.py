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


# Cloud Run reserva caminhos terminados em "z" (/healthz dá 404 no front-end do
# Google) — /health é o que funciona lá; /healthz fica para uso local.
@app.get("/health")
@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}

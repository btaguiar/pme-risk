"""Casca do SPA (frontend/dist, gerado pelo Vite) e negociação HTML × JSON.

URLs de página são reais (/laudos, /laudos/{id}) para serem compartilháveis:
navegador (Accept: text/html) recebe index.html; cliente de API recebe JSON.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse

DIST_DIR = Path(
    os.environ.get("FRONTEND_DIST")
    or Path(__file__).resolve().parent.parent / "frontend" / "dist"
).resolve()


def quer_html(request: Request) -> bool:
    accept = request.headers.get("accept") or ""
    return "text/html" in accept and "application/json" not in accept


def index() -> Path:
    return DIST_DIR / "index.html"


def casca_spa() -> FileResponse:
    # Vary: Accept — mesma URL serve HTML e JSON; sem isso o cache do navegador
    # devolve a casca HTML ao fetch() que pediu JSON.
    return FileResponse(
        index(),
        media_type="text/html",
        headers={"Vary": "Accept", "Cache-Control": "no-cache"},
    )


def arquivo_estatico(caminho: str) -> Path | None:
    """Arquivo dentro de DIST_DIR — nunca fora dele (bloqueia ../)."""
    if not caminho:
        return None
    alvo = (DIST_DIR / caminho).resolve()
    if not alvo.is_relative_to(DIST_DIR) or not alvo.is_file():
        return None
    return alvo

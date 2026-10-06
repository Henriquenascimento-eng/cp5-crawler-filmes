"""
API — expõe os dados coletados (armazenados no MongoDB) via FastAPI.
É a única porta de entrada para o dashboard consumir os dados.
"""
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

sys.path.append(str(Path(__file__).resolve().parent.parent))
from banco_dados.mongo import (  # noqa: E402
    buscar_filtrado,
    buscar_por_id,
    contar_total,
    estatisticas,
    listar_filmes,
)

app = FastAPI(
    title="API — Maiores Bilheterias (Wikipédia)",
    description=(
        "API para consultar os dados coletados da lista de maiores "
        "bilheterias de filmes pelo Web Crawler do CP5."
    ),
    version="1.0.0",
)

# Libera acesso para o dashboard (Streamlit, rodando em outra porta) consumir a API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def raiz():
    return {"mensagem": "API do CP5 no ar. Veja /docs para a documentação interativa."}


@app.get("/filmes")
def endpoint_listar_filmes(
    skip: int = Query(0, ge=0, description="Quantos registros pular (paginação)"),
    limit: int = Query(50, ge=1, le=250, description="Quantos registros retornar"),
):
    """Lista os registros, com paginação."""
    return {"total": contar_total(), "filmes": listar_filmes(skip=skip, limit=limit)}


@app.get("/filmes/buscar")
def endpoint_buscar(
    genero: Optional[str] = Query(None, description="Filtra por gênero, ex: action"),
    ano: Optional[int] = Query(None, description="Filtra por ano de lançamento"),
):
    """Filtro/busca por gênero e/ou ano."""
    resultados = buscar_filtrado(genero=genero, ano=ano)
    return {"quantidade": len(resultados), "filmes": resultados}


@app.get("/filmes/{wiki_id}")
def endpoint_filme_por_id(wiki_id: str):
    """Consulta um registro específico pelo id da Wikipédia (ex: Avatar_(2009_film))."""
    filme = buscar_por_id(wiki_id)
    if not filme:
        raise HTTPException(status_code=404, detail="Filme não encontrado")
    return filme


@app.get("/estatisticas")
def endpoint_estatisticas():
    """Informações estatísticas sobre os dados coletados."""
    return estatisticas()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

"""
Módulo de persistência — conexão com MongoDB Atlas e operações
sobre a coleção de filmes.

Responsabilidade única deste módulo: falar com o banco de dados.
Nem o crawler, nem a API, acessam o MongoDB diretamente — sempre
passam por aqui.
"""
import os
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING
from pymongo.collection import Collection

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB = os.getenv("MONGODB_DB", "cp5_filmes")
COLLECTION_NAME = "filmes"

_client: Optional[MongoClient] = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        if not MONGODB_URI:
            raise RuntimeError(
                "MONGODB_URI não configurada. Copie .env.example para .env "
                "e preencha com a string de conexão do MongoDB Atlas."
            )
        _client = MongoClient(MONGODB_URI)
    return _client


def get_collection() -> Collection:
    db = get_client()[MONGODB_DB]
    colecao = db[COLLECTION_NAME]
    # Índice único por wiki_id: garante que o mesmo filme nunca seja duplicado,
    # mesmo que o crawler rode várias vezes.
    colecao.create_index([("wiki_id", ASCENDING)], unique=True)
    return colecao


def upsert_filme(dados: dict) -> None:
    """
    Insere um filme novo ou atualiza um já existente (identificado por
    wiki_id — o nome do artigo na Wikipédia). Preserva a data da primeira
    coleta e mantém um pequeno histórico de bilheteria/posição a cada nova
    coleta, sem apagar dados anteriores nem criar registros duplicados.
    """
    colecao = get_collection()
    agora = datetime.now(timezone.utc).isoformat()

    existente = colecao.find_one({"wiki_id": dados["wiki_id"]})

    entrada_historico = {
        "coletado_em": agora,
        "bilheteria_mundial": dados.get("bilheteria_mundial"),
        "posicao_ranking": dados.get("posicao_ranking"),
    }

    if existente:
        historico = existente.get("historico", [])
        historico.append(entrada_historico)
        colecao.update_one(
            {"wiki_id": dados["wiki_id"]},
            {"$set": {**dados, "ultima_coleta": agora, "historico": historico}},
        )
    else:
        colecao.insert_one(
            {
                **dados,
                "primeira_coleta": agora,
                "ultima_coleta": agora,
                "historico": [entrada_historico],
            }
        )


def listar_filmes(skip: int = 0, limit: int = 50) -> list:
    colecao = get_collection()
    return list(
        colecao.find({}, {"_id": 0})
        .sort("posicao_ranking", ASCENDING)
        .skip(skip)
        .limit(limit)
    )


def buscar_por_id(wiki_id: str) -> Optional[dict]:
    colecao = get_collection()
    return colecao.find_one({"wiki_id": wiki_id}, {"_id": 0})


def buscar_filtrado(genero: Optional[str] = None, ano: Optional[int] = None) -> list:
    colecao = get_collection()
    filtro = {}
    if genero:
        filtro["generos"] = {"$regex": genero, "$options": "i"}
    if ano:
        filtro["ano"] = ano
    return list(colecao.find(filtro, {"_id": 0}).sort("posicao_ranking", ASCENDING))


def contar_total() -> int:
    return get_collection().count_documents({})


def estatisticas() -> dict:
    colecao = get_collection()
    total = colecao.count_documents({})
    if total == 0:
        return {"total_filmes": 0}

    pipeline = [
        {
            "$group": {
                "_id": None,
                "bilheteria_media": {"$avg": "$bilheteria_mundial"},
                "duracao_media": {"$avg": "$duracao_min"},
                "ano_mais_antigo": {"$min": "$ano"},
                "ano_mais_recente": {"$max": "$ano"},
            }
        }
    ]
    agregados = list(colecao.aggregate(pipeline))[0]

    pipeline_generos = [
        {"$unwind": "$generos"},
        {"$group": {"_id": "$generos", "quantidade": {"$sum": 1}}},
        {"$sort": {"quantidade": -1}},
    ]
    generos = list(colecao.aggregate(pipeline_generos))

    return {
        "total_filmes": total,
        "bilheteria_media": round(agregados["bilheteria_media"] or 0, 2),
        "duracao_media_min": round(agregados["duracao_media"] or 0, 1),
        "ano_mais_antigo": agregados["ano_mais_antigo"],
        "ano_mais_recente": agregados["ano_mais_recente"],
        "distribuicao_generos": [
            {"genero": g["_id"], "quantidade": g["quantidade"]} for g in generos
        ],
    }

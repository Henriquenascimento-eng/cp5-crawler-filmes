"""
Web Crawler — coleta os dados da lista "List of highest-grossing films"
da Wikipédia e armazena no MongoDB. Roda de forma totalmente independente
da API: pode ser executado quantas vezes quiser sem que a API precise
estar no ar.

Por que Wikipédia e não IMDb: o IMDb tem proteção anti-bot que bloqueia
requisições simples (retorna respostas vazias). A Wikipédia não tem esse
bloqueio e tem uma tabela pronta e bem estruturada sobre bilheteria de
filmes.

Estratégia de coleta:
1. Acessa a página da lista e extrai, da primeira tabela grande
   ("Highest-grossing films"), o título, ano e bilheteria mundial de
   cada filme, junto com o link para a página individual dele.
2. Para cada filme, acessa a própria página na Wikipédia e extrai, da
   infobox (a caixa de informações no canto superior direito de todo
   artigo sobre filme), o diretor e a duração. O(s) gênero(s) são
   inferidos a partir das categorias do artigo (ex: categoria
   "2026 science fiction films" → gênero "science fiction").
"""
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.append(str(Path(__file__).resolve().parent.parent))
from banco_dados.mongo import upsert_filme  # noqa: E402

BASE_URL = "https://en.wikipedia.org"
LISTA_URL = f"{BASE_URL}/wiki/List_of_highest-grossing_films"

# A Wikipédia pede que bots/scripts se identifiquem com um User-Agent
# descritivo (politica de uso da API/scraping da Wikimedia).
HEADERS = {
    "User-Agent": "CP5-FIAP-EducationalCrawler/1.0 (projeto academico; sem fins comerciais)"
}
DELAY_ENTRE_REQUISICOES = 1.0  # segundos — evita sobrecarregar o site

# Palavras-chave usadas para reconhecer gênero dentro das categorias do
# artigo (ex: a categoria "British science fiction films" vira "science
# fiction").
GENEROS_CONHECIDOS = [
    "science fiction", "superhero", "action", "adventure", "animated",
    "comedy", "drama", "fantasy", "horror", "musical", "mystery",
    "romance", "romantic comedy", "thriller", "war", "western", "crime",
    "family", "disaster", "spy",
]


def _limpar_numero(texto: str) -> str:
    """Remove tudo que não é dígito de uma string (sobra de notas de rodapé etc.)."""
    return re.sub(r"[^\d]", "", texto or "")


def coletar_lista() -> list:
    """
    Acessa a página da lista e retorna uma lista de dicionários com:
    posicao_ranking, titulo, ano, bilheteria_mundial, url
    """
    resp = requests.get(LISTA_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    # A tabela que queremos é a primeira "wikitable" cujo cabeçalho
    # contém "Worldwide gross" — assim não dependemos da posição exata
    # da tabela na página, só do conteúdo do cabeçalho.
    tabela = None
    for t in soup.find_all("table", {"class": "wikitable"}):
        cabecalho = t.find("tr")
        if cabecalho and "Worldwide gross" in cabecalho.get_text():
            tabela = t
            break

    if tabela is None:
        raise RuntimeError(
            "Não encontrei a tabela de bilheteria — a estrutura da página "
            "pode ter mudado. Abra a página manualmente e confira o HTML."
        )

    filmes = []
    linhas = tabela.find_all("tr")[1:]  # pula o cabeçalho
    print(f"DEBUG: {len(linhas)} linhas encontradas na tabela")

    for i, linha in enumerate(linhas):
        celulas = linha.find_all(["td", "th"])

        # Remove notas de rodapé (<sup>) antes de extrair texto, pra não
        # misturar números de referência com os dados.
        for sup in linha.find_all("sup"):
            sup.decompose()

        if len(celulas) < 5:
            if i < 5:
                print(f"DEBUG linha {i}: só {len(celulas)} células, pulando. "
                      f"Conteúdo bruto: {linha.get_text(' | ', strip=True)[:150]}")
            continue

        rank_texto = _limpar_numero(celulas[0].get_text())
        titulo_celula = celulas[2]
        link = titulo_celula.find("a")

        href = link.get("href", "") if link else ""
        if not link or "/wiki/" not in href:
            if i < 5:
                print(f"DEBUG linha {i}: sem link válido na célula de título. "
                      f"Célula 2 bruta: {titulo_celula.get_text(strip=True)[:80]!r} "
                      f"| link encontrado: {href or None}")
            continue

        titulo = link.get_text(strip=True)
        # O link pode vir absoluto (https://en.wikipedia.org/wiki/...) ou
        # relativo (/wiki/...) — tratamos os dois casos.
        url = href if href.startswith("http") else BASE_URL + href
        bilheteria_texto = _limpar_numero(celulas[3].get_text())
        ano_texto = _limpar_numero(celulas[4].get_text())

        if not (rank_texto and bilheteria_texto and ano_texto):
            if i < 5:
                print(f"DEBUG linha {i}: campo vazio. rank={rank_texto!r} "
                      f"bilheteria={bilheteria_texto!r} ano={ano_texto!r}")
            continue

        filmes.append(
            {
                "posicao_ranking": int(rank_texto),
                "titulo": titulo,
                "ano": int(ano_texto[:4]),  # alguns anos vêm com nota colada
                "bilheteria_mundial": int(bilheteria_texto),
                "url": url,
            }
        )

    if not filmes:
        raise RuntimeError(
            "A tabela foi encontrada, mas nenhuma linha pôde ser lida — "
            "confira as mensagens DEBUG acima."
        )
    return filmes


def _extrair_generos(soup: BeautifulSoup) -> list:
    """Procura nas categorias do artigo por palavras-chave de gênero conhecidas."""
    generos_encontrados = set()
    catlinks = soup.find("div", {"id": "catlinks"})
    if not catlinks:
        return []

    for link in catlinks.find_all("a"):
        texto = link.get_text(strip=True).lower()
        for genero in GENEROS_CONHECIDOS:
            if genero in texto:
                generos_encontrados.add(genero)

    return sorted(generos_encontrados)


def _extrair_duracao(texto: str):
    """Converte algo como '162 minutes' em 162 (inteiro)."""
    match = re.search(r"(\d+)\s*minutes?", texto)
    return int(match.group(1)) if match else None


def coletar_detalhes(url: str) -> dict:
    """Acessa a página individual do filme e extrai diretor, duração e gêneros."""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    diretor = None
    duracao_min = None

    infobox = soup.find("table", {"class": "infobox"})
    if infobox:
        for linha in infobox.find_all("tr"):
            rotulo = linha.find("th")
            valor = linha.find("td")
            if not rotulo or not valor:
                continue

            # remove notas de rodapé antes de ler o texto
            for sup in valor.find_all("sup"):
                sup.decompose()

            rotulo_texto = rotulo.get_text(strip=True).lower()
            if "directed by" in rotulo_texto and not diretor:
                diretor = valor.get_text(separator=", ", strip=True)
            elif "running time" in rotulo_texto and not duracao_min:
                duracao_min = _extrair_duracao(valor.get_text())

    return {
        "diretor": diretor,
        "duracao_min": duracao_min,
        "generos": _extrair_generos(soup),
    }


def executar_coleta(limite: int = None) -> int:
    """
    Executa uma coleta completa. Use `limite` para testar com poucos
    filmes antes de rodar a lista inteira (50 filmes).
    """
    print("Acessando a lista de maiores bilheterias na Wikipédia...")
    lista = coletar_lista()
    if limite:
        lista = lista[:limite]

    total_coletado = 0
    for item in lista:
        try:
            print(f"[{item['posicao_ranking']}] Coletando: {item['titulo']}")
            detalhes = coletar_detalhes(item["url"])
            wiki_id = item["url"].rsplit("/wiki/", 1)[-1]

            dados = {
                "wiki_id": wiki_id,
                "titulo": item["titulo"],
                "url": item["url"],
                "ano": item["ano"],
                "bilheteria_mundial": item["bilheteria_mundial"],
                "posicao_ranking": item["posicao_ranking"],
                "diretor": detalhes["diretor"],
                "duracao_min": detalhes["duracao_min"],
                "generos": detalhes["generos"],
                "fonte": LISTA_URL,
            }
            upsert_filme(dados)
            total_coletado += 1
        except Exception as exc:
            print(f"  -> Erro ao coletar '{item['titulo']}': {exc}")
        time.sleep(DELAY_ENTRE_REQUISICOES)

    print(f"Coleta finalizada. {total_coletado} filmes processados.")
    return total_coletado


if __name__ == "__main__":
    # Para testar rápido: python crawler_wiki.py 5  (coleta só 5 filmes)
    limite_teste = int(sys.argv[1]) if len(sys.argv) > 1 else None
    executar_coleta(limite=limite_teste)
# CP5 — Web Crawler, API e Dashboard: Maiores Bilheterias (Wikipédia)

Sistema que coleta os dados da lista de **maiores bilheterias de filmes**
da Wikipédia, armazena no **MongoDB Atlas**, disponibiliza por uma
**API em FastAPI** e apresenta tudo em um **painel (dashboard) em Streamlit**.

Fluxo: `Wikipédia → coleta/ → banco_dados/ → api/ → painel/`

# Integrantes do Grupo
Andrey luigi rm569575 - 
Nicolas Moreira rm571510 -  
Lucas Trevisan rm569731 - 
Henrique da Silva rm569137 - 


## Site escolhido e dados coletados

- **Site:** Wikipédia — página *List of highest-grossing films*
  (`https://en.wikipedia.org/wiki/List_of_highest-grossing_films`).
- Trocamos o site original (IMDb) porque o IMDb tem proteção anti-bot
  que bloqueia requisições simples — a Wikipédia não tem esse problema.
- **Dados públicos**, sem informação pessoal: título, ano, bilheteria
  mundial, posição no ranking, diretor, duração e gênero(s).
- O crawler lê a tabela da página da lista para título/ano/bilheteria, e
  a infobox + categorias de cada página individual do filme para
  diretor/duração/gênero.

## Estrutura do projeto

```
cp5-pt/
├── coleta/
│   └── crawler_wiki.py      # Web Crawler — coleta os dados da Wikipédia
├── banco_dados/
│   └── mongo.py             # única camada que fala com o MongoDB
├── api/
│   └── main.py               # API em FastAPI — expõe os dados
├── painel/
│   └── app.py                 # Dashboard em Streamlit — consome a API
├── requirements.txt
├── .env.example
└── README.md
```

## Estrutura do banco de dados (MongoDB)

Banco: `cp5_filmes` — coleção: `filmes`. Um documento por filme
(chave única: `wiki_id`, o nome do artigo na Wikipédia, ex:
`Avatar_(2009_film)`), no formato:

```json
{
  "wiki_id": "Avatar_(2009_film)",
  "titulo": "Avatar",
  "url": "https://en.wikipedia.org/wiki/Avatar_(2009_film)",
  "ano": 2009,
  "bilheteria_mundial": 2923710708,
  "posicao_ranking": 1,
  "diretor": "James Cameron",
  "duracao_min": 162,
  "generos": ["science fiction", "action"],
  "fonte": "https://en.wikipedia.org/wiki/List_of_highest-grossing_films",
  "primeira_coleta": "2026-10-04T20:00:00+00:00",
  "ultima_coleta": "2026-10-05T09:00:00+00:00",
  "historico": [
    {"coletado_em": "2026-10-04T20:00:00+00:00", "bilheteria_mundial": 2923710708, "posicao_ranking": 1}
  ]
}
```

- `primeira_coleta` / `ultima_coleta` / `historico` identificam quando
  cada dado foi coletado.
- Rodar o crawler de novo **atualiza** o registro existente (pelo
  `wiki_id`) em vez de duplicar ou apagar dados anteriores.

## Instalação

```bash
cd cp5-pt
py -m pip install -r requirements.txt
```

Depois, copie o `.env.example` para `.env` e edite a variável
`MONGODB_URI` com a sua connection string do MongoDB Atlas.

## Configuração do MongoDB Atlas

1. Crie uma conta e um cluster gratuito em https://cloud.mongodb.com
2. Em **Database & Network Access** (seção "Security" na barra lateral):
   - Aba de usuários: crie um usuário e senha (só letras/números).
   - Aba de IP: libere `0.0.0.0/0` ("Allow Access from Anywhere").
3. Em **Database → Clusters**, clique em **Connect → Drivers → Python**
   e copie a connection string.
4. Cole no `.env`, trocando `<db_username>` e `<db_password>` pelos
   valores reais:
   ```
   MONGODB_URI=mongodb+srv://usuario:senha@cluster0.xxxxx.mongodb.net/?appName=Cluster0
   ```

## Execução

**1. Rodar o crawler** (pode testar com poucos filmes primeiro), a partir
da pasta raiz do projeto (`cp5-pt`):
```bash
python coleta/crawler_wiki.py 5      # coleta só 5 filmes, para testar
python coleta/crawler_wiki.py         # coleta os 50 filmes completos
```

**2. Subir a API:**
```bash
cd api
uvicorn main:app --reload
```
Documentação interativa em `http://localhost:8000/docs`.

**3. Subir o painel** (em outro terminal, com a API já rodando):
```bash
cd painel
streamlit run app.py
```

## Endpoints da API

| Método | Rota | Descrição |
|---|---|---|
| GET | `/filmes` | Lista os registros (params: `skip`, `limit`) |
| GET | `/filmes/buscar` | Filtra por `genero` e/ou `ano` |
| GET | `/filmes/{wiki_id}` | Retorna um filme específico |
| GET | `/estatisticas` | Total, bilheteria média, duração média, distribuição por gênero |

## Observações / limitações conhecidas

- Gêneros são inferidos a partir das categorias do artigo da Wikipédia
  (ex: categoria "British science fiction films" → gênero "science
  fiction"), já que a infobox de filme da Wikipédia não tem um campo
  de gênero explícito. Alguns filmes podem não ter gênero detectado se
  as categorias usarem termos fora da lista reconhecida pelo crawler
  (`GENEROS_CONHECIDOS` em `crawler_wiki.py`).
- A lista de maiores bilheterias muda pouco entre coletas (só quando um
  filme novo entra no top 50 ou a bilheteria de um filme em cartaz é
  atualizada) — coletas sucessivas tendem a atualizar mais os valores
  do que trazer filmes novos.
- Apenas dados públicos e não pessoais são coletados, conforme pedido
  no enunciado.

# Endpoints novos para o Sistema do Candidato

Para: equipe que mantém `eleicoes.55.com.vc` (servidor da API).

O app (`/candidato/index.html`) já usa as rotas que existem: `/api/meta`, `/api/governador/{estado|capital|interior}`, `/api/governador/candidato/{n}`, `/api/locais-votacao/{area}` e `/api/stream`. Faltam **dois endpoints**. Enquanto eles não existem (resposta 404), o app mostra um aviso e segue funcionando com o que já tem.

## 1. Votos por colégio (local de votação) — prioridade alta

Usado nas abas **Zonas, bairros e colégios** e **Colégios do Omar (1º × 2º turno)**.

```
GET /api/{cargo}/locais?turno={1|2}&area={capital|interior}
```

Resposta:

```json
{
  "turno": 2, "area": "capital", "geradoEm": "2026-10-25T19:41:58-04:00",
  "locais": [
    {
      "local": "1015",
      "zona": "0062", "codigo": "02550", "municipio": "MANAUS",
      "nome": "ESCOLA ESTADUAL …", "bairro": "CIDADE NOVA",
      "secoesTotal": 12, "secoesTotalizadas": 12,
      "aptos": 4100, "comparecimento": 3400,
      "validos": 3150, "brancos": 60, "nulos": 190,
      "candidatos": { "55": 1700, "22": 1450 }
    }
  ]
}
```

Regras:

- **Mesma chave do cadastro:** `zona` + `codigo` (município) + `nome`, iguais aos de `/api/locais-votacao/{area}`. É por essa chave que o app junta cadastro e votos. Se houver o número do local do TSE, mandar também em `local`.
- **Origem:** soma dos boletins de urna (BU) das seções de cada local. É o que a central já calcula nas tabelas `bu_leitura` e `secao_local`.
- **Sem dupla contagem:** seção agregada conta uma vez só (armadilha 16 do sistema).
- **Eleitorado do cargo:** usar votos e cadastro do cargo, não o cabeçalho do BU, que é o de Presidente (armadilha 15).
- **Conferência que o app faz:** a soma dos colégios de cada município tem de bater com os votos do candidato no município (`/api/{cargo}/candidato/{n}`). Divergência aparece como ✕ na validação.

## 2. Marcos da apuração — prioridade média

Usado na aba **Marcos da apuração**. Hoje cada aparelho registra os marcos só enquanto o app está aberto. Com este endpoint, a lista passa a ser a oficial do sistema, igual para todos.

```
GET /api/{cargo}/marcos?turno={1|2}
```

```json
{
  "turno": 2,
  "marcos": [
    { "id": "p50", "titulo": "50% das seções", "tse": "2026-10-25T17:39:00-04:00",
      "pct": 50.02, "eu": 51.2, "dif": 23110, "lider": "55" }
  ]
}
```

- `eu` = % do candidato acompanhado; `dif` = votos dele menos os do 2º colocado; `lider` = número de quem lidera.
- `eu` e `dif` são o que o pop-up de marcos da tela principal mostra; sem eles, o pop-up exibe só horário e andamento.
- Marcos mínimos: primeiros votos, 25%, 50%, 75%, 100%, troca de liderança, totalização finalizada.
- A central já registra marcos (tabela `marco`, 82 no 1º turno); o endpoint pode publicar essa tabela.

## Hospedagem e acesso

- O app precisa ficar **no mesmo domínio da API**, por exemplo `https://eleicoes.55.com.vc/candidato/`, porque a API não aceita chamadas de outra origem (CORS). Também funciona num subdomínio, desde que a API libere CORS só para ele.
- **Acesso restrito:** é material estratégico de campanha. Colocar `/candidato/` atrás de login no próprio servidor (autenticação básica ou login por e-mail) e não indexar.

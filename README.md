# Sistema do Candidato — Apuração AM 2026 (mobile)

App de uma página para acompanhar pelo celular a apuração do 2º turno de 25/10/2026 (Governador e Presidente) no Amazonas. Todo número vem do TSE, consolidado pela central de apuração da equipe (SESMT01).

**Link público:** `https://euammess.github.io/sistema-candidato-am/` · ensaio com o 1º turno real: acrescente `?turno=1`.

## Como funciona

```
 TSE ──► central SESMT01 (coletor + boletins de urna, banco SQLite)
              │  publicar_candidato.py  (a cada 3 min, só quando a versão muda)
              ▼
         ramo `site` deste repositório  ──►  GitHub Actions  ──►  GitHub Pages
                                                                  │
                                                     celular (qualquer rede)
```

- A central continua fechada na rede local. O que sai dela são **retratos**: arquivos JSON com os mesmos dados que a API local responde.
- O ramo `site` é reescrito a cada envio (um commit só) para o histórico não crescer na noite da eleição.
- Na rede da DMD o mesmo app também roda direto na central, ao vivo: `http://<ip-da-central>:8765/candidato/`.

## Estrutura

| Caminho | O que é |
|---|---|
| `candidato/index.html` | O app (v2.5.0). Na central lê `/api/...`; no Pages, o publicador liga o modo estático. |
| `central/api_candidato.py` | API do app na central: rotas `/api/meta`, `/api/{governador\|presidente}/{estado\|capital\|interior\|candidato/N\|locais\|marcos}`, `/api/locais-votacao/{area}`, `/api/brasil[/uf]`, `/api/stream`, `/fotos/`. |
| `central/publicar_candidato.py` | Gera o site estático e envia ao ramo `site`. |
| `central/calhas_cores_am.json` | Calha de rio de cada município e cores dos candidatos. |
| `docs/DOCUMENTACAO_COMPLETA.md` | Documentação original do app (abas, regras de dados, homologação). |
| `CONTRATO_API.md` · `CHANGELOG.md` | Formato dos endpoints e histórico de versões. |

Os arquivos de `central/` rodam dentro da pasta do sistema de apuração da central (dependem de `api_territorio.py`, `banco.py`, `coletor.py` e do banco).

## Operação na noite (25/10)

Na central: `python publicar_candidato.py loop --cada 180` (ou o atalho `14 - PUBLICAR SISTEMA DO CANDIDATO.bat`). A faixa do topo do app mostra o horário da totalização do TSE; o retrato chega ao celular em ~3–5 min.

## Regras de dados

Percentual sobre votos válidos · "Eleito" só quando o TSE informa · interior = Amazonas − Manaus, identificado como cálculo · zonas, bairros e colégios = soma dos boletins de urna · 1º e 2º turno nunca se misturam, exceto na aba comparativa · sem dado = "aguardando", nunca zero inventado.

Material de acompanhamento da campanha. Dados públicos do TSE; a página tem `noindex` e `robots.txt` bloqueando buscadores.

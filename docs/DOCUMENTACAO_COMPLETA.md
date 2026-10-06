# Sistema do Candidato — Apuração AM 2026 · Documentação completa

**Versão do app:** 2.4.0 (06/10/2026) · **Repositório:** privado · **Uso:** interno da campanha, não divulgar.

Este documento basta para instalar, operar, validar e evoluir o sistema numa máquina que **já roda a API de apuração** (backup do TSE e dos colégios). Ele não depende do computador de quem o criou.

---

## 1. O que é

Um app de uma página, feito para celular, que acompanha a apuração do 2º turno de 25/10/2026 (Governador e Presidente) para a coordenação da campanha. Ele lê a API do sistema de apuração (`/api`, hoje em `eleicoes.55.com.vc`), que consolida os dados oficiais do TSE e o cadastro dos locais de votação.

**Princípios:**

- **Fonte única:** todo número vem da API, que vem do TSE. Nada é digitado à mão.
- **Todo número tem horário:** a faixa do topo mostra o horário da totalização do TSE e há quanto tempo o app atualizou.
- **Projeção não é resultado:** "Eleito" e "2º turno" só aparecem quando o TSE publica. Dado calculado (ex.: interior = estado − capital) vem identificado.
- **Conferência visível:** a aba Colégios do Omar valida se municípios, capital e estado fecham entre si.
- **Separado da tela neutra do estúdio:** este app é material de campanha. A tela da transmissão fica em outro repositório (`apuracao-am`).

---

## 2. Arquitetura

```
 resultados.tse.jus.br ──►  SERVIDOR DE APURAÇÃO (máquina de produção)
 (arquivos oficiais)        ├─ API  /api/...         ◄── coleta TSE + boletins de urna + cadastro de locais
                            ├─ /candidato/index.html ◄── ESTE APP (arquivo estático)
                            └─ login (acesso restrito a /candidato/)
                                         │  HTTPS, mesmo domínio
                                         ▼
                              celulares da coordenação (navegador)
```

- **Mesmo domínio, obrigatório.** A API não aceita chamadas de outra origem (CORS fechado, testado em 06/10). O app precisa ser servido pelo mesmo endereço da API, por exemplo `https://eleicoes.55.com.vc/candidato/`.
- **Nada a instalar no celular.** É um site: abre no navegador e pode ser adicionado à tela inicial.
- **Ao vivo.** O app escuta `/api/stream` (Server-Sent Events, eventos `hello` e `update` com `versao`) e, como reserva, consulta `/api/meta` a cada 20 s. Quando a `versao` muda, ele recarrega os dados da aba aberta.
- **Sem build.** O app é HTML + CSS + JavaScript puro, num arquivo só. Não usa bibliotecas externas.

---

## 3. Estrutura do repositório

| Caminho | O que é |
|---|---|
| `candidato/index.html` | **O app.** Vai para o servidor em `/candidato/`. |
| `prototipo/sistema-candidato-prototipo.html` | Protótipo com os dados reais do 1º turno embutidos, para teste de uso sem a API. |
| `docs/DOCUMENTACAO_COMPLETA.md` | Este documento. |
| `CONTRATO_API.md` | Especificação dos dois endpoints novos que o servidor precisa criar. |
| `deploy/nginx-candidato.conf` | Exemplo de configuração nginx (com login). |
| `deploy/Caddyfile.exemplo` | Exemplo equivalente para Caddy. |
| `deploy/CHECKLIST_DEPLOY.md` | Passo a passo de instalação e de homologação. |
| `CHANGELOG.md` | Histórico de versões. |
| `README.md` | Resumo e atalhos. |

---

## 4. Abas

| # | Aba | Rota | Pergunta que responde | Endpoints |
|---|---|---|---|---|
| 1 | Principal | `#/principal` | Quem lidera e por quanto? | `/api/{cargo}/estado\|capital\|interior`, `/api/brasil`, `/api/brasil/{uf}`, marcos |
| 2 | Zonas, bairros e colégios | `#/zonas` | Onde estão os votos, por local? | `/api/governador/capital\|interior`, `/api/governador/candidato/{n}`, `/api/locais-votacao/{area}`, **novo** `/api/governador/locais` |
| 3 | Capital, municípios e geral | `#/areas` | Como está cada área? | `/api/governador/capital\|interior\|estado` |
| 4 | Por município | `#/municipio/{codigo}` | Como está a cidade X? | `/api/governador/interior\|capital`, `/api/governador/candidato/{n}`, `/api/locais-votacao/{area}` |
| 5 | Colégios do Omar | `#/colegios` | Quanto cresceu desde o 1º turno? Os números fecham? | `/api/governador/candidato/55?turno=1` e `?turno=2`, **novo** `/api/governador/locais` |
| 6 | Marcos da apuração | `#/marcos` | Quando chegou a 50%? Houve virada? | **novo** `/api/governador/marcos` (até lá, registro local do aparelho) |

### 4.1 Principal

- **Filtros:** cargo (Governador · Presidente) e abrangência (Amazonas · Brasil · outros estados, com as 26 UFs). Governador × Brasil fica desativado. A escolha fica salva no aparelho.
- **Blocos, nesta ordem:** cartão "Último marco"; seções totalizadas (%, X de Y, horário, barra); os dois mais votados (foto, À FRENTE ou ELEITO · TSE, partido e número, % grande, votos, barra); diferença em votos e em pontos percentuais; Manaus × interior (só no Amazonas); totais (comparecimento, abstenção, válidos, brancos e nulos).
- **Pop-up de marcos:** abre sozinho quando há um marco que o aparelho ainda não viu. Mostra horário, seções e, se o marco trouxer, o % do candidato e o saldo sobre o 2º, com a variação desde o marco anterior. Tem navegação Anterior/Próximo; os marcos vistos não reaparecem; o cartão "Último marco" reabre o pop-up.
- **Presidente em outro estado:** mostra só os dois mais votados, que é o que `/api/brasil` (`mapaPresidente`) traz por UF.

### 4.2 Zonas, bairros e colégios

Alterna entre Capital e Interior. Tabela de zonas (votos, % do candidato e posição, 1º colocado; tocar filtra o resto). Bairros por eleitorado. Colégios com busca. Votos por bairro e por colégio aparecem quando o endpoint `/locais` existir; antes disso, a aba mostra eleitores e seções do cadastro, com aviso.

### 4.3 Capital, municípios e geral

Ranking dos candidatos e totais da área. No interior: tabela por calha de rio e tabela dos 61 municípios (filtro por calha, ordenação por votos ou A–Z). Tocar num município abre a aba 4.

### 4.4 Por município

Seletor com os 62 municípios. Mostra o candidato e o adversário (votos, %, posição), o saldo, comparecimento, abstenção, válidos, brancos e nulos, as zonas que atendem o município e os colégios do cadastro.

### 4.5 Colégios do Omar (1º × 2º turno)

- Estado, Manaus e interior: % e votos nos dois turnos, e a variação.
- Os 62 municípios, com ordenação (maior queda primeiro, mais votos, A–Z) e filtro por calha.
- **Validação nos 62**, para cada turno:
  1. 62 municípios presentes (61 do interior + Manaus);
  2. soma dos 61 municípios = interior;
  3. capital + interior = estado;
  4. percentuais entre 0% e 100%;
  5. municípios com 100% das seções.
- Colégio a colégio (Manaus) quando o endpoint `/locais` existir, com a conferência "soma dos colégios = votos do candidato na capital".

Resultado com os dados reais do 1º turno (06/10): as 5 conferências passam (Omar: 354.664 na capital + 487.182 no interior = 841.846 no estado).

### 4.6 Marcos da apuração

Lista de marcos (primeiros votos, 25%, 50%, 75%, 100%, troca de liderança, totalização finalizada). A fonte oficial é o endpoint `/marcos`. Enquanto ele não existir, cada aparelho registra os marcos que observou com o app aberto.

---

## 5. API consumida (já existente)

Todas as rotas recebem `Accept: application/json`. `turno` = 1 ou 2. `cargo` = `governador` ou `presidente`.

### `GET /api/meta`
Usado: `versao` (muda a cada atualização). Também traz `eleicoes` e `cargos[].turnos[]`.

### `GET /api/{cargo}/{area}?turno=` — `area` = `estado` | `capital` | `interior`
```
status ("finalizado" | "sem-dados" | …), aviso, inconsistente, desatualizado
estado: { pctSecoes, secoesTotalizadas, secoesTotal, geradoEm (ISO com fuso), finalizado }
resumo: { pctSecoes, comparecimento, pctComparecimento, abstencao, pctAbstencao,
          validos, totalVotos, brancos, pctBrancos, nulos, pctNulos, … }
candidatos[]: { numero, nomeUrna, partidoSigla, sqcand, votos, pct, situacao, cor, anulado, … }
zonas[]      (capital e interior): { zona, municipios[{codigo,nome}] (interior), totalVotos, validos,
               brancos, nulos, pctSecoes, primeiro{numero,votos,pct}, segundo{…}, margem }
municipios[] (interior): { codigo, nome, calha, totalVotos, comparecimento, abstencao, validos,
               brancos, nulos, pctSecoes, primeiro, segundo, margem }
calhas[]     (interior): { calha, municipios, totalVotos, pctSecoes, primeiro, segundo, margem }
```
`status: "sem-dados"` = turno ainda não publicado. O app mostra "aguardando".

### `GET /api/{cargo}/candidato/{numero}?turno=`
```
candidato: { numero, nomeUrna, partidoSigla, sqcand, situacao, cor }
estado | capital | interior: { votos, pct, posicao }
municipios[]: { codigo, nome, votos, pct, posicao, pctSecoes }
zonas[] (capital) e zonasInterior[]: { zona, votos, pct, posicao, pctSecoes }
calhas[]: { calha, votos, pct, posicao }
```

### `GET /api/locais-votacao/{area}` — cadastro de colégios (sem votos)
```
fonte, totais{locais,secoes,eleitores,zonas,municipios}
locais[]: { zona, codigo (município TSE), municipio, nome, bairro, secoes, eleitores, endereco }
```
Opcional, já aceito pelo app: `bairros[]: { chave ("bairro" ou "códigoMunicípio|bairro"), locais, secoes, eleitores, zonas[] }`.

### `GET /api/brasil?turno=`
```
presidente: { estado, resumo, candidatos[] }        ← Presidente · Brasil
ufs[]: { uf, nome, pctSecoes, secoesTotalizadas, secoesTotal }
mapaPresidente[]: { uf, aptos, comparecimento, abstencao, validos, brancos, nulos, totalVotos,
                    finalizado, primeiro{numero,votos,pct}, segundo{…} }   ← Presidente em outra UF
```

### `GET /api/brasil/{uf}?turno=` — Governador de outra UF
```
disponivel, estado, resumo, candidatos[]   (também traz senador, não usado)
```

### `GET /api/stream` (SSE)
Eventos `hello` e `update`, com `data: {"versao": N}`.

### `GET /fotos/{sqcand}.jpeg`
Foto do candidato. Se faltar, o app mostra as iniciais.

---

## 6. Endpoints novos (a criar no servidor)

Detalhe completo em `CONTRATO_API.md`. Resumo:

| Endpoint | Para quê | Sem ele |
|---|---|---|
| `GET /api/{cargo}/locais?turno=&area=` | Votos por colégio (soma dos boletins de urna das seções de cada local), com `zona`, `codigo`, `nome`, `bairro`, `validos`, `candidatos{numero: votos}` | Abas 2 e 5 mostram só o cadastro, com aviso |
| `GET /api/{cargo}/marcos?turno=` | Marcos oficiais da noite, com `tse`, `pct`, `eu` (% do candidato), `dif` (saldo), `lider` | Cada aparelho registra os próprios marcos; o pop-up mostra o que houver |

Chave de ligação colégio ↔ cadastro: `codigo` + `zona` + `nome` normalizado (sem acento, minúsculo), iguais aos de `/api/locais-votacao`.

---

## 7. Regras de dados e conferências

| Regra | Onde |
|---|---|
| Percentual sobre votos válidos (base do TSE) | Todas as abas |
| "Eleito" só com situação exata do TSE ("Não eleito" contém "eleito") | Principal, Áreas |
| Interior calculado e identificado (estado − capital) | Principal (Manaus × interior) |
| Turno 1 e turno 2 nunca se misturam, exceto na aba comparativa | Todas |
| Comparação 1º × 2º avisa quando o 2º está parcial | Colégios do Omar |
| Validação nos 62 municípios | Colégios do Omar |
| Falha de conexão não apaga a tela; a faixa avisa | Todas |
| Sem dado do turno = "aguardando", nunca zero inventado | Todas |

---

## 8. Configuração

### Parâmetros na URL
| Parâmetro | Padrão | Uso |
|---|---|---|
| `?turno=1` | 2 | Ensaio com o 1º turno real |
| `?candidato=55` | 55 | Número do candidato acompanhado |
| `?cargo=governador` | governador | Cargo das abas 2 a 6 |
| `?api=https://…` | vazio | Só para testes; em produção fica vazio (mesmo domínio) |

### Constantes no código (`candidato/index.html`)
| Constante | Valor | Quando mudar |
|---|---|---|
| `VERSAO` | `"2.4.0 (06/10/2026)"` | A cada publicação |
| `CAPITAL` | `"02550"` (Manaus, código TSE) | Nunca, para o AM |
| `ROTAS` | todas as rotas da API | Se o servidor mudar um caminho |
| `UFS` | 27 UFs | Nunca |

### Preferências salvas no aparelho (localStorage)
`cand_principal` (filtros), `cand_acess` (acessibilidade), `cand_marcos_*` (marcos locais e vistos). Se apagadas, o app volta ao padrão.

---

## 9. Instalação no servidor de produção

**Pré-requisitos:** o servidor que já responde `https://<domínio>/api/...`; um servidor web na frente (nginx, Caddy ou o próprio backend servindo arquivos estáticos); HTTPS ativo.

1. Clonar o repositório privado na máquina de produção (ou baixar o ZIP pelo GitHub).
2. Copiar `candidato/index.html` para a pasta pública que responde em `/candidato/`. Ex.: `/var/www/eleicoes/candidato/index.html`.
3. Configurar o **login** só para `/candidato/` (modelos em `deploy/`). Criar um usuário por pessoa da coordenação.
4. Garantir que `/api/` e `/fotos/` continuem abertos para o próprio domínio. O app não precisa de CORS.
5. Cabeçalhos: `Cache-Control: no-cache` para `/candidato/index.html`, para que uma nova versão chegue sem limpar o cache; `X-Robots-Tag: noindex`.
6. Abrir `https://<domínio>/candidato/?turno=1` e seguir a homologação (seção 11).
7. Confirmar a versão no rodapé.

**Se o backend for Node/Express em vez de nginx:** servir a pasta como estática na rota `/candidato` e proteger com autenticação básica (ex.: `express.static` + `express-basic-auth`), usando usuários definidos em variáveis de ambiente, nunca no repositório.

**Atualização:** `git pull` na máquina e copiar de novo o `index.html`. Os celulares pegam a versão nova ao recarregar.

---

## 10. Operação (2º turno, 25/10/2026)

| Quando | O quê |
|---|---|
| D-2 (23/10) | Ensaio final com `?turno=1` nos celulares da coordenação; versão congelada |
| D, 06h | Conferir se `/api/meta` responde e se `/candidato/` pede login |
| D, 15h | Abrir o app em todos os celulares; aba Principal aguardando dados do 2º turno |
| Apuração | Acompanhar a faixa do topo: "ao vivo" verde; "sem conexão" vermelho → ver contingência |
| Fim | Colégios do Omar: validação nos 62 com tudo OK |

**Contingência:**

- **API fora do ar:** o app mantém o último dado e mostra "sem conexão". Use o site oficial `resultados.tse.jus.br`.
- **Celular sem rede:** troque para o 4G; o app volta sozinho.
- **Número suspeito:** confira na aba Colégios do Omar (validação) e no site do TSE antes de repassar.

---

## 11. Testes e homologação

- **Protótipo** (`prototipo/`): dados reais do 1º turno embutidos. Serve para testar uso e leitura sem a API.
- **Ensaio na produção:** `https://<domínio>/candidato/?turno=1`.

| Critério de aceite | Como verificar |
|---|---|
| Abre em até 5 s no 4G e pede login | Cronômetro, 3 aparelhos |
| Números da Principal = site do TSE | 10 conferências (AM, Brasil, 2 UFs) |
| Validação nos 62 sem ✕ no 1º turno | Aba Colégios do Omar |
| Nada passa da largura da tela (360 a 430 px) | Celulares da equipe |
| Acessibilidade: texto a 160% sem cortes | Botão Aa |
| Ao vivo: mudança de `versao` atualiza a tela em até 20 s | Forçar atualização no backend |
| Pop-up de marcos abre uma vez por marco | Recarregar a página |

---

## 12. Acessibilidade

Botão **Aa**: tamanho do texto (85% a 160%), alto contraste, tema escuro, reduzir animações e tela cheia. Também: foco visível, leitores de tela (faixa de status anunciada, diálogos com `aria-modal`), Esc fecha menus e pop-ups, e o app respeita "reduzir movimento" do sistema. Sem escolha salva, o tema segue o do aparelho.

---

## 13. Versões e fluxo no GitHub

- Padrão `MAIOR.MENOR.CORREÇÃO`. Toda mudança: atualizar `VERSAO`, registrar no `CHANGELOG.md`, fazer commit e criar a tag `vX.Y.Z`.
- Ramo `main` = o que está em produção. Mudanças em ramo próprio, revisadas antes de entrar.
- **Congelamento** após o ensaio de 23/10: só correções críticas, com aprovação da coordenação.

---

## 14. Segurança e privacidade

- **Repositório privado.** Não publicar no GitHub Pages: o site ficaria aberto a qualquer pessoa com o link.
- **App só com login**, no mesmo domínio da API.
- **Nenhuma senha, token ou lista de usuários no repositório.** Credenciais ficam no servidor (arquivo de senhas fora da pasta pública ou variáveis de ambiente).
- `noindex` no HTML e no cabeçalho.
- Dados exibidos: resultados oficiais e cadastro de locais (públicos), organizados para uso estratégico da campanha. Tratar como material interno.

---

## 15. Pendências

| Item | Responsável sugerido | Prazo sugerido |
|---|---|---|
| Criar `/api/{cargo}/locais` (votos por colégio) | Equipe do servidor | 16/10 |
| Criar `/api/{cargo}/marcos` | Equipe do servidor | 16/10 |
| Publicar `/candidato/` com login | Equipe do servidor | 12/10 |
| Lista de quem terá acesso | Coordenação | 12/10 |
| Ensaio com a coordenação (`?turno=1`) | Coordenação + equipe | 16/10 e 23/10 |

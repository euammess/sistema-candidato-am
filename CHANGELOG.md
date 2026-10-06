# Histórico de versões

## 2.5.0 — 06/10/2026
- O app passa a rodar na **central SESMT01** (`PAINEL/candidato/index.html`), servido pelo `api_territorio.py servir --rede` em `http://<ip-da-central>:8765/candidato/`. O servidor do modelo visual (eleicoes.55.com.vc) não é usado.
- Dados: `api_candidato.py` responde as mesmas rotas com o banco da central. Os dois endpoints que faltavam existem: `/api/{cargo}/locais` (votos por colégio, soma dos boletins) e `/api/{cargo}/marcos` (marcos oficiais da central, com % e saldo do candidato).
- Sem login (decisão de 06/10): acesso só pelo link, enviado pela MESA.
- Interior identificado como cálculo (Amazonas − Manaus) no bloco Manaus × interior; marcos pedem o número do candidato (`&candidato=`).

## 2.4.0 — 06/10/2026
- Pop-up de marcos na aba Principal: abre sozinho quando há marco novo que este aparelho ainda não viu; mostra horário, seções totalizadas e, quando o marco traz os votos, o % do candidato e o saldo sobre o 2º, com a variação desde o marco anterior.
- Navegação entre marcos (botões, setas do teclado), fecha com Esc ou "Entendi"; marcos vistos não reaparecem.
- Cartão "Último marco" na Principal para reabrir o pop-up, com contador de marcos novos.

## 2.3.0 — 06/10/2026
- Modo protótipo (dados embutidos em `window.__PROTO`) para testes de uso sem a API.
- Troca de turno sem recarregar no protótipo; tema segue o aparelho quando não há escolha salva.
- Bairros pré-agregados aceitos da API (`bairros` em `/api/locais-votacao`); coluna de seções oculta em telas estreitas.
- Confirmação de "apagar marcos" feita na própria página.

## 2.2.0 — 06/10/2026
- Página principal refeita no modelo aprovado: bloco de seções totalizadas, os dois mais votados com percentual grande, diferença, Manaus × interior e totais.
- Filtro de cargo (Governador · Presidente) e de abrangência (Amazonas · Brasil · outros estados, com seletor das 26 UFs). Governador × Brasil fica desativado.

## 2.1.0 — 06/10/2026
- Painel de acessibilidade (Aa): tamanho do texto, alto contraste, tema escuro, reduzir animações e tela cheia, com as escolhas salvas no aparelho.
- Nomes longos quebram em duas linhas em vez de serem cortados.

## 2.0.0 — 06/10/2026
- Novo produto: Sistema do Candidato (mobile), separado da tela neutra do estúdio.
- Seis abas: Principal, Zonas/bairros/colégios, Capital/municípios/geral, Por município (62), Colégios do Omar (1º × 2º turno, com validação nos 62 municípios) e Marcos da apuração.
- Fonte: API do sistema (`eleicoes.55.com.vc/api`), com atualização ao vivo por `/api/stream` e consulta de reserva a cada 20 s.
- Votos por colégio e marcos dependem de dois endpoints novos (ver CONTRATO_API.md); sem eles, o app avisa e mostra o cadastro.

## 1.0.0 — 06/10/2026
- Tela do estúdio com leitura direta da API do TSE (repositório `apuracao-am`).

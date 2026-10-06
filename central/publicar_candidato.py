# -*- coding: utf-8 -*-
"""
publicar_candidato.py — o Sistema do Candidato aberto pela internet (GitHub Pages)
==================================================================================

Decisão de 06/10/2026: o app do celular fica disponível POR LINK para qualquer
usuário. A central (SESMT01) continua fechada na rede da DMD; o que sai dela são
RETRATOS: os mesmos JSON que o api_candidato.py responde, gravados em arquivos e
enviados a um repositório PÚBLICO do GitHub, que o GitHub Pages serve.

    python publicar_candidato.py gerar              # monta SITE_CANDIDATO/ (sem enviar)
    python publicar_candidato.py enviar             # gera + envia, se algo mudou
    python publicar_candidato.py loop --cada 180    # noite da eleição: a cada 3 min

Como o site é montado (SITE_CANDIDATO/)
---------------------------------------
    index.html                    o app (PAINEL/candidato/index.html) em MODO ESTÁTICO
    dados/*.json                  um arquivo por rota da API (nomes em ARQ abaixo)
    fotos/<sqcand>.jpeg           fotos dos candidatos (ENTRADA/FOTOS, baixadas do TSE)
    .github/workflows/pages.yml   publica no GitHub Pages a cada envio
    .nojekyll                     o Pages não mexe nos arquivos

O modo estático: o index.html ganha `window.__ESTATICO = true`. Com ele o app troca
as rotas /api/... pelos arquivos de dados/, não abre o /api/stream (não existe no
Pages) e confere dados/meta.json a cada 20 s; quando a `versao` muda, recarrega.

Repositório: o código (este arquivo, o app, a API, a documentação) vai no ramo `main`.
O SITE vai no ramo `site`, ÓRFÃO e reescrito a cada envio (um commit só): a noite da
eleição gera ~100 retratos de ~1 MB e o histórico não pode crescer junto.

ARMADILHAS
----------
 1. O Pages serve o site em https://<conta>.github.io/<repo>/ — caminho com prefixo.
    Tudo no app tem de ser RELATIVO ("dados/...", "fotos/..."), nunca "/api" ou "/fotos".
 2. O Pages responde com cache de 10 min. Cada leitura leva "?v=<versao>" e a do
    meta.json leva "?t=<agora>", senão o celular via o retrato velho.
 3. Envio com ramo de deploy por branch tem limite de ~10 publicações por hora; com o
    workflow do Actions (este) não há esse limite. O ambiente github-pages precisa
    aceitar o ramo `site` (configurado uma vez por `configurar`).
 4. Só envia quando a versão muda: sem apuração, nada sai (sem commits vazios).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

import api_candidato as C
from banco import Banco
from coletor import ler_config

RAIZ = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("ELEICOES_DB") or os.path.join(RAIZ, "BANCO", "eleicoes_am_2026.db")
APP = os.path.join(RAIZ, "PAINEL", "candidato", "index.html")
SITE = os.path.join(RAIZ, "SITE_CANDIDATO")
NUM = "55"
UFS = [u for u in C.UFS if u != "am"]

WORKFLOW = """name: Publicar no GitHub Pages
on:
  push:
    branches: [site]
  workflow_dispatch:
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: pages
  cancel-in-progress: true
jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: .
      - id: deployment
        uses: actions/deploy-pages@v4
"""

#: JS injetado no app: rotas da API -> arquivos de dados/ (armadilhas 1 e 2)
ESTATICO_JS = """<script>
/* MODO ESTÁTICO (publicar_candidato.py): retratos da central no GitHub Pages */
window.__ESTATICO = true;
window.__ROTA_ESTATICA = function(caminho, versao){
  var u = new URL(caminho, "http://x"), p = u.pathname.replace(/^\\/api\\//, "").split("/"), q = u.searchParams;
  var t = q.get("turno") ? "-t" + q.get("turno") : "", nome;
  if (p[0] === "meta") return "dados/meta.json?t=" + Date.now();
  if (p[0] === "locais-votacao") nome = "locais-votacao-" + p[1];
  else if (p[0] === "brasil") nome = p[1] ? "brasil-" + p[1] + t : "brasil" + t;
  else if (p[1] === "candidato") nome = p[0] + "-candidato-" + p[2] + t;
  else if (p[1] === "locais") nome = p[0] + "-locais-" + (q.get("area") || "capital") + t;
  else nome = p[0] + "-" + p[1] + t;
  return "dados/" + nome + ".json?v=" + (versao || "0");
};
</script>
"""


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _grava(nome: str, obj) -> None:
    with open(os.path.join(SITE, "dados", nome + ".json"), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"), default=str)


def app_estatico() -> str:
    """O index.html da central com o modo estático ligado."""
    with open(APP, encoding="utf-8") as f:
        h = f.read()
    trocas = [
        # armadilha 1: caminhos relativos
        ('function foto(sq){ return "/fotos/" + encodeURIComponent(sq) + ".jpeg"; }',
         'function foto(sq){ return "fotos/" + encodeURIComponent(sq) + ".jpeg"; }'),
        # rotas -> arquivos
        ('var p = fetch(API + caminho, { headers:{ Accept:"application/json" }, cache:"no-store" })',
         'var p = fetch(window.__ESTATICO ? window.__ROTA_ESTATICA(caminho, versaoDados) : API + caminho, '
         '{ headers:{ Accept:"application/json" }, cache:"no-store" })'),
        # meta da consulta de reserva
        ('fetch(API + ROTAS.meta(), {cache:"no-store"})',
         'fetch(window.__ESTATICO ? window.__ROTA_ESTATICA(ROTAS.meta()) : API + ROTAS.meta(), {cache:"no-store"})'),
        # sem /api/stream no Pages: só a consulta de reserva (20 s), com 1ª leitura imediata
        ('else { lerRota(); desenhar(); conectarStream(); consultar(); }',
         'else { lerRota(); if (window.__ESTATICO) { fetch(window.__ROTA_ESTATICA(ROTAS.meta()), {cache:"no-store"})'
         '.then(function(r){ return r.json(); }).then(function(m){ versaoDados = m.versao; desenhar(); }, function(){ desenhar(); }); '
         'consultar(); } else { desenhar(); conectarStream(); consultar(); } }'),
        ('Fonte: TSE, via central SESMT01. Versão ',
         'Fonte: TSE, via central SESMT01 (retrato publicado). Versão '),
    ]
    for a, b in trocas:
        if a not in h:
            raise SystemExit(f"publicar_candidato: o app mudou e o trecho não foi achado:\n  {a[:90]}")
        h = h.replace(a, b, 1)
    return h.replace("<script>\n(function(){", ESTATICO_JS + "<script>\n(function(){", 1)


def gerar(cfg: dict) -> int:
    """Monta SITE_CANDIDATO/. Devolve a versão dos dados."""
    os.makedirs(os.path.join(SITE, "dados"), exist_ok=True)
    os.makedirs(os.path.join(SITE, "fotos"), exist_ok=True)
    os.makedirs(os.path.join(SITE, ".github", "workflows"), exist_ok=True)
    b = Banco(DB)
    try:
        v = C.versao(b)
        resp = lambda partes, q=None: C.responder(b, cfg, partes, q or {})
        n = 0
        meta, _ = resp(["meta"])
        meta.pop("ipRede", None)
        meta["publicadoEm"] = C._iso_mao(datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
        _grava("meta", meta)
        for area in ("capital", "interior"):
            _grava(f"locais-votacao-{area}", resp(["locais-votacao", area])[0])
        fotos = set()
        for t in (1, 2):
            q = {"turno": str(t)}
            for cargo in ("governador", "presidente"):
                for area in ("estado", "capital", "interior"):
                    o, _ = resp([cargo, area], q)
                    _grava(f"{cargo}-{area}-t{t}", o)
                    n += 1
                    for c in o.get("candidatos") or []:
                        if c.get("sqcand"):
                            fotos.add(c["sqcand"])
                est, _ = resp([cargo, "estado"], q)
                nums = [c["numero"] for c in est.get("candidatos") or []]
                if cargo == "presidente":
                    nums = nums[:2]
                for num in nums:
                    o, code = resp([cargo, "candidato", num], q)
                    if code == 200:
                        _grava(f"{cargo}-candidato-{num}-t{t}", o)
                        n += 1
                for area in ("capital", "interior"):
                    _grava(f"{cargo}-locais-{area}-t{t}", resp([cargo, "locais"], dict(q, area=area))[0])
                _grava(f"{cargo}-marcos-t{t}", resp([cargo, "marcos"], dict(q, candidato=NUM))[0])
            _grava(f"brasil-t{t}", resp(["brasil"], q)[0])
            for uf in UFS:                                   # fotos de outras UFs: não baixadas
                _grava(f"brasil-{uf}-t{t}", resp(["brasil", uf], q)[0])
        # fotos: as que a central já tem; as que faltam, baixa do TSE uma vez
        for sq in fotos:
            dst = os.path.join(SITE, "fotos", f"{sq}.jpeg")
            if os.path.exists(dst):
                continue
            src = os.path.join(C.DIR_FOTOS, f"{sq}.jpeg")
            if not os.path.exists(src):
                C.foto(_Nulo(), cfg, sq)                     # grava em ENTRADA/FOTOS
            if os.path.exists(src):
                shutil.copyfile(src, dst)
    finally:
        b.fechar()
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write(app_estatico())
    with open(os.path.join(SITE, ".github", "workflows", "pages.yml"), "w", encoding="utf-8") as f:
        f.write(WORKFLOW)
    open(os.path.join(SITE, ".nojekyll"), "w").close()
    with open(os.path.join(SITE, "robots.txt"), "w") as f:
        f.write("User-agent: *\nDisallow: /\n")
    log(f"site gerado: versão {v}, {n} retratos de cargo, {len(fotos)} fotos")
    return v


class _Nulo:
    """Handler de mentira para reaproveitar api_candidato.foto() fora do servidor."""
    class _W:
        def write(self, *_): pass
    wfile = _W()
    def send_response(self, *_): pass
    def send_header(self, *_): pass
    def end_headers(self): pass


# ===========================================================================
# GIT: ramo `site` órfão, reescrito a cada envio
# ===========================================================================

def git(*args, cwd=SITE, ok=(0,)) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode not in ok:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def remoto(cfg: dict) -> str:
    url = (cfg.get("candidato_site") or {}).get("repositorio")
    if not url:
        raise SystemExit("config.json -> candidato_site.repositorio está vazio (ex.: "
                         "https://github.com/<conta>/sistema-candidato-am.git)")
    return url


def enviar(cfg: dict, forcar: bool = False) -> bool:
    estado = os.path.join(RAIZ, "LOGS", "candidato_site_versao.txt")
    v = gerar(cfg)
    try:
        antes = open(estado).read().strip()
    except Exception:
        antes = ""
    if str(v) == antes and not forcar:
        log("nada mudou desde o último envio — não envia (armadilha 4)")
        return False
    if os.path.isdir(os.path.join(SITE, ".git")):
        shutil.rmtree(os.path.join(SITE, ".git"), onerror=lambda f, p, e: (os.chmod(p, 0o700), f(p)))
    git("init", "-q", "-b", "site")
    git("add", "-A")
    git("-c", "user.name=Central SESMT01", "-c", "user.email=central@sesmt01.local",
        "commit", "-q", "-m", f"retrato da central · versão {v} · {datetime.now():%d/%m %H:%M}")
    git("push", "-q", "--force", remoto(cfg), "site:site")
    os.makedirs(os.path.dirname(estado), exist_ok=True)
    with open(estado, "w") as f:
        f.write(str(v))
    log(f"enviado ao GitHub (ramo site): versão {v}")
    return True


def loop(cfg: dict, cada: int):
    log(f"publicação contínua a cada {cada}s — Ctrl+C encerra")
    while True:
        try:
            enviar(ler_config())
        except Exception as e:
            log(f"FALHOU: {e}  (tenta de novo no próximo ciclo)")
        time.sleep(cada)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("acao", choices=["gerar", "enviar", "loop"])
    p.add_argument("--cada", type=int, default=180)
    p.add_argument("--forcar", action="store_true")
    a = p.parse_args()
    cfg = ler_config()
    if a.acao == "gerar":
        gerar(cfg)
    elif a.acao == "enviar":
        enviar(cfg, a.forcar)
    else:
        loop(cfg, a.cada)


if __name__ == "__main__":
    main()

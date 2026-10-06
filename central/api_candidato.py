# -*- coding: utf-8 -*-
"""
api_candidato.py — a API do SISTEMA DO CANDIDATO servida pela própria central
==============================================================================

O app `PAINEL/candidato/index.html` (Sistema do Candidato, mobile, versão 2.4.0 de
06/10/2026) foi desenhado sobre a API do modelo visual (eleicoes.55.com.vc). Decisão
de 06/10/2026: o app NÃO vai para aquele servidor — roda na central SESMT01, servido
pelo `api_territorio.py servir`, e lê o BANCO DA CENTRAL. Este módulo responde as
mesmas rotas, no mesmo formato, com os dados do banco:

    GET /api/meta                                  versao (muda a cada coleta/boletim)
    GET /api/{cargo}/{estado|capital|interior}?turno=1|2
    GET /api/{cargo}/candidato/{numero}?turno=
    GET /api/{cargo}/locais?turno=&area=capital|interior   votos por colégio (boletins)
    GET /api/{cargo}/marcos?turno=                 marcos oficiais da noite (tabela marco)
    GET /api/locais-votacao/{capital|interior}     cadastro de colégios (sem votos)
    GET /api/brasil?turno=                         Presidente · Brasil
    GET /api/brasil/{uf}?turno=                    Governador de outra UF
    GET /api/stream                                SSE: hello/update com {"versao": N}
    GET /fotos/{sqcand}.jpeg                       foto do TSE, guardada em ENTRADA/FOTOS

    cargo = governador | presidente

De onde vem cada número
-----------------------
  estado / capital / municípios / Brasil / outras UFs
      Totalização oficial do TSE gravada pelo coletor (tabelas apuracao + voto), a
      rodada mais recente de cada abrangência.
  interior
      CALCULADO: estado − Manaus (o TSE não publica "interior"). Vem marcado em
      abrangencia.calculado.
  zonas, colégios e bairros
      Soma dos BOLETINS DE URNA lidos pelo bu.py (Territorio do api_territorio), porque
      o coletor não grava totalização por zona. Vem marcado em fonte.
  calhas e cores
      ENTRADA/calhas_cores_am.json (copiado do modelo visual em 06/10/2026).

ARMADILHAS
----------
 1. abr_cd 'am' existe com abr_tipo 'uf' E 'ufbr' (governador das 27 UFs). O estado
    do AM é sempre abr_tipo='uf'; outra UF é 'ufbr'.
 2. gerado_em vem do TSE em horário de BRASÍLIA (sem fuso) → "-03:00". Já apuracao.ts
    e marco.ts são o relógio da central (Manaus) → "-04:00".
 3. Presidente por UF: o coletor só baixa Brasil e AM. O mapaPresidente traz só o AM;
    o app mostra "sem dados" para as outras UFs (não inventa).
 4. 2º turno sem pleito no config (turnos.2.pleito = null) → sem boletins: colégios e
    zonas do 2º turno ficam vazios até o descobrir gravar o pleito.
 5. Os marcos "empate:*" são PROJEÇÃO do motor de empate — não entram aqui (projeção
    não é resultado). Só os marcos oficiais (início, 25/50/75/100%, totalização,
    2º turno, eleitos, virada).
"""

from __future__ import annotations

import json
import os
import threading
import time
import unicodedata
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

RAIZ = os.path.dirname(os.path.abspath(__file__))
DIR_FOTOS = os.path.join(RAIZ, "ENTRADA", "FOTOS")
ARQ_CALHAS = os.path.join(RAIZ, "ENTRADA", "calhas_cores_am.json")

CAPITAL = "02550"
CARGOS = {"governador": 3, "presidente": 1}
NOME_CARGO = {3: "Governador", 1: "Presidente"}
ROTAS = {"meta", "governador", "presidente", "brasil", "locais-votacao", "stream"}
UFS = {"ac": "Acre", "al": "Alagoas", "ap": "Amapá", "am": "Amazonas", "ba": "Bahia",
       "ce": "Ceará", "df": "Distrito Federal", "es": "Espírito Santo", "go": "Goiás",
       "ma": "Maranhão", "mt": "Mato Grosso", "ms": "Mato Grosso do Sul",
       "mg": "Minas Gerais", "pa": "Pará", "pb": "Paraíba", "pr": "Paraná",
       "pe": "Pernambuco", "pi": "Piauí", "rj": "Rio de Janeiro",
       "rn": "Rio Grande do Norte", "rs": "Rio Grande do Sul", "ro": "Rondônia",
       "rr": "Roraima", "sc": "Santa Catarina", "sp": "São Paulo", "se": "Sergipe",
       "to": "Tocantins"}
#: marco do banco (prefixo do tipo) -> título no app
MARCOS = [("inicio_apuracao", "inicio", "Primeiros votos"),
          ("um_quarto", "p25", "25% das seções"),
          ("metade", "p50", "50% das seções"),
          ("tres_quartos", "p75", "75% das seções"),
          ("apuracao_100", "p100", "100% das seções"),
          ("totalizacao_finalizada", "fim", "Totalização finalizada pelo TSE"),
          ("segundo_turno", "2t", None),
          ("eleitos", "eleitos", None),
          ("virada", "virada", None)]


def _ref() -> dict:
    try:
        with open(ARQ_CALHAS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"calhas": {}, "cores": {}}


REF = _ref()


def norm(t) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t or ""))
                   if unicodedata.category(c) != "Mn").lower()


def _pct(a, b) -> float:
    return (100.0 * a / b) if b else 0.0


def _iso_br(t: Optional[str]) -> Optional[str]:
    """gerado_em do TSE (Brasília, sem fuso) -> ISO com -03:00 (armadilha 2)."""
    return (t + "-03:00") if t and len(t) == 19 else t


def _iso_mao(t: Optional[str]) -> Optional[str]:
    """relógio da central (Manaus) -> ISO com -04:00 (armadilha 2)."""
    return (t + "-04:00") if t and len(t) == 19 else t


def eleicao(cfg: dict, cargo: int, turno: int) -> Optional[int]:
    t = cfg.get("turnos", {}).get(str(turno), {})
    v = t.get("eleicao_federal" if cargo == 1 else "eleicao_estadual")
    return int(v) if v else None


# ===========================================================================
# 1. LEITURA DO BANCO: a rodada mais recente de cada abrangência
# ===========================================================================

def ultima(b, cd: Optional[int], cargo: int, tipo: str, abr: str):
    if not cd:
        return None
    return b.um("""SELECT * FROM apuracao WHERE cd_eleicao=? AND cargo=? AND abr_cd=?
                   AND abr_tipo=? ORDER BY ts DESC, id DESC LIMIT 1""", (cd, cargo, abr, tipo))


def ultimas_mun(b, cd: Optional[int], cargo: int) -> Dict[str, object]:
    if not cd:
        return {}
    out = {}
    for r in b.query("""SELECT a.* FROM apuracao a JOIN (
                          SELECT abr_cd, MAX(id) mid FROM apuracao
                          WHERE cd_eleicao=? AND cargo=? AND abr_tipo='mu' GROUP BY abr_cd) u
                        ON u.mid=a.id""", (cd, cargo)):
        out[r["abr_cd"]] = r
    return out


def votos_da(b, ap) -> List[dict]:
    if ap is None:
        return []
    rs = b.query("""SELECT * FROM voto WHERE cd_eleicao=? AND cargo=? AND abr_cd=?
                    AND abr_tipo=? AND rodada=?""",
                 (ap["cd_eleicao"], ap["cargo"], ap["abr_cd"], ap["abr_tipo"], ap["rodada"]))
    return [dict(r) for r in rs]


def resumo_de(ap) -> dict:
    if ap is None:
        return {}
    comp = ap["comparecimento"] or 0
    return {"secoesTotal": ap["secoes_total"] or 0,
            "secoesTotalizadas": ap["secoes_totalizadas"] or 0,
            "pctSecoes": ap["pct_secoes_totalizadas"] or 0,
            "aptos": ap["eleitores_aptos"] or 0,
            "aptosApurados": ap["eleitores_aptos_apurados"] or 0,
            "comparecimento": comp,
            "pctComparecimento": _pct(comp, ap["eleitores_aptos_apurados"] or 0),
            "abstencao": ap["abstencao"] or 0,
            "pctAbstencao": _pct(ap["abstencao"] or 0, ap["eleitores_aptos_apurados"] or 0),
            "validos": ap["votos_validos"] or 0, "nominais": ap["votos_nominais"] or 0,
            "legenda": ap["votos_legenda"] or 0, "totalVotos": comp,
            "brancos": ap["votos_brancos"] or 0, "pctBrancos": _pct(ap["votos_brancos"] or 0, comp),
            "nulos": ap["votos_nulos"] or 0, "pctNulos": _pct(ap["votos_nulos"] or 0, comp),
            "votosPorEleitor": 1, "geradoEm": _iso_br(ap["gerado_em"]),
            "finalizado": bool(ap["finalizado"])}


def subtrai(a: dict, c: dict) -> dict:
    """interior = estado − capital (CALCULADO)."""
    r = {}
    for k in ("secoesTotal", "secoesTotalizadas", "aptos", "aptosApurados", "comparecimento",
              "abstencao", "validos", "nominais", "legenda", "totalVotos", "brancos", "nulos"):
        r[k] = (a.get(k) or 0) - (c.get(k) or 0)
    r.update(pctSecoes=_pct(r["secoesTotalizadas"], r["secoesTotal"]),
             pctComparecimento=_pct(r["comparecimento"], r["aptosApurados"]),
             pctAbstencao=_pct(r["abstencao"], r["aptosApurados"]),
             pctBrancos=_pct(r["brancos"], r["totalVotos"]), pctNulos=_pct(r["nulos"], r["totalVotos"]),
             votosPorEleitor=1, geradoEm=max(a.get("geradoEm") or "", c.get("geradoEm") or "") or None,
             finalizado=bool(a.get("finalizado") and c.get("finalizado")))
    return r


def cand_de(v: dict) -> dict:
    num = str(v.get("numero") or "")
    sit = v.get("situacao") or ""
    return {"numero": num, "nome": v.get("nome"), "nomeUrna": v.get("nome_urna") or v.get("nome"),
            "sqcand": v.get("sqcand"), "partidoNumero": num[:2], "partidoSigla": v.get("partido"),
            "coligacao": v.get("coligacao"), "situacao": sit, "eleito": bool(v.get("eleito")),
            "cor": REF.get("cores", {}).get(num, "#6b7b8d"), "votos": v.get("votos") or 0,
            "pct": v.get("pct") or 0.0,
            "anulado": (v.get("validade") or "").lower().startswith("anulad")}


def ordenar(cands: List[dict]) -> List[dict]:
    cands.sort(key=lambda c: -c["votos"])
    p = 0
    for c in cands:
        if not c["anulado"]:
            p += 1
            c["posicao"] = p
    return cands


def duelo(votos: Dict[str, int], validos: int) -> dict:
    o = sorted(votos.items(), key=lambda x: -x[1])
    f = lambda i: ({"numero": o[i][0], "votos": o[i][1], "pct": _pct(o[i][1], validos)}
                   if len(o) > i else None)
    p1, p2 = f(0), f(1)
    return {"primeiro": p1, "segundo": p2,
            "margem": (p1["pct"] - (p2["pct"] if p2 else 0)) if p1 else 0,
            "empate": bool(p1 and p2 and p1["votos"] == p2["votos"])}


# ===========================================================================
# 2. TERRITÓRIO (boletins de urna) — zonas, colégios; em cache por turno
# ===========================================================================

_cache_T: Dict[int, Tuple[tuple, object]] = {}
_trava_T = threading.Lock()


def territorio(b, cfg: dict, turno: int):
    """Territorio do api_territorio para o turno, refeito só quando chega boletim novo."""
    import api_territorio as AT
    from coletor import contexto
    ctx = contexto(cfg, turno)
    if not ctx.get("pleito"):
        return None                                          # armadilha 4
    r = b.um("SELECT COUNT(*) n, MAX(lido_em) m FROM bu_leitura WHERE pleito=?",
             (int(ctx["pleito"]),))
    chave = (r["n"], r["m"])
    with _trava_T:
        c = _cache_T.get(turno)
        if c and c[0] == chave:
            return c[1]
        T = AT.Territorio(b, cfg, ctx)
        _cache_T[turno] = (chave, T)
        return T


def zonas_bu(T, cargo: int, area: str) -> List[dict]:
    """Zonas pela soma dos boletins. Capital: zonas de Manaus. Interior: zona =
    soma dos municípios do interior que ela atende (sem a parte de Manaus)."""
    if T is None:
        return []
    G: Dict[str, dict] = {}
    for u in T.agregar("zona"):
        cap = u["mun"] == CAPITAL
        if (area == "capital") != cap:
            continue
        g = G.setdefault(u["zona"], {"zona": u["zona"], "municipios": [], "aptos": 0,
                                      "aptosApurados": 0, "comparecimento": 0, "urnas": 0,
                                      "apuradas": 0, "validos": 0, "brancos": 0, "nulos": 0,
                                      "votos": defaultdict(int)})
        if not cap:
            g["municipios"].append({"codigo": u["mun"], "nome": u.get("mun_nome")})
        g["aptos"] += u["aptos"]
        g["aptosApurados"] += u["aptos_apurados"]
        g["urnas"] += u["urnas"]
        g["apuradas"] += u["urnas_apuradas"]
        c = u["cargos"].get(cargo)
        if c:
            g["validos"] += c["validos"]
            g["brancos"] += c["brancos"]
            g["nulos"] += c["nulos"]
            for x in c["cand"]:
                g["votos"][x["n"]] += x["v"]
    out = []
    for g in G.values():
        tot = g["validos"] + g["brancos"] + g["nulos"]
        z = {"zona": g["zona"], "aptos": g["aptos"], "comparecimento": tot,
             "abstencao": max(0, g["aptosApurados"] - tot), "validos": g["validos"],
             "brancos": g["brancos"], "nulos": g["nulos"], "totalVotos": tot,
             "pctSecoes": _pct(g["apuradas"], g["urnas"]),
             "finalizado": g["urnas"] > 0 and g["apuradas"] >= g["urnas"],
             "_votos": dict(g["votos"])}
        if area == "interior":
            z["municipios"] = g["municipios"]
        z.update(duelo(z["_votos"], g["validos"]))
        out.append(z)
    return sorted(out, key=lambda z: z["zona"])


# ===========================================================================
# 3. ROTAS
# ===========================================================================

def cabecalho(cfg, cargo: int, turno: int, ap_estado, versao) -> dict:
    est = resumo_de(ap_estado)
    tem = ap_estado is not None
    st = ("sem-dados" if not tem else "finalizado" if est.get("finalizado") else "em-andamento")
    desat = False
    if tem and not est.get("finalizado") and est.get("pctSecoes", 0) > 0:
        try:
            idade = (datetime.now() - datetime.fromisoformat(ap_estado["ts"])).total_seconds()
            desat = idade > 300
        except Exception:
            pass
    return {"cargo": {"slug": "governador" if cargo == 3 else "presidente", "codigo": cargo,
                      "nome": NOME_CARGO[cargo], "vagas": 1, "proporcional": False},
            "turno": turno, "eleicao": eleicao(cfg, cargo, turno) if tem else None,
            "versao": versao, "status": st, "aviso": None, "inconsistente": False,
            "desatualizado": desat, "fonte": "central SESMT01 (banco do coletor, TSE)",
            "estado": {"pctSecoes": est.get("pctSecoes", 0),
                       "secoesTotalizadas": est.get("secoesTotalizadas", 0),
                       "secoesTotal": est.get("secoesTotal", 0),
                       "geradoEm": est.get("geradoEm"), "finalizado": bool(est.get("finalizado"))}}


def versao(b) -> int:
    r = b.um("SELECT MAX(id) m FROM apuracao")
    n = b.um("SELECT COUNT(*) n FROM bu_leitura")
    return int(r["m"] or 0) * 100000 + int(n["n"] or 0)


def visao(b, cfg, cargo: int, area: str, turno: int) -> dict:
    cd = eleicao(cfg, cargo, turno)
    ap_uf = ultima(b, cd, cargo, "uf", "am")
    out = cabecalho(cfg, cargo, turno, ap_uf, versao(b))
    if ap_uf is None:
        out.update(resumo={}, candidatos=[], abrangencia={"tipo": area})
        return out
    ap_cap = ultimas_mun(b, cd, cargo).get(CAPITAL)
    if area == "estado":
        out["abrangencia"] = {"tipo": "estado", "codigo": "uf", "nome": "Estado"}
        out["resumo"] = resumo_de(ap_uf)
        out["candidatos"] = ordenar([cand_de(v) for v in votos_da(b, ap_uf)])
        return out
    if area == "capital":
        out["abrangencia"] = {"tipo": "capital", "codigo": CAPITAL, "nome": "MANAUS"}
        out["resumo"] = resumo_de(ap_cap)
        out["candidatos"] = ordenar([cand_de(v) for v in votos_da(b, ap_cap)])
        zs = zonas_bu(territorio(b, cfg, turno), cargo, "capital")
        for z in zs:
            z.pop("_votos", None)
        out["zonas"], out["fonteZonas"] = zs, "soma dos boletins de urna lidos pela central"
        return out
    # interior = estado − capital (CALCULADO)
    rs_uf, rs_cap = resumo_de(ap_uf), resumo_de(ap_cap)
    out["abrangencia"] = {"tipo": "interior", "codigo": "interior", "nome": "Interior",
                          "municipios": 61, "calculado": "estado − Manaus"}
    out["resumo"] = subtrai(rs_uf, rs_cap)
    cap = {v["numero"]: v for v in votos_da(b, ap_cap)}
    cands = []
    for v in votos_da(b, ap_uf):
        c = cand_de(v)
        c["votos"] = c["votos"] - ((cap.get(v["numero"]) or {}).get("votos") or 0)
        c["pct"] = _pct(c["votos"], out["resumo"]["validos"])
        cands.append(c)
    out["candidatos"] = ordenar(cands)
    muns = []
    calhas: Dict[str, dict] = {}
    for mun, ap in ultimas_mun(b, cd, cargo).items():
        if mun == CAPITAL:
            continue
        rs = resumo_de(ap)
        vs = {v["numero"]: v["votos"] or 0 for v in votos_da(b, ap)
              if not (v.get("validade") or "").lower().startswith("anulad")}
        nome = (b.um("SELECT nome FROM municipio WHERE cd=?", (mun,)) or {"nome": mun})["nome"]
        calha = REF.get("calhas", {}).get(mun, "")
        m = {"codigo": mun, "nome": nome, "calha": calha, "aptos": rs["aptos"],
             "comparecimento": rs["comparecimento"], "abstencao": rs["abstencao"],
             "validos": rs["validos"], "brancos": rs["brancos"], "nulos": rs["nulos"],
             "totalVotos": rs["totalVotos"], "pctSecoes": rs["pctSecoes"],
             "finalizado": rs["finalizado"]}
        m.update(duelo(vs, rs["validos"]))
        muns.append(m)
        k = calhas.setdefault(calha, {"calha": calha, "municipios": 0, "aptos": 0,
                                       "comparecimento": 0, "abstencao": 0, "validos": 0,
                                       "brancos": 0, "nulos": 0, "totalVotos": 0, "_st": 0,
                                       "_sz": 0, "_v": defaultdict(int), "finalizado": True})
        k["municipios"] += 1
        for f in ("aptos", "comparecimento", "abstencao", "validos", "brancos", "nulos", "totalVotos"):
            k[f] += m[f]
        k["_st"] += rs["secoesTotal"]
        k["_sz"] += rs["secoesTotalizadas"]
        k["finalizado"] = k["finalizado"] and rs["finalizado"]
        for n, x in vs.items():
            k["_v"][n] += x
    out["municipios"] = sorted(muns, key=lambda m: norm(m["nome"]))
    cl = []
    for k in calhas.values():
        k["pctSecoes"] = _pct(k.pop("_sz"), k.pop("_st"))
        k.update(duelo(dict(k.pop("_v")), k["validos"]))
        cl.append(k)
    out["calhas"] = sorted(cl, key=lambda k: norm(k["calha"]))
    zs = zonas_bu(territorio(b, cfg, turno), cargo, "interior")
    for z in zs:
        z.pop("_votos", None)
    out["zonas"], out["fonteZonas"] = zs, "soma dos boletins de urna lidos pela central"
    return out


def candidato(b, cfg, cargo: int, numero: str, turno: int) -> Optional[dict]:
    cd = eleicao(cfg, cargo, turno)
    ap_uf = ultima(b, cd, cargo, "uf", "am")
    out = cabecalho(cfg, cargo, turno, ap_uf, versao(b))
    if ap_uf is None:
        return None
    vuf = {v["numero"]: v for v in votos_da(b, ap_uf)}
    if numero not in vuf:
        return None
    rs_uf = resumo_de(ap_uf)
    out["candidato"] = {k: v for k, v in cand_de(vuf[numero]).items()
                        if k not in ("votos", "pct", "anulado")}

    def pos(vs: Dict[str, int], validos: int) -> dict:
        o = sorted(vs.items(), key=lambda x: -x[1])
        p = next((i + 1 for i, (n, _) in enumerate(o) if n == numero), None)
        v = vs.get(numero, 0)
        return {"votos": v, "pct": _pct(v, validos), "posicao": p,
                "empate": bool(p and len(o) > 1 and o[0][1] == o[1][1] and p <= 2)}

    def vs_de(ap) -> Dict[str, int]:
        return {v["numero"]: v["votos"] or 0 for v in votos_da(b, ap)
                if not (v.get("validade") or "").lower().startswith("anulad")}

    muns_ap = ultimas_mun(b, cd, cargo)
    ap_cap = muns_ap.get(CAPITAL)
    v_uf, v_cap = vs_de(ap_uf), vs_de(ap_cap)
    rs_cap = resumo_de(ap_cap)
    v_int = {n: v_uf.get(n, 0) - v_cap.get(n, 0) for n in v_uf}
    out["estado"] = pos(v_uf, rs_uf["validos"])
    out["capital"] = pos(v_cap, rs_cap.get("validos", 0))
    out["interior"] = pos(v_int, rs_uf["validos"] - rs_cap.get("validos", 0))
    muns, calhas = [], defaultdict(lambda: {"v": defaultdict(int), "val": 0, "st": 0, "sz": 0})
    for mun, ap in muns_ap.items():
        if mun == CAPITAL:
            continue
        rs, vs = resumo_de(ap), vs_de(ap)
        nome = (b.um("SELECT nome FROM municipio WHERE cd=?", (mun,)) or {"nome": mun})["nome"]
        m = dict(pos(vs, rs["validos"]), codigo=mun, nome=nome, pctSecoes=rs["pctSecoes"])
        muns.append(m)
        k = calhas[REF.get("calhas", {}).get(mun, "")]
        for n, x in vs.items():
            k["v"][n] += x
        k["val"] += rs["validos"]
        k["st"] += rs["secoesTotal"]
        k["sz"] += rs["secoesTotalizadas"]
    out["municipios"] = sorted(muns, key=lambda m: norm(m["nome"]))
    out["calhas"] = sorted([dict(pos(dict(k["v"]), k["val"]), calha=c, pctSecoes=_pct(k["sz"], k["st"]))
                            for c, k in calhas.items()], key=lambda x: norm(x["calha"]))
    T = territorio(b, cfg, turno)
    for area, campo in (("capital", "zonas"), ("interior", "zonasInterior")):
        out[campo] = [dict(pos(z["_votos"], z["validos"]), zona=z["zona"], pctSecoes=z["pctSecoes"])
                      for z in zonas_bu(T, cargo, area)]
    out["fonteZonas"] = "soma dos boletins de urna lidos pela central"
    return out


def locais_votacao(b, area: str) -> dict:
    """Cadastro de colégios do TSE (tabelas local_votacao + secao_local), sem votos."""
    r = b.um("SELECT ano, turno FROM local_votacao ORDER BY ano DESC, turno DESC LIMIT 1")
    if not r:
        return {"area": area, "disponivel": False, "locais": []}
    ano, tl = r["ano"], r["turno"]
    agg: Dict[tuple, dict] = {}
    for s in b.query("""SELECT mun, zona, local, principal, aptos_estadual, aptos_secao, secao_principal
                        FROM secao_local WHERE ano=? AND turno=?""", (ano, tl)):
        a = agg.setdefault((s["mun"], s["zona"], s["local"]), {"secoes": 0, "eleitores": 0})
        if s["principal"]:
            a["secoes"] += 1
        a["eleitores"] += (s["aptos_estadual"] or
                           (0 if (s["principal"] == 0 and s["secao_principal"]) else s["aptos_secao"] or 0))
    locais = []
    for L in b.query("SELECT * FROM local_votacao WHERE ano=? AND turno=?", (ano, tl)):
        if (area == "capital") != (L["mun"] == CAPITAL):
            continue
        a = agg.get((L["mun"], L["zona"], L["local"]), {"secoes": 0, "eleitores": 0})
        locais.append({"local": L["local"], "zona": L["zona"], "codigo": L["mun"],
                       "municipio": L["mun_nome"], "nome": L["nome"], "bairro": L["bairro"],
                       "secoes": a["secoes"], "eleitores": a["eleitores"], "endereco": L["endereco"]})
    return {"area": area, "disponivel": True,
            "fonte": f"Cadastro de Locais de Votação do TSE ({ano}, {tl}º turno), banco da central",
            "totais": {"locais": len(locais), "secoes": sum(l["secoes"] for l in locais),
                       "eleitores": sum(l["eleitores"] for l in locais),
                       "zonas": len({l["zona"] for l in locais}),
                       "municipios": len({l["codigo"] for l in locais})},
            "locais": locais}


def locais_votos(b, cfg, cargo: int, turno: int, area: str) -> Optional[dict]:
    """Votos por colégio = soma dos boletins das seções do colégio (CONTRATO_API.md)."""
    T = territorio(b, cfg, turno)
    if T is None:
        return {"turno": turno, "area": area, "geradoEm": None, "locais": []}
    out = []
    for u in T.agregar("colegio"):
        if (area == "capital") != (u["mun"] == CAPITAL):
            continue
        c = u["cargos"].get(cargo)
        if not c:
            continue
        out.append({"local": u.get("local"), "zona": u.get("zona"), "codigo": u["mun"],
                    "municipio": u.get("mun_nome"), "nome": u.get("nome"), "bairro": u.get("bairro"),
                    "secoesTotal": u["urnas"], "secoesTotalizadas": u["urnas_apuradas"],
                    "aptos": u["aptos"], "comparecimento": c["validos"] + c["brancos"] + c["nulos"],
                    "validos": c["validos"], "brancos": c["brancos"], "nulos": c["nulos"],
                    "candidatos": {x["n"]: x["v"] for x in c["cand"]}})
    ult = b.um("SELECT MAX(lido_em) m FROM bu_leitura")
    return {"turno": turno, "area": area, "geradoEm": _iso_mao(ult["m"] if ult else None),
            "fonte": "soma dos boletins de urna lidos pela central", "locais": out}


def marcos(b, cfg, cargo: int, turno: int, numero: str) -> dict:
    """Marcos oficiais (armadilha 5), cada um com o retrato da totalização naquele minuto."""
    cd = eleicao(cfg, cargo, turno)
    lista = []
    if cd:
        for r in b.query("SELECT * FROM marco WHERE cargo=? AND (cd_eleicao=? OR tipo LIKE ?) "
                         "ORDER BY ts, id", (cargo, cd, f"virada:{cargo}:%")):
            tipo = r["tipo"] or ""
            if tipo.startswith("empate:"):
                continue
            regra = next((m for m in MARCOS if tipo.startswith(m[0])), None)
            if not regra:
                continue
            ap = b.um("""SELECT * FROM apuracao WHERE cd_eleicao=? AND cargo=? AND abr_cd='am'
                         AND abr_tipo='uf' AND ts<=? ORDER BY ts DESC, id DESC LIMIT 1""",
                      (cd, cargo, r["ts"]))
            m = {"id": f"m{r['id']}", "tse": _iso_mao(r["ts"]),
                 "titulo": regra[2] or (r["descricao"] or "").split(": ", 1)[-1].strip("*"),
                 "pct": ap["pct_secoes_totalizadas"] if ap else None}
            if ap:
                vs = sorted(((v["numero"], v["votos"] or 0) for v in votos_da(b, ap)
                             if not (v.get("validade") or "").lower().startswith("anulad")),
                            key=lambda x: -x[1])
                val = ap["votos_validos"] or 0
                eu = next((v for n, v in vs if n == numero), None)
                outro = next((v for n, v in vs if n != numero), None)
                if eu is not None:
                    m["eu"] = _pct(eu, val)
                    m["dif"] = eu - (outro or 0)
                m["lider"] = vs[0][0] if vs else None
            lista.append(m)
    return {"turno": turno, "fonte": "Marcos registrados pela central durante a apuração "
                                     "(horário da central).", "marcos": lista}


def brasil(b, cfg, turno: int) -> dict:
    cd = eleicao(cfg, 1, turno)
    ap_br = ultima(b, cd, 1, "br", "br")
    ap_am = ultima(b, cd, 1, "uf", "am")
    out = cabecalho(cfg, 1, turno, ap_am, versao(b))
    if ap_br is None:
        out.update(presidente={"candidatos": []}, ufs=[], mapaPresidente=[])
        return out
    rs = resumo_de(ap_br)
    out["presidente"] = {"abrangencia": {"tipo": "brasil", "codigo": "br", "nome": "Brasil"},
                         "resumo": rs, "candidatos": ordenar([cand_de(v) for v in votos_da(b, ap_br)]),
                         "estado": {"pctSecoes": rs["pctSecoes"], "secoesTotalizadas": rs["secoesTotalizadas"],
                                    "secoesTotal": rs["secoesTotal"], "geradoEm": rs["geradoEm"],
                                    "finalizado": rs["finalizado"]}}
    out["ufs"], out["mapaPresidente"] = [], []
    if ap_am is not None:                                        # armadilha 3: só o AM
        ra = resumo_de(ap_am)
        vs = {v["numero"]: v["votos"] or 0 for v in votos_da(b, ap_am)}
        out["ufs"].append({"uf": "am", "nome": "Amazonas", "eleitores": ra["aptos"],
                           "secoesTotal": ra["secoesTotal"], "secoesTotalizadas": ra["secoesTotalizadas"],
                           "pctSecoes": ra["pctSecoes"]})
        row = {"uf": "am", "nome": "Amazonas", "aptos": ra["aptos"], "comparecimento": ra["comparecimento"],
               "abstencao": ra["abstencao"], "validos": ra["validos"], "brancos": ra["brancos"],
               "nulos": ra["nulos"], "totalVotos": ra["totalVotos"], "pctSecoes": ra["pctSecoes"],
               "finalizado": ra["finalizado"]}
        row.update(duelo(vs, ra["validos"]))
        out["mapaPresidente"].append(row)
    return out


def governador_uf(b, cfg, uf: str, turno: int) -> dict:
    cd = eleicao(cfg, 3, turno)
    tipo = "uf" if uf == "am" else "ufbr"                      # armadilha 1
    ap = ultima(b, cd, 3, tipo, uf)
    if ap is None:
        return {"uf": uf, "nome": UFS.get(uf, uf), "turno": turno, "disponivel": False,
                "candidatos": []}
    rs = resumo_de(ap)
    return {"cargo": {"slug": "governador", "codigo": 3, "nome": "Governador"}, "uf": uf,
            "nome": UFS.get(uf, uf), "turno": turno, "eleicao": cd, "disponivel": True,
            "abrangencia": {"tipo": "uf", "codigo": uf, "nome": UFS.get(uf, uf)}, "resumo": rs,
            "candidatos": ordenar([cand_de(v) for v in votos_da(b, ap)]),
            "estado": {"pctSecoes": rs["pctSecoes"], "secoesTotalizadas": rs["secoesTotalizadas"],
                       "secoesTotal": rs["secoesTotal"], "geradoEm": rs["geradoEm"],
                       "finalizado": rs["finalizado"]}}


def meta(b, cfg) -> dict:
    cargos = []
    for slug, cargo in CARGOS.items():
        ts = []
        for t in (1, 2):
            cd = eleicao(cfg, cargo, t)
            ap = ultima(b, cd, cargo, "uf", "am")
            rs = resumo_de(ap)
            ts.append({"turno": t, "eleicao": cd,
                       "status": "sem-dados" if ap is None else
                       ("finalizado" if rs["finalizado"] else "em-andamento"),
                       "pctSecoes": rs.get("pctSecoes", 0), "geradoEm": rs.get("geradoEm"),
                       "finalizado": bool(rs.get("finalizado"))})
        cargos.append({"slug": slug, "codigo": cargo, "nome": NOME_CARGO[cargo], "turnos": ts})
    return {"modo": "central", "uf": "AM", "versao": versao(b), "cargos": cargos,
            "fonte": "central SESMT01", "ipRede": ip_rede(),
            "geradoEm": _iso_mao(datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))}


def ip_rede() -> Optional[str]:
    """IP desta máquina na rede (a mesa usa para montar o link do celular)."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def responder(b, cfg: dict, partes: List[str], q: dict) -> Tuple[object, int]:
    """partes = caminho depois de /api/, já separado. Devolve (json, http)."""
    turno = 1 if str(q.get("turno")) == "1" else 2
    r0 = partes[0]
    if r0 == "meta":
        return meta(b, cfg), 200
    if r0 == "locais-votacao" and len(partes) == 2 and partes[1] in ("capital", "interior"):
        return locais_votacao(b, partes[1]), 200
    if r0 == "brasil":
        if len(partes) == 1:
            return brasil(b, cfg, turno), 200
        return governador_uf(b, cfg, partes[1].lower(), turno), 200
    if r0 in CARGOS and len(partes) >= 2:
        cargo = CARGOS[r0]
        if partes[1] in ("estado", "capital", "interior"):
            return visao(b, cfg, cargo, partes[1], turno), 200
        if partes[1] == "candidato" and len(partes) == 3:
            r = candidato(b, cfg, cargo, partes[2], turno)
            return (r, 200) if r else ({"erro": "candidato sem dados neste turno"}, 404)
        if partes[1] == "locais":
            area = q.get("area") if q.get("area") in ("capital", "interior") else "capital"
            return locais_votos(b, cfg, cargo, turno, area), 200
        if partes[1] == "marcos":
            return marcos(b, cfg, cargo, turno, str(q.get("candidato") or "55")), 200
    return {"erro": "rota desconhecida"}, 404


# ===========================================================================
# 4. SSE e FOTOS (precisam do socket do handler)
# ===========================================================================

def stream(handler, abrir_banco, duracao: int = 600):
    """SSE: 'hello' na conexão e 'update' quando a versão muda (confere a cada 5 s).
    Fecha depois de `duracao` s; o navegador reconecta sozinho (retry)."""
    handler.send_response(200)
    handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    ult = None
    fim = time.time() + duracao
    try:
        handler.wfile.write(b"retry: 5000\n\n")
        while time.time() < fim:
            b = abrir_banco()
            try:
                v = versao(b)
            finally:
                b.fechar()
            if v != ult:
                ev = "hello" if ult is None else "update"
                handler.wfile.write(f"event: {ev}\ndata: {json.dumps({'versao': v})}\n\n".encode())
                handler.wfile.flush()
                ult = v
            else:
                handler.wfile.write(b": ping\n\n")
                handler.wfile.flush()
            time.sleep(5)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
        pass


def foto(handler, cfg: dict, sqcand: str):
    """Foto do candidato: do disco (ENTRADA/FOTOS) ou do TSE, que fica guardada."""
    sq = "".join(ch for ch in sqcand if ch.isdigit())
    caminho = os.path.join(DIR_FOTOS, f"{sq}.jpeg")
    dado = None
    if sq and os.path.exists(caminho):
        with open(caminho, "rb") as f:
            dado = f.read()
    elif sq:
        import api_tse as A
        base = A.ROTAS.get("base", "https://resultados.tse.jus.br")
        ciclo = cfg.get("ciclo", "ele2026")
        eles = [eleicao(cfg, c, t) for t in (2, 1) for c in (3, 1)]
        try:
            s = A.sessao_navegador(15)
        except Exception:
            s = None
        for ele in [e for e in eles if e]:
            for uf in ("am", "br"):
                url = f"{base}/oficial/{ciclo}/{ele}/fotos/{uf}/{sq}.jpeg"
                try:
                    if s is not None:
                        r = s.get(url)
                        ok, corpo = r.status_code == 200, r.content
                    else:
                        import urllib.request
                        with urllib.request.urlopen(url, timeout=15) as r:
                            ok, corpo = r.status == 200, r.read()
                except Exception:
                    continue
                if ok and corpo[:2] == b"\xff\xd8":
                    dado = corpo
                    os.makedirs(DIR_FOTOS, exist_ok=True)
                    with open(caminho, "wb") as f:
                        f.write(dado)
                    break
            if dado:
                break
    if not dado:
        handler.send_response(404)
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return
    handler.send_response(200)
    handler.send_header("Content-Type", "image/jpeg")
    handler.send_header("Cache-Control", "max-age=86400")
    handler.send_header("Content-Length", str(len(dado)))
    handler.end_headers()
    handler.wfile.write(dado)

"""Participação de cada empresa em cada campo (Relação de Concessionários da ANP)."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .precos import norm

# Nomes comerciais: subsidiárias do mesmo grupo somadas
GRUPOS = [
    (r"petrobras", "Petrobras"), (r"prio|petro rio", "PRIO"), (r"3r|brava|enauta", "Brava"),
    (r"totalenergies", "TotalEnergies"), (r"shell", "Shell"), (r"equinor", "Equinor"),
    (r"repsol", "Repsol Sinopec"), (r"petrogal|galp", "Galp"), (r"cnooc", "CNOOC"), (r"cnpc|cnodc", "CNPC"),
    (r"petronas", "Petronas"), (r"qatar", "QatarEnergy"), (r"exxon", "ExxonMobil"), (r"karoon", "Karoon"),
    (r"perenco", "Perenco"), (r"trident", "Trident"), (r"\bbw\b", "BW Energy"), (r"ongc", "ONGC"),
    (r"ecopetrol", "Ecopetrol"), (r"panoro", "Panoro"),
]


def grupo(nome: str) -> str:
    n = norm(nome)
    for padrao, g in GRUPOS:
        if re.search(padrao, n):
            return g
    return str(nome).strip()


def carregar(pasta: Path) -> pd.DataFrame | None:
    arqs = sorted(Path(pasta).rglob("*.csv")) if Path(pasta).exists() else []
    if not arqs:
        return None
    c = pd.read_csv(arqs[0], sep=";", encoding="latin-1", dtype=str)
    c.columns = [norm(x) for x in c.columns]
    if "ambiente" in c.columns:   # só contratos marítimos (há nomes curtos repetidos em terra)
        c = c[c["ambiente"].astype(str).str.strip().str.lower().str.startswith("mar")]
    col = {k: [x for x in c.columns if k in x][0] for k in ("nome fantasia", "nome", "% participa")}
    col["nome"] = [x for x in c.columns if x == "nome"][0]
    out = pd.DataFrame({
        "contrato": c[col["nome fantasia"]].str.strip(),
        "empresa_bruta": c[col["nome"]].str.strip(),
        "pct": pd.to_numeric(c[col["% participa"]].str.replace(".", "", regex=False).str.replace(",", "."),
                             errors="coerce") / 100,
    })
    out["operador"] = out.empresa_bruta.str.contains(r"\(Operador\)", regex=True)
    out["empresa"] = out.empresa_bruta.str.replace(r"\(Operador\)\s*-\s*", "", regex=True).map(grupo)
    return out.groupby(["contrato", "empresa"]).agg(pct=("pct", "sum"), operador=("operador", "max")).reset_index()


def participacoes_base(raiz: Path, pasta: Path) -> pd.DataFrame | None:
    """Tabela campo × empresa com a participação (0–1) no CONTRATO, segundo a Relação de Concessionários."""
    conc = carregar(pasta)
    f = Path(raiz) / "config" / "campo_contrato.csv"
    if conc is None or not f.exists():
        return None
    mapa = pd.read_csv(f, comment="#")
    linhas = []
    for _, r in mapa.iterrows():
        if r.contrato == "UNIAO":
            linhas.append(dict(campo=r.campo, empresa="União (PPSA)", pct=1.0, operador=False))
            continue
        sub = conc[conc.contrato.map(norm) == norm(r.contrato)]
        for _, s in sub.iterrows():
            linhas.append(dict(campo=r.campo, empresa=s.empresa, pct=s.pct, operador=bool(s.operador)))
    return pd.DataFrame(linhas)


def carregar_aip(raiz: Path) -> pd.DataFrame | None:
    """Participações por jazida definidas em Acordos de Individualização da Produção, com data de vigência."""
    f = Path(raiz) / "config" / "participacoes_aip.csv"
    if not f.exists():
        return None
    a = pd.read_csv(f, comment="#", parse_dates=["desde"])
    a["operador"] = a.operador.astype(str).str.lower().eq("true")
    return a


def aplicar_aip(base: pd.DataFrame, aip: pd.DataFrame | None) -> pd.DataFrame:
    """Participações vigentes hoje: o AIP substitui a participação do contrato nos campos que ele cobre."""
    if aip is None or aip.empty:
        return base
    return pd.concat([base[~base.campo.isin(aip.campo)], aip.drop(columns="desde")], ignore_index=True)


def participacoes_campo(raiz: Path, pasta: Path) -> pd.DataFrame | None:
    """Tabela campo × empresa com a participação vigente (0–1) e a operadora."""
    base = participacoes_base(raiz, pasta)
    return None if base is None else aplicar_aip(base, carregar_aip(raiz))


def operador_por_unidade(part: pd.DataFrame, vol: pd.DataFrame) -> dict:
    """Operadora da unidade = operadora do subcampo com maior produção nos últimos 12 meses."""
    ult = vol.mes.max()
    rec = vol[vol.mes > ult - pd.DateOffset(months=12)].groupby(["unidade", "campo"]).oleo_m3.sum().reset_index()
    ops = part[part.operador].drop_duplicates("campo").set_index("campo").empresa
    res = {}
    for u, g in rec.groupby("unidade"):
        for c in g.sort_values("oleo_m3", ascending=False).campo:
            if c in ops.index:
                res[u] = ops[c]
                break
    return res


def liquida_historica(vol: pd.DataFrame, part: pd.DataFrame, aip: pd.DataFrame | None = None) -> pd.DataFrame:
    """Produção de petróleo (bbl/dia) da parte de cada empresa, por mês.
    part = participações do contrato; nos campos com AIP, a partir da vigência vale a participação do acordo."""
    if aip is not None and not aip.empty:
        desde = aip.groupby("campo").desde.min()
        pos = vol.campo.map(desde).le(vol.mes).fillna(False).astype(bool)
        v = pd.concat([vol[~pos].merge(part, on="campo", how="left"),
                       vol[pos].merge(aip.drop(columns="desde"), on="campo", how="left")], ignore_index=True)
    else:
        v = vol.merge(part, on="campo", how="left")
    v["empresa"] = v.empresa.fillna("Outras")
    v["pct"] = v.pct.fillna(1.0)
    v["oleo_liq"] = v.oleo_bpd * v.pct
    return v.groupby(["empresa", "mes"]).oleo_liq.sum().reset_index()


def liquida_prevista(por_u: pd.DataFrame, vol: pd.DataFrame, part: pd.DataFrame) -> pd.DataFrame:
    """Reparte a previsão de cada unidade pelos subcampos (mix dos últimos 3 meses) e pelas empresas.
    3 meses: reflete a configuração atual (ex.: subcampos unificados quando um AIP entra em vigor)."""
    ult = vol.mes.max()
    rec = vol[vol.mes > ult - pd.DateOffset(months=3)]
    mix = rec.groupby(["unidade", "campo"]).oleo_m3.sum()
    mix = (mix / mix.groupby(level=0).transform("sum")).rename("mix").reset_index()
    p = por_u.merge(mix, on="unidade", how="left").merge(part, on="campo", how="left")
    p["empresa"] = p.empresa.fillna("Outras")
    p["mix"] = p["mix"].fillna(1.0)
    p["pct"] = p.pct.fillna(1.0)
    w = p["mix"] * p["pct"]
    cols = {"producao_p50": "producao_liq", "receita_p50": "receita_liq", "royalties_p50": "royalties_liq",
            "pe_estimada": "pe_liq"}
    for a, b in cols.items():
        p[b] = p[a] * w
    return p.groupby(["empresa", "mes"])[list(cols.values())].sum().reset_index()


def pesos_unidade(vol: pd.DataFrame, part: pd.DataFrame) -> pd.DataFrame:
    """Parte de cada empresa em cada unidade: mix dos subcampos nos últimos 3 meses × participação."""
    ult = vol.mes.max()
    rec = vol[vol.mes > ult - pd.DateOffset(months=3)]
    mix = rec.groupby(["unidade", "campo"]).oleo_m3.sum()
    mix = (mix / mix.groupby(level=0).transform("sum")).rename("mix").reset_index()
    p = mix.merge(part, on="campo", how="left")
    p["empresa"] = p.empresa.fillna("Outras")
    p["peso"] = p["mix"].fillna(0.0) * p.pct.fillna(1.0)
    return p.groupby(["unidade", "empresa"]).peso.sum().reset_index()

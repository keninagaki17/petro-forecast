"""Preços e participações governamentais publicados pela ANP, câmbio e Brent."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

M3_BBL = 6.28981


def norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"\s+", " ", s)


def _num(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip()
    s = s.where(~s.str.contains(","), s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(s, errors="coerce")


def _ler(f: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(f, sep=";", encoding=enc, dtype=str)
            df.columns = [norm(c) for c in df.columns]
            return df
        except UnicodeDecodeError:
            continue
    raise ValueError(f"não consegui ler {f}")


def _mes_excel(s: pd.Series) -> pd.Series:
    v = pd.to_numeric(s, errors="coerce")
    ok = v.notna()
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    out[ok] = pd.to_datetime("1899-12-30") + pd.to_timedelta(v[ok], unit="D")
    # alguns arquivos podem trazer a data como texto
    out[~ok] = pd.to_datetime(s[~ok], dayfirst=True, errors="coerce")
    return out.dt.to_period("M").dt.to_timestamp()


def _precos_pasta(pasta: Path) -> pd.DataFrame:
    partes = []
    for f in sorted(Path(pasta).glob("*.csv")):
        df = _ler(f)
        col = [c for c in df.columns if c.startswith("pre")]
        if not col or "campo" not in df.columns:
            continue
        partes.append(pd.DataFrame({"mes": _mes_excel(df["data"]), "campo_n": df["campo"].map(norm),
                                    "preco": _num(df[col[0]])}))
    if not partes:
        return pd.DataFrame(columns=["campo_n", "mes", "preco"])
    p = pd.concat(partes).dropna()
    return p.groupby(["campo_n", "mes"])["preco"].mean().reset_index()


def precos_petroleo(pg: Path) -> pd.DataFrame:
    """Preço de referência (2018+) e preço mínimo (até 2017), R$/m³ por campo e mês."""
    ref = _precos_pasta(pg / "preco-referencia-petroleo")
    minimo = _precos_pasta(pg / "preco-minimo-petroleo")
    p = pd.concat([ref.assign(o=0), minimo.assign(o=1)]).sort_values("o")
    return p.drop_duplicates(["campo_n", "mes"]).drop(columns="o")


def precos_gas(pg: Path) -> pd.DataFrame:
    return _precos_pasta(pg / "preco-referencia-gas-natural")


def royalties_nacional(pg: Path) -> pd.DataFrame:
    """Total de royalties distribuídos (soma de todos os beneficiários) por mês de competência."""
    partes = []
    for f in sorted(pg.rglob("royalties*uniao*.csv")):
        df = _ler(f)
        if "competencia" not in df.columns:
            continue
        vals = df.drop(columns=[c for c in ("competencia", "caixa") if c in df.columns]).apply(_num)
        partes.append(pd.DataFrame({"mes": _mes_excel(df["competencia"]), "royalties": vals.sum(1)}))
    r = pd.concat(partes).dropna()
    return r.groupby("mes")["royalties"].max().reset_index()


def pe_por_campo(pg: Path) -> pd.DataFrame:
    f = pg / "participacao-especial" / "pe_campo.csv"
    if not f.exists():
        return pd.DataFrame(columns=["trimestre", "campo_n", "pe"])
    df = _ler(f)
    return pd.DataFrame({"trimestre": _mes_excel(df["competencia"]), "campo_n": df["campo"].map(norm),
                         "pe": _num(df["valor"])}).dropna()


def ptax(pasta_mercado: Path) -> pd.Series:
    p = pd.read_csv(pasta_mercado / "ptax_mensal.csv", parse_dates=["data"])
    return p.set_index(p["data"].dt.to_period("M").dt.to_timestamp())["ptax_venda_media"]


def brent(raiz: Path, pasta_mercado: Path) -> pd.DataFrame:
    """Brent mensal: arquivo baixado (se houver) + config/brent_mensal.csv (realizado e cenário base)."""
    cfg = pd.read_csv(raiz / "config" / "brent_mensal.csv", comment="#", parse_dates=["mes"])
    f = pasta_mercado / "brent_mensal.csv"
    if f.exists():
        b = pd.read_csv(f, parse_dates=["data"]).rename(columns={"data": "mes"})
        b["mes"] = b["mes"].dt.to_period("M").dt.to_timestamp()
        b["tipo"] = "realizado"
        cfg = pd.concat([b[["mes", "brent_usd", "tipo"]], cfg[~cfg.mes.isin(b.mes)]])
    return cfg.sort_values("mes").drop_duplicates("mes", keep="first").reset_index(drop=True)

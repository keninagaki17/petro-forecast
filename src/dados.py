"""
Leitura e padronização dos dados públicos.

A ANP já publicou a produção por poço em dois layouts:
  - antigo: "Período" (AAAA/MM), volumes em bbl/dia e gás em Mm³/dia
  - 2026+:  "Mês/Ano" (MM/AAAA), volumes mensais em m³
Este módulo reconhece as colunas pelo nome e converte tudo para uma
tabela única por poço e mês, com petróleo em bbl/dia.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

M3_PARA_BBL = 6.28981


# --------------------------------------------------------------------------
# Utilidades de leitura
# --------------------------------------------------------------------------
def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    t = t.lower().replace("³", "3")
    return re.sub(r"\s+", " ", t).strip()


def para_numero(serie: pd.Series) -> pd.Series:
    """Converte números no padrão brasileiro ("1.234,56") ou internacional."""
    if pd.api.types.is_numeric_dtype(serie):
        return serie.astype(float)
    s = serie.astype(str).str.strip()
    tem_virgula = s.str.contains(",", regex=False)
    s = s.where(~tem_virgula, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(s, errors="coerce")


def para_mes(serie: pd.Series) -> pd.Series:
    """Aceita AAAA/MM, MM/AAAA, AAAA-MM, DD/MM/AAAA e datas já convertidas."""
    if pd.api.types.is_datetime64_any_dtype(serie):
        return serie.dt.to_period("M").dt.to_timestamp()
    s = serie.astype(str).str.strip()
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    formatos = [
        (r"^\d{4}[/-]\d{1,2}$", "%Y/%m"),
        (r"^\d{1,2}[/-]\d{4}$", "%m/%Y"),
        (r"^\d{1,2}/\d{1,2}/\d{4}", "%d/%m/%Y"),
        (r"^\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
    ]
    for padrao, fmt in formatos:
        mask = s.str.match(padrao) & out.isna()
        if mask.any():
            valores = s[mask].str.replace("-", "/", regex=False) if fmt in ("%Y/%m", "%m/%Y") else s[mask]
            valores = valores.str.slice(0, 10)
            out[mask] = pd.to_datetime(valores, format=fmt, errors="coerce")
    return out.dt.to_period("M").dt.to_timestamp()


def ler_csv_anp(caminho: Path) -> pd.DataFrame:
    """Lê os CSVs da ANP. Alguns anos (ex.: 2019–2021) vêm com cada linha de dados
    inteira entre aspas ("2019,01/2019,...,""624,251"",..."); aqui isso é desfeito."""
    import csv
    import io
    bruto = Path(caminho).read_bytes()
    for enc in ("utf-8-sig", "latin-1"):
        try:
            texto = bruto.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    linhas = texto.splitlines()
    if not linhas:
        raise ValueError(f"{caminho.name} está vazio")
    cab = linhas[0]
    sep = ";" if cab.count(";") > cab.count(",") else ","
    corrigidas = [cab]
    for ln in linhas[1:]:
        if len(ln) > 1 and ln[0] == '"' and ln[-1] == '"' and ln.count(sep) >= cab.count(sep):
            ln = ln[1:-1].replace('""', '"')
        corrigidas.append(ln)
    df = pd.read_csv(io.StringIO("\n".join(corrigidas)), sep=sep, dtype=str, low_memory=False,
                     quoting=csv.QUOTE_MINIMAL)
    if df.shape[1] <= 3:
        raise ValueError(f"Não consegui ler {caminho.name}")
    return df


# --------------------------------------------------------------------------
# Produção por poço
# --------------------------------------------------------------------------
def _achar(cols: dict[str, str], *, contem: tuple[str, ...], exclui: tuple[str, ...] = (),
           exato: tuple[str, ...] = ()) -> str | None:
    for norm, original in cols.items():
        if norm in exato:
            return original
    for norm, original in cols.items():
        if all(c in norm for c in contem) and not any(e in norm for e in exclui):
            return original
    return None


def _volume_bbl_dia(df: pd.DataFrame, col: str, dias: pd.Series) -> pd.Series:
    """Converte uma coluna de volume líquido para bbl/dia, olhando a unidade no nome."""
    n = normalizar(col)
    v = para_numero(df[col]).fillna(0.0)
    if "bbl" in n:
        return v if ("/d" in n or "dia" in n) else v / dias
    if "m3" in n:
        v = v * M3_PARA_BBL
        return v if ("/d" in n or "dia" in n) else v / dias
    return v  # sem unidade explícita: assume bbl/dia


def _gas_mil_m3_dia(df: pd.DataFrame, col: str, dias: pd.Series) -> pd.Series:
    n = normalizar(col)
    v = para_numero(df[col]).fillna(0.0)
    if "mm3" in n or "mil m3" in n:  # Mm³ = mil m³ no padrão da ANP
        return v if ("/d" in n or "dia" in n) else v / dias
    if "m3" in n:
        v = v / 1000.0
        return v if ("/d" in n or "dia" in n) else v / dias
    return v


def padronizar_producao(df: pd.DataFrame, origem: str = "") -> pd.DataFrame:
    cols = {normalizar(c): c for c in df.columns}

    c_periodo = _achar(cols, contem=("periodo",), exclui=("carga",)) or \
        _achar(cols, contem=("mes/ano",)) or _achar(cols, contem=("data",), exato=("data",))
    c_poco = _achar(cols, contem=("poco", "anp")) or \
        _achar(cols, contem=("poco",), exclui=("operador", "tipo", "categoria"))
    c_campo = _achar(cols, contem=("campo",), exato=("campo",))
    c_operador = _achar(cols, contem=("operador",), exclui=("poco",), exato=("operador",))
    c_bacia = _achar(cols, contem=("bacia",))
    c_inst = _achar(cols, contem=("instalacao",), exclui=("tipo",))
    c_horas = _achar(cols, contem=("tempo", "producao"))

    faltando = [n for n, c in [("período", c_periodo), ("poço", c_poco), ("campo", c_campo)] if c is None]
    if faltando:
        raise ValueError(f"{origem}: colunas não encontradas: {faltando}. Colunas: {list(df.columns)}")

    out = pd.DataFrame({
        "mes": para_mes(df[c_periodo]),
        "poco": df[c_poco].astype(str).str.strip(),
        "campo": df[c_campo].astype(str).str.strip().str.upper(),
        "operador": df[c_operador].astype(str).str.strip() if c_operador else "N/D",
        "bacia": df[c_bacia].astype(str).str.strip() if c_bacia else "N/D",
        "instalacao": df[c_inst].astype(str).str.strip() if c_inst else "N/D",
    })
    dias = out["mes"].dt.days_in_month.astype(float)

    # Petróleo = óleo + condensado
    c_petroleo = _achar(cols, contem=("petroleo",), exclui=("preco",))
    c_oleo = _achar(cols, contem=("oleo",), exclui=("preco",))
    c_cond = _achar(cols, contem=("condensado",))
    if c_petroleo:
        out["petroleo_bpd"] = _volume_bbl_dia(df, c_petroleo, dias).values
    else:
        oleo = _volume_bbl_dia(df, c_oleo, dias) if c_oleo else 0.0
        cond = _volume_bbl_dia(df, c_cond, dias) if c_cond else 0.0
        out["petroleo_bpd"] = np.asarray(oleo + cond, dtype=float)

    c_gas_total = _achar(cols, contem=("gas", "total"))
    if c_gas_total:
        out["gas_mil_m3d"] = _gas_mil_m3_dia(df, c_gas_total, dias).values
    else:
        gas_cols = [orig for norm, orig in cols.items()
                    if "gas" in norm and "royalt" not in norm and "queim" not in norm
                    and "inje" not in norm and "consum" not in norm]
        out["gas_mil_m3d"] = sum((_gas_mil_m3_dia(df, c, dias) for c in gas_cols), 0.0) if gas_cols else 0.0

    c_agua = _achar(cols, contem=("agua",), exclui=("inje",))
    out["agua_bpd"] = _volume_bbl_dia(df, c_agua, dias).values if c_agua else np.nan

    if c_horas:
        out["horas"] = para_numero(df[c_horas]).values
    else:
        out["horas"] = np.nan

    out = out.dropna(subset=["mes"])
    out = out[~out["campo"].isin(["", "NAN", "NONE"])]
    return out


def carregar_producao(pasta: Path, desde: int | None = None) -> pd.DataFrame:
    arquivos = sorted(Path(pasta).rglob("*.csv"))
    if not arquivos:
        raise FileNotFoundError(f"Nenhum CSV de produção em {pasta}. Rode coleta_dados.py antes.")
    partes = []
    for a in arquivos:
        try:
            partes.append(padronizar_producao(ler_csv_anp(a), a.name))
            print(f"  ok   {a.name}")
        except ValueError as e:
            print(f"  pulei {a.name}: {e}")
    base = pd.concat(partes, ignore_index=True)
    if desde:
        base = base[base["mes"].dt.year >= desde]
    # Arquivos podem se sobrepor (ex.: pré-sal é subconjunto do mar): fica 1 linha por poço/mês
    base = (base.sort_values("petroleo_bpd")
                .drop_duplicates(["poco", "mes"], keep="last")
                .sort_values(["campo", "poco", "mes"])
                .reset_index(drop=True))
    return base


def agregar_por_campo(pocos: pd.DataFrame) -> pd.DataFrame:
    """Tabela campo × mês com volumes e indicadores operacionais."""
    p = pocos.copy()
    p["ativo"] = (p["petroleo_bpd"] > 0).astype(int)
    primeiro_mes = p[p["ativo"] == 1].groupby("poco")["mes"].min().rename("mes_inicio_poco")
    p = p.join(primeiro_mes, on="poco")
    p["poco_novo"] = (p["mes"] == p["mes_inicio_poco"]).astype(int)

    g = p.groupby(["campo", "mes"])
    campo = g.agg(
        petroleo_bpd=("petroleo_bpd", "sum"),
        gas_mil_m3d=("gas_mil_m3d", "sum"),
        agua_bpd=("agua_bpd", "sum"),
        pocos_ativos=("ativo", "sum"),
        pocos_novos=("poco_novo", "sum"),
        horas_media=("horas", "mean"),
    ).reset_index()

    # Operador, bacia e instalação mais frequentes do campo no mês
    for c in ("operador", "bacia"):
        moda = p.groupby(["campo", "mes"])[c].agg(lambda s: s.mode().iat[0] if len(s.mode()) else "N/D")
        campo = campo.join(moda, on=["campo", "mes"])

    # Garante meses contínuos por campo (mês sem registro = produção zero)
    completos = []
    for nome, df in campo.groupby("campo"):
        idx = pd.date_range(df["mes"].min(), df["mes"].max(), freq="MS")
        df = df.set_index("mes").reindex(idx)
        df.index.name = "mes"
        df["campo"] = nome
        for c in ("petroleo_bpd", "gas_mil_m3d", "pocos_ativos", "pocos_novos"):
            df[c] = df[c].fillna(0.0)
        df[["operador", "bacia"]] = df[["operador", "bacia"]].ffill().bfill()
        completos.append(df.reset_index())
    campo = pd.concat(completos, ignore_index=True)
    campo["horas_mes"] = campo["mes"].dt.days_in_month * 24
    campo["uptime"] = (campo["horas_media"] / campo["horas_mes"]).clip(0, 1)
    return campo.sort_values(["campo", "mes"]).reset_index(drop=True)


# --------------------------------------------------------------------------
# Mercado
# --------------------------------------------------------------------------
def carregar_mercado(pasta: Path) -> pd.DataFrame:
    pasta = Path(pasta)
    brent = pd.read_csv(pasta / "brent_mensal.csv", parse_dates=["data"])
    ptax = pd.read_csv(pasta / "ptax_mensal.csv", parse_dates=["data"])
    brent["mes"] = brent["data"].dt.to_period("M").dt.to_timestamp()
    ptax["mes"] = ptax["data"].dt.to_period("M").dt.to_timestamp()
    m = brent[["mes", "brent_usd"]].merge(ptax[["mes", "ptax_venda_media"]], on="mes", how="inner")
    return m.rename(columns={"ptax_venda_media": "ptax"}).sort_values("mes").reset_index(drop=True)


def completar_compartilhados(pocos: pd.DataFrame, raiz: Path) -> pd.DataFrame:
    """Recria a parcela de produção que o arquivo por poço omite em campos compartilhados
    (ver config/coparticipacao.csv). Só completa poço/mês em que a parcela faltante está zerada."""
    f = Path(raiz) / "config" / "coparticipacao.csv"
    if not f.exists():
        return pocos
    cfg = pd.read_csv(f, comment="#", parse_dates=["desde"])
    novos = []
    chave_existente = pocos[pocos.petroleo_bpd > 0].set_index(["campo", "poco", "mes"]).index
    for _, r in cfg.iterrows():
        base = pocos[(pocos.campo == r.campo_reportado) & (pocos.mes >= r.desde)].copy()
        if base.empty:
            continue
        fator = (1 - r.parcela_reportada) / r.parcela_reportada
        idx = pd.MultiIndex.from_arrays([[r.campo_faltante] * len(base), base.poco, base.mes])
        base = base[~idx.isin(chave_existente)]
        for c in ("petroleo_bpd", "gas_mil_m3d", "agua_bpd"):
            base[c] = base[c] * fator
        base["campo"] = r.campo_faltante
        novos.append(base)
    if not novos:
        return pocos
    out = pd.concat([pocos] + novos, ignore_index=True)
    # remove linhas zeradas do campo faltante que agora estão duplicadas
    out = out.sort_values("petroleo_bpd").drop_duplicates(["campo", "poco", "mes"], keep="last")
    return out.sort_values(["campo", "poco", "mes"]).reset_index(drop=True)

"""Plataformas novas: curva de rampa aprendida do histórico e projeção dos projetos anunciados.

O modelo de ML só enxerga o que já produz. Plataformas que ainda vão entrar em
operação (anunciadas publicamente) entram por aqui:
  produção(mês) = capacidade × fração da capacidade atingida k meses após o 1º óleo
A fração vem das plataformas que entraram em operação no Brasil desde 2010.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .precos import norm
from .unidades import unidade

K_MAX = 36          # meses de rampa modelados
CAP_MIN = 30_000    # só plataformas de porte (bbl/dia)


def historico_rampas(pocos: pd.DataFrame, raiz: Path) -> pd.DataFrame:
    """Uma linha por plataforma × mês desde o 1º óleo, com a fração da capacidade."""
    d = pocos[~pocos.instalacao.astype(str).isin(["Não Informado", "N/D", "nan"])].copy()
    d["inst_n"] = d.instalacao.map(norm)
    s = d.groupby(["inst_n", "mes"]).agg(oleo=("petroleo_bpd", "sum"), inst=("instalacao", "first")).reset_index()
    nominal = {}
    f = Path(raiz) / "config" / "capacidade_fpso.csv"
    if f.exists():
        c = pd.read_csv(f, comment="#")
        nominal = dict(zip(c.instalacao.map(norm), c.capacidade_bpd.astype(float)))
    unid = d.assign(u=d.campo.map(unidade)).groupby("inst_n").u.agg(lambda x: x.mode().iat[0])
    ult = pocos.mes.max()
    linhas = []
    for i, g in s.groupby("inst_n"):
        g = g[g.oleo > 0].sort_values("mes")
        if g.empty:
            continue
        ini = g.mes.iloc[0]
        if ini < pd.Timestamp("2010-01-01"):
            continue
        idade_obs = (ult.year - ini.year) * 12 + ult.month - ini.month
        serie = g.set_index("mes").oleo.reindex(pd.date_range(ini, min(ult, ini + pd.DateOffset(months=K_MAX - 1)),
                                                              freq="MS")).fillna(0.0)
        cap_obs = float(serie.max())
        cap = nominal.get(i, cap_obs if idade_obs >= 24 else np.nan)
        if not np.isfinite(cap) or cap < CAP_MIN:
            continue
        # troca de nome da plataforma na base (ex.: "Petrobras 66" -> "Petrobras 66 (P-66)") parece
        # um início de operação; um 1º óleo de verdade começa bem abaixo da capacidade
        if serie.iloc[:2].max() > 0.5 * cap:
            continue
        for k, v in enumerate(serie.values):
            linhas.append(dict(instalacao=g.inst.iloc[0], inst_n=i, unidade=unid.get(i, ""), inicio=ini, k=k,
                               oleo=v, capacidade=cap, fracao=v / cap, nominal=i in nominal))
    return pd.DataFrame(linhas)


def curva(hist: pd.DataFrame, excluir: str | None = None) -> pd.DataFrame:
    h = hist if excluir is None else hist[hist.inst_n != excluir]
    q = h.groupby("k").fracao.quantile([0.1, 0.5, 0.9]).unstack()
    q.columns = ["f10", "f50", "f90"]
    return q.reindex(range(K_MAX)).ffill()


def avaliar(hist: pd.DataFrame, meses: int = 18) -> pd.DataFrame:
    """Validação deixando uma plataforma de fora: curva aprendida × rampa linear de 12 meses."""
    res = []
    for i, g in hist.groupby("inst_n"):
        g = g[g.k < meses]
        if len(g) < meses:
            continue
        c = curva(hist, excluir=i)
        prev = c.loc[g.k, "f50"].values * g.capacidade.values
        linear = np.minimum((g.k.values + 1) / 12, 1.0) * g.capacidade.values
        res.append(dict(instalacao=g.instalacao.iloc[0], unidade=g.unidade.iloc[0], inicio=g.inicio.iloc[0],
                        real=g.oleo.sum(), curva=prev.sum(), linear=linear.sum(),
                        erro_curva=np.abs(prev - g.oleo.values).sum(), erro_linear=np.abs(linear - g.oleo.values).sum()))
    r = pd.DataFrame(res)
    return r


def projetar(projetos: pd.DataFrame, hist: pd.DataFrame, meses_fut: pd.DatetimeIndex, n_sim=2000, semente=3):
    """P10/P50/P90 da produção de cada projeto anunciado, sorteando data de início e formato da rampa."""
    rng = np.random.default_rng(semente)
    curvas = hist.pivot_table(index="inst_n", columns="k", values="fracao").reindex(columns=range(K_MAX))
    curvas = curvas.T.ffill().T.dropna(thresh=12)
    curvas = curvas.ffill(axis=1).to_numpy()
    linhas = []
    for _, p in projetos.iterrows():
        cedo, tarde = pd.Timestamp(p.inicio_cedo), pd.Timestamp(p.inicio_tarde)
        n_meses_ini = (tarde.year - cedo.year) * 12 + tarde.month - cedo.month
        sims = np.zeros((n_sim, len(meses_fut)))
        for s in range(n_sim):
            ini = cedo + pd.DateOffset(months=int(rng.integers(0, n_meses_ini + 1)))
            cv = curvas[rng.integers(0, len(curvas))]
            for j, m in enumerate(meses_fut):
                k = (m.year - ini.year) * 12 + m.month - ini.month
                if k >= 0:
                    sims[s, j] = p.capacidade_bpd * cv[min(k, K_MAX - 1)]
        for j, m in enumerate(meses_fut):
            linhas.append(dict(unidade=p.unidade, instalacao=p.instalacao, mes=m,
                               p10=np.percentile(sims[:, j], 10), p50=np.percentile(sims[:, j], 50),
                               p90=np.percentile(sims[:, j], 90), media=sims[:, j].mean()))
    return pd.DataFrame(linhas)


def somar_projetos_backtest(bt: pd.DataFrame, hist: pd.DataFrame, colunas) -> pd.DataFrame:
    """Simula no backtest um analista que conhecia a data de entrada das plataformas novas
    (como as anunciadas hoje): soma capacidade × curva de rampa (aprendida sem a própria
    plataforma) às previsões das colunas indicadas. Cria colunas '<col>_proj'."""
    bt = bt.copy()
    extra = pd.Series(0.0, index=bt.index)
    info = hist.groupby("inst_n").agg(inicio=("inicio", "first"), cap=("capacidade", "first"),
                                      unidade=("unidade", "first"))
    for i, r in info.iterrows():
        c = curva(hist, excluir=i)["f50"].to_numpy()
        m = (bt.unidade == r.unidade) & (bt.origem < r.inicio) & (bt.mes_alvo >= r.inicio)
        if not m.any():
            continue
        k = ((bt.loc[m, "mes_alvo"].dt.year - r.inicio.year) * 12 + bt.loc[m, "mes_alvo"].dt.month - r.inicio.month)
        extra[m] += r.cap * c[np.minimum(k.to_numpy(), K_MAX - 1)]
    for col in colunas:
        bt[f"{col}_proj"] = bt[col] + extra
    return bt


def resumo_plataformas(hist: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por plataforma: quanto tempo levou para chegar perto da capacidade."""
    res = []
    for i, g in hist.groupby("inst_n"):
        g = g.sort_values("k")
        def ate(x):
            k = g.k[g.fracao >= x]
            return int(k.iloc[0]) + 1 if len(k) else np.nan
        res.append(dict(instalacao=g.instalacao.iloc[0], unidade=g.unidade.iloc[0], inicio=g.inicio.iloc[0],
                        capacidade=g.capacidade.iloc[0], nominal=bool(g.nominal.iloc[0]), meses_obs=int(g.k.max()) + 1,
                        meses_50=ate(0.5), meses_80=ate(0.8), frac_12=g.fracao[g.k == 11].mean(), pico=g.fracao.max()))
    return pd.DataFrame(res).sort_values("inicio")

"""Modelo vencedor do torneio e ferramentas de backtest.

Modelo: gradient boosting (LightGBM, perda Huber) treinado com todas as
unidades ao mesmo tempo. Prevê a variação em log da produção entre a base
(média dos últimos 3 meses) e o mês t+h. As previsões dos métodos simples
(Arps, Arps por poço, ETS) entram como variáveis (stacking).

Faixas P10/P90: conformes (empíricas). Usamos os erros que o próprio modelo
cometeu no backtest, por horizonte e porte da unidade, e aplicamos esses
quantis à previsão central. Assim a faixa reflete o erro real observado.
"""
from __future__ import annotations

import warnings

import lightgbm as lgb
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

SIMPLES = ["m_ingenuo", "m_media3", "m_arps", "m_arps60", "m_arps_pocos", "m_ets"]
FEATS = ["h", "idade", "d1", "d3", "d6", "d12", "tend_3_12", "vol12", "pico_ratio", "meses_desde_pico",
         "pico24_ratio", "log_cum", "bsw", "d_bsw12", "log_rgo", "log_pocos", "d_pocos6", "d_pocos12",
         "novos3", "novos12", "prod_por_poco", "presal"]
REL = ["r_arps", "r_arps60", "r_arps_pocos", "r_ets"]
PARAMS = dict(objective="huber", alpha=0.3, n_estimators=400, learning_rate=0.03, num_leaves=15,
              min_child_samples=100, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
              random_state=42, verbose=-1)
PORTES = [0, 10_000, 100_000, np.inf]


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for m in SIMPLES:
        df[m] = df[m].fillna(df["m_media3"])
    lb = np.log1p(df["base"])
    for m, r in zip(["m_arps", "m_arps60", "m_arps_pocos", "m_ets"], REL):
        df[r] = np.log1p(df[m]) - lb
    df["alvo"] = np.log1p(df["real"]) - lb
    df["porte"] = pd.cut(df["base"], PORTES, labels=["pequeno", "medio", "grande"]).astype(str)
    return df


def treinar(treino: pd.DataFrame, params: dict = PARAMS) -> lgb.LGBMRegressor:
    tr = treino[treino.alvo.notna()]
    return lgb.LGBMRegressor(**params).fit(tr[FEATS + REL], tr.alvo, sample_weight=np.sqrt(tr.base))


def prever(modelo, df: pd.DataFrame) -> pd.Series:
    return np.expm1(np.log1p(df["base"]) + modelo.predict(df[FEATS + REL])).clip(lower=0)


def backtest(df: pd.DataFrame, origens, passo_meses: int = 6, log=print) -> pd.Series:
    """Para cada origem, usa um modelo treinado só com alvos já conhecidos
    naquela data (re-treina a cada `passo_meses`)."""
    out = pd.Series(np.nan, index=df.index)
    modelo, ult = None, None
    for o in sorted(pd.to_datetime(origens)):
        if ult is None or (o - ult).days > passo_meses * 30 - 5:
            modelo = treinar(df[df.mes_alvo <= o])
            ult = o
            log(f"  treino até {o:%Y-%m}")
        te = df.origem == o
        if te.any():
            out[te] = prever(modelo, df[te])
    return out


# Os erros do passado subestimam um pouco os do futuro (o mundo muda). Testando no período
# 2018–2021 com quantis aprendidos em 2010–2017, os quantis 5%/95% dos erros passados
# cobriram 80,7% dos casos — por isso são eles que formam a faixa "P10–P90".
Q_INF, Q_SUP = 0.05, 0.95


def quantis_erro(bt: pd.DataFrame, col: str = "ml") -> pd.DataFrame:
    """Quantis do erro em log (real vs previsto) por horizonte e porte, calibrados para ~80% de cobertura."""
    d = bt[bt.real.notna() & bt[col].notna()].copy()
    d["erro"] = np.log1p(d["real"]) - np.log1p(d[col])
    q = d.groupby(["h", "porte"])["erro"].quantile([Q_INF, Q_SUP]).unstack()
    q.columns = ["q10", "q90"]
    return q.reset_index()


def aplicar_faixas(prev: pd.DataFrame, q: pd.DataFrame, col: str = "ml") -> pd.DataFrame:
    p = prev.merge(q, on=["h", "porte"], how="left")
    p["q10"] = p["q10"].fillna(p.groupby("h")["q10"].transform("mean"))
    p["q90"] = p["q90"].fillna(p.groupby("h")["q90"].transform("mean"))
    p["p50"] = p[col]
    p["p10"] = np.expm1(np.log1p(p[col]) + p["q10"]).clip(lower=0)
    p["p90"] = np.expm1(np.log1p(p[col]) + p["q90"]).clip(lower=0)
    return p


def metricas(d: pd.DataFrame, cols) -> pd.DataFrame:
    d = d[d.real.notna()]
    res = {}
    for c in cols:
        port = d.groupby(["origem", "h"]).apply(lambda g: abs(g[c].sum() - g.real.sum()) / g.real.sum())
        res[c] = {"WAPE por unidade": (d[c] - d.real).abs().sum() / d.real.sum(),
                  "Erro da carteira": port.mean(),
                  "Viés": (d[c] - d.real).sum() / d.real.sum()}
    return pd.DataFrame(res).T


def metricas_por_h(d: pd.DataFrame, cols) -> pd.DataFrame:
    d = d[d.real.notna()]
    return d.groupby("h").apply(
        lambda g: pd.Series({c: (g[c] - g.real).abs().sum() / g.real.sum() for c in cols})).reset_index()


def pesos_combinacao(dev: pd.DataFrame, col: str = "ml") -> dict:
    """Peso do ML (contra o ingênuo) em cada horizonte, escolhido para minimizar o erro absoluto."""
    ws = np.linspace(0, 1, 21)
    pesos = {}
    for h, g in dev.groupby("h"):
        erros = [((w * g[col] + (1 - w) * g.m_ingenuo) - g.real).abs().sum() for w in ws]
        pesos[h] = float(ws[int(np.argmin(erros))])
    return pesos


def combinar(df: pd.DataFrame, pesos: dict, col: str = "ml") -> pd.Series:
    w = df.h.map(pesos).fillna(1.0)
    return w * df[col] + (1 - w) * df.m_ingenuo


def correlacao_erros(bt: pd.DataFrame, col: str = "final") -> float:
    """Correlação média entre os erros (em log) das unidades numa mesma data e horizonte.
    Usada no Monte Carlo: campos tendem a errar juntos (preço, paradas da mesma operadora...)."""
    d = bt[bt.real.notna() & (bt.real > 0) & (bt[col] > 0)].copy()
    d["e"] = np.log(d.real) - np.log(d[col])
    d["z"] = d.groupby("h").e.transform(lambda x: (x - x.mean()) / x.std())
    num, den = [], []
    for _, g in d.groupby(["origem", "h"]):
        z = g.z.to_numpy()
        n = len(z)
        if n < 3:
            continue
        num.append((z.sum() ** 2 - (z ** 2).sum()) / (n * (n - 1)))
        den.append((z ** 2).mean())
    return float(np.clip(np.mean(num) / np.mean(den), 0, 0.9)) if num else 0.0


ROTULOS = {
    "h": "horizonte", "idade": "maturidade do campo", "d1": "variação no último mês", "d3": "tendência de 3 meses",
    "d6": "tendência de 6 meses", "d12": "tendência de 12 meses", "tend_3_12": "ritmo recente vs. ano",
    "vol12": "instabilidade da produção", "pico_ratio": "distância do pico histórico",
    "meses_desde_pico": "meses desde o pico", "pico24_ratio": "distância do pico de 2 anos",
    "log_cum": "produção acumulada", "bsw": "% de água", "d_bsw12": "aumento da % de água",
    "log_rgo": "razão gás/óleo", "log_pocos": "nº de poços ativos", "d_pocos6": "poços ativos (6 meses)",
    "d_pocos12": "poços ativos (12 meses)", "novos3": "poços novos (3 meses)", "novos12": "poços novos (12 meses)",
    "prod_por_poco": "produção por poço", "presal": "pré-sal", "r_arps": "curva de declínio (Arps)",
    "r_arps60": "curva de declínio longa", "r_arps_pocos": "declínio poço a poço", "r_ets": "tendência suavizada (ETS)",
}


def fatores(modelo, df: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    """Principais fatores de cada previsão (contribuições SHAP nativas do LightGBM)."""
    contrib = modelo.predict(df[FEATS + REL], pred_contrib=True)[:, :-1]
    nomes = FEATS + REL
    linhas = []
    for (_, r), c in zip(df.iterrows(), contrib):
        ordem = np.argsort(-np.abs(c))
        ordem = [i for i in ordem if nomes[i] != "h"][:n]
        txt = "; ".join(f"{ROTULOS.get(nomes[i], nomes[i])} ({'+' if c[i] > 0 else '−'}{abs(np.expm1(c[i])) * 100:.0f}%)"
                        for i in ordem)
        linhas.append(dict(unidade=r.unidade, h=r.h, fatores=txt, variacao_prevista=np.expm1(c.sum())))
    return pd.DataFrame(linhas)


def erro_anual(bt: pd.DataFrame, cols) -> pd.DataFrame:
    """Previsão feita em dezembro para o ano seguinte inteiro (como num orçamento anual)."""
    d = bt[(bt.origem.dt.month == 12) & (bt.h <= 12) & bt.real.notna()]
    d = d.groupby(["origem", "unidade"]).filter(lambda g: len(g) == 12)
    a = d.groupby(["origem", "unidade"])[["real"] + list(cols)].mean().reset_index()
    a["ano"] = a.origem.dt.year + 1
    res = {}
    for c in cols:
        por_ano = a.groupby("ano").apply(lambda g: pd.Series({
            "wape": (g[c] - g.real).abs().sum() / g.real.sum(),
            "carteira": abs(g[c].sum() - g.real.sum()) / g.real.sum()}))
        res[c] = {"WAPE anual por unidade": (a[c] - a.real).abs().sum() / a.real.sum(),
                  "Erro anual da carteira": por_ano.carteira.mean(), "anos": len(por_ano)}
    return pd.DataFrame(res).T, a

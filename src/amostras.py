"""Da tabela poço × mês para as amostras do modelo (unidade × origem × horizonte)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from .metodos import H, arps, arps_pocos, ets_amortecido
from .unidades import unidade

BASE_MIN = 500.0   # unidades abaixo disso (bbl/dia) não entram no modelo


def preparar_series(pocos: pd.DataFrame):
    """Retorna meses, máscara de lacuna, séries por unidade e matrizes poço × mês."""
    d = pocos.copy()
    d["unidade"] = d["campo"].map(unidade)
    meses = pd.date_range(d.mes.min(), d.mes.max(), freq="MS")
    idx = {m: i for i, m in enumerate(meses)}
    tot = d.groupby("mes")["petroleo_bpd"].sum()
    lacuna = np.array([tot.get(m, 0) <= 0 for m in meses])

    d["ativo"] = (d.petroleo_bpd > 0).astype(int)
    ini = d[d.ativo == 1].groupby("poco")["mes"].min()
    d["novo"] = (d["mes"] == d["poco"].map(ini)).astype(int)
    pu = d.groupby(["unidade", "mes", "poco"]).agg(oleo=("petroleo_bpd", "sum"), gas=("gas_mil_m3d", "sum"),
                                                    agua=("agua_bpd", "sum"), novo=("novo", "max")).reset_index()
    pu["ativo"] = (pu.oleo > 0).astype(int)
    pm = pu.groupby(["unidade", "mes"]).agg(oleo=("oleo", "sum"), gas=("gas", "sum"), agua=("agua", "sum"),
                                            pocos=("ativo", "sum"), novos=("novo", "sum")).reset_index()
    bacia = d.groupby("unidade")["bacia"].agg(lambda s: s.mode().iat[0]).to_dict()

    series, matrizes = {}, {}
    for u, g in pm.groupby("unidade"):
        arr = {}
        for c in ["oleo", "gas", "agua", "pocos", "novos"]:
            a = np.zeros(len(meses))
            a[[idx[m] for m in g.mes]] = g[c].to_numpy(float)
            a[lacuna] = np.nan
            arr[c] = a
        series[u] = arr
        w = pu[pu.unidade == u].pivot_table(index="poco", columns="mes", values="oleo", aggfunc="sum")
        mat = np.zeros((len(w), len(meses)))
        for m in w.columns:
            mat[:, idx[m]] = w[m].fillna(0).to_numpy()
        mat[:, lacuna] = np.nan
        matrizes[u] = mat
    return meses, lacuna, series, matrizes, bacia


def _amostras_unidade(u, arr, mat, meses, origens, bacia):
    q = arr["oleo"]
    n = len(q)
    pos = np.where(np.nan_to_num(q) > 0)[0]
    if len(pos) == 0:
        return []
    inicio = pos[0]
    linhas = []
    for t in origens:
        if t < max(inicio + 3, 12) or np.isnan(q[t - 12: t + 1]).any():
            continue
        base = q[t - 2: t + 1].mean()
        if base < BASE_MIN:
            continue
        hist = q[: t + 1]
        f_arps, f_arps60 = arps(hist, 36), arps(hist, 60)
        f_poc = arps_pocos(mat, t, 24)
        f_ets = ets_amortecido(hist)
        lb = np.log1p(base)
        agua, gas, pc, nv = arr["agua"], arr["gas"], arr["pocos"], arr["novos"]
        bsw = agua / np.maximum(agua + q, 1e-9)
        y = np.log1p(np.nan_to_num(q))
        dy = np.diff(y[t - 12: t + 1])
        f = dict(
            unidade=u, bacia=bacia, origem=meses[t], base=base, ultimo=q[t], idade=t - inicio,
            d1=y[t] - y[t - 1], d3=y[t] - y[t - 3], d6=y[t] - y[t - 6], d12=y[t] - y[t - 12],
            tend_3_12=lb - np.log1p(np.nanmean(q[t - 11: t + 1])), vol12=dy.std(),
            pico_ratio=lb - np.log1p(np.nanmax(hist)), meses_desde_pico=t - int(np.nanargmax(hist)),
            pico24_ratio=lb - np.log1p(np.nanmax(q[t - 23: t + 1])) if t >= 23 else np.nan,
            log_cum=np.log1p(np.nansum(hist) * 30.4), bsw=np.nanmean(bsw[t - 2: t + 1]),
            d_bsw12=bsw[t] - bsw[t - 12], log_rgo=np.log1p(gas[t] * 1000 / max(q[t], 1.0)),
            log_pocos=np.log1p(pc[t]), d_pocos6=pc[t] - pc[t - 6], d_pocos12=pc[t] - pc[t - 12],
            novos3=np.nansum(nv[t - 2: t + 1]), novos12=np.nansum(nv[t - 11: t + 1]),
            prod_por_poco=np.log1p(base / max(pc[t], 1)), presal=int(bacia == "Santos"),
        )
        for i in range(H):
            h = i + 1
            r = dict(f)
            r.update(h=h, mes_alvo=meses[t] + pd.DateOffset(months=h),
                     real=q[t + h] if t + h < n else np.nan,
                     m_ingenuo=q[t], m_media3=base,
                     m_arps=f_arps[i] if f_arps is not None else np.nan,
                     m_arps60=f_arps60[i] if f_arps60 is not None else np.nan,
                     m_arps_pocos=f_poc[i], m_ets=f_ets[i] if f_ets is not None else np.nan)
            linhas.append(r)
    return linhas


def construir(pocos: pd.DataFrame, n_jobs: int = -1) -> pd.DataFrame:
    meses, lacuna, series, matrizes, bacia = preparar_series(pocos)
    origens = [t for t in range(12, len(meses)) if not lacuna[t]]
    res = Parallel(n_jobs=n_jobs)(delayed(_amostras_unidade)(u, series[u], matrizes[u], meses, origens, bacia[u])
                                  for u in series)
    return pd.DataFrame([r for lst in res for r in lst])

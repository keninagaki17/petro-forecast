"""Teto físico da previsão: capacidade das plataformas (FPSOs) ativas em cada unidade."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .precos import norm
from .unidades import unidade

FOLGA = 1.03


def tabela_capacidade(pocos: pd.DataFrame, raiz: Path) -> pd.DataFrame:
    """Capacidade por unidade e mês de origem (bbl/dia), usando só informação disponível no mês."""
    d = pocos[~pocos.instalacao.isin(["Não Informado", "N/D", "nan"])].copy()
    d["unidade"] = d.campo.map(unidade)
    d["inst_n"] = d.instalacao.map(norm)
    ui = d.groupby(["unidade", "inst_n", "mes"]).petroleo_bpd.sum().unstack("mes").fillna(0.0)
    meses = pd.date_range(pocos.mes.min(), pocos.mes.max(), freq="MS")
    ui = ui.reindex(columns=meses, fill_value=0.0)
    f = raiz / "config" / "capacidade_fpso.csv"
    nominal = {}
    if f.exists():
        c = pd.read_csv(f, comment="#")
        nominal = dict(zip(c.instalacao.map(norm), c.capacidade_bpd.astype(float)))
    # o total da unidade num mês pode ter lacunas (mês sem dados = 0 em todas as plataformas)
    tem_dado = pocos.groupby("mes").petroleo_bpd.sum().reindex(meses).fillna(0) > 0
    mask = pd.DataFrame(np.repeat(tem_dado.values[:, None], ui.shape[0], axis=1), index=meses, columns=ui.index)
    uiT = ui.T.where(mask)
    pico24 = uiT.rolling(24, min_periods=1).max().T.fillna(0.0)
    ativo = uiT.rolling(3, min_periods=1).max().T.fillna(0.0) > 0
    nom = pd.Series([nominal.get(i, 0.0) for i in ui.index.get_level_values("inst_n")], index=ui.index)
    cap = np.maximum(pico24.values, nom.values[:, None]) * ativo.values
    # plataforma em rampa (menos de 24 meses) sem capacidade nominal conhecida: o pico observado
    # ainda não é o teto, então a unidade fica sem teto naquele mês
    inicio = (ui > 0).idxmax(axis=1)
    idade = np.array([[(m.year - i.year) * 12 + m.month - i.month for m in meses] for i in inicio])
    em_rampa_sem_nominal = (idade < 24) & (idade >= 0) & (nom.values[:, None] == 0) & ativo.values
    cap = pd.DataFrame(cap, index=ui.index, columns=meses).groupby(level="unidade").sum() * FOLGA
    sem_teto = pd.DataFrame(em_rampa_sem_nominal, index=ui.index, columns=meses).groupby(level="unidade").any()
    cap = cap.mask(sem_teto, np.inf)
    out = cap.stack().rename("capacidade").reset_index()
    out.columns = ["unidade", "origem", "capacidade"]
    return out[(out.capacidade > 0) & np.isfinite(out.capacidade)]


def aplicar_teto(df: pd.DataFrame, cap: pd.DataFrame, colunas) -> pd.DataFrame:
    df = df.merge(cap, on=["unidade", "origem"], how="left")
    lim = df.capacidade.fillna(np.inf)
    for c in colunas:
        df[c] = np.minimum(df[c], lim)
    return df

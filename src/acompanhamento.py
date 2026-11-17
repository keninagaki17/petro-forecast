"""Previsto × realizado: arquiva a previsão de cada rodada e compara com o que aconteceu depois.

A cada rodada mensal:
  1. a previsão recém-feita é guardada em saidas/historico/previsao_AAAA-MM.csv;
  2. toda previsão guardada em rodadas anteriores é comparada com a produção já publicada.
Enquanto não há previsões guardadas para um mês, a comparação usa o teste retroativo
(o que o modelo teria previsto naquela data, treinado só com dados anteriores).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def arquivar(prev: pd.DataFrame, saidas: Path, ultimo: pd.Timestamp) -> Path:
    pasta = Path(saidas) / "historico"
    pasta.mkdir(parents=True, exist_ok=True)
    f = pasta / f"previsao_{ultimo:%Y-%m}.csv"
    prev[["unidade", "mes", "h", "p10", "p50", "p90"]].to_csv(f, index=False)
    return f


def comparar(saidas: Path, hist_u: pd.DataFrame, bt: pd.DataFrame, ultimo: pd.Timestamp, meses: int = 36) -> pd.DataFrame:
    """Uma linha por unidade × mês × horizonte: previsto, ingênuo (último mês repetido), realizado e a fonte."""
    real = hist_u.set_index(["unidade", "mes"]).petroleo_bpd
    ini = ultimo - pd.DateOffset(months=meses - 1)
    b = bt[(bt.mes_alvo >= ini) & (bt.mes_alvo <= ultimo)]
    teste = pd.DataFrame({"origem": b.origem, "unidade": b.unidade, "mes": b.mes_alvo, "h": b.h, "previsto": b.final_proj,
                          "ingenuo": b.m_ingenuo, "real": b.real, "fonte": "teste retroativo"})
    pub = []
    for f in sorted((Path(saidas) / "historico").glob("previsao_*.csv")):
        origem = pd.Timestamp(f.stem.split("_")[1] + "-01")
        if origem >= ultimo:
            continue
        p = pd.read_csv(f, parse_dates=["mes"])
        p = p[(p.mes <= ultimo) & (p.mes >= ini)]
        if p.empty:
            continue
        base = real.xs(origem, level="mes") if origem in real.index.get_level_values("mes") else pd.Series(dtype=float)
        pub.append(pd.DataFrame({"origem": origem, "unidade": p.unidade, "mes": p.mes, "h": p.h, "previsto": p.p50,
                                 "ingenuo": p.unidade.map(base), "fonte": "publicada",
                                 "real": [real.get((u, m), 0.0) for u, m in zip(p.unidade, p.mes)]}))
    if pub:
        pub = pd.concat(pub, ignore_index=True)
        chave = pd.MultiIndex.from_frame(pub[["unidade", "mes", "h"]])
        teste = teste[~pd.MultiIndex.from_frame(teste[["unidade", "mes", "h"]]).isin(chave)]
        teste = pd.concat([pub, teste], ignore_index=True)
    return teste.sort_values(["mes", "h", "unidade"]).reset_index(drop=True)

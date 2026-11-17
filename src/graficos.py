"""Gráficos estáticos (PNG) para o relatório. O painel web virá na próxima etapa."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

COR = {
    "superficie": "#fcfcfb", "texto": "#0b0b0b", "texto2": "#52514e", "mudo": "#898781",
    "grade": "#e1e0d9", "eixo": "#c3c2b7",
    "s1": "#2a78d6", "s2": "#eb6834", "s3": "#1baf7a",
    "pos": "#2a78d6", "neg": "#e34948",
}


def _estilo(ax, titulo: str, subtitulo: str = ""):
    ax.set_facecolor(COR["superficie"])
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(COR["eixo"])
    ax.tick_params(colors=COR["texto2"], labelsize=9, length=0)
    ax.grid(axis="y", color=COR["grade"], linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_title(titulo, loc="left", fontsize=12, color=COR["texto"], pad=22, fontweight="bold")
    if subtitulo:
        ax.text(0, 1.02, subtitulo, transform=ax.transAxes, fontsize=9, color=COR["texto2"])


def _fig(w=9, h=4.6):
    fig, ax = plt.subplots(figsize=(w, h), dpi=150)
    fig.patch.set_facecolor(COR["superficie"])
    return fig, ax


def erro_por_horizonte(por_h: pd.DataFrame, destino: Path) -> None:
    fig, ax = _fig()
    series = [("Modelo final (ML + plataformas novas)", "Modelo final", COR["s1"]), ("Curva de declínio (Arps) da unidade", "Arps", COR["s2"]),
              ("Ingênuo (repete o último mês)", "Ingênuo", COR["s3"]), ("Suavização exponencial (ETS)", "ETS", "#8a63d2")]
    for col, rot, cor in series:
        if col not in por_h:
            continue
        y = por_h[col] * 100
        ax.plot(por_h["h"], y, color=cor, linewidth=2, marker="o", markersize=3.5, label=rot)
        ax.annotate(rot, (por_h["h"].iat[-1], y.iat[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=9, color=COR["texto2"])
    _estilo(ax, "Erro da previsão de produção por horizonte (dados reais)",
            "WAPE por unidade no backtest, em %; menor é melhor")
    ax.set_xlabel("Meses à frente", color=COR["texto2"], fontsize=9)
    ax.set_xlim(0.5, por_h["h"].max() + 3)
    ax.set_xticks([1, 3, 6, 9, 12, 15, 18])
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=9, loc="upper left", labelcolor=COR["texto2"])
    fig.tight_layout()
    fig.savefig(destino, facecolor=COR["superficie"])
    plt.close(fig)


def calibracao(calib: pd.DataFrame, destino: Path) -> None:
    c = calib[calib.index >= "2015-01-01"].copy()
    c.index = pd.to_datetime(c.index)
    c = c.reindex(pd.date_range(c.index.min(), c.index.max(), freq="MS"))
    fig, ax = _fig(9, 4.2)
    ax.plot(c.index, c["royalties"] / 1e9, color=COR["texto2"], linewidth=2, label="Arrecadado (ANP)")
    ax.plot(c.index, c["ajustado"] / 1e9, color=COR["s1"], linewidth=2, label="Calculado pelo modelo")
    _estilo(ax, "Royalties: calculado pelo modelo × arrecadação publicada pela ANP",
            "R$ bilhões por mês de competência")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=9, loc="upper left", labelcolor=COR["texto2"])
    fig.tight_layout()
    fig.savefig(destino, facecolor=COR["superficie"])
    plt.close(fig)


def leque_campos(historico: pd.DataFrame, previsao: pd.DataFrame, campos: list[str],
                 destino: Path, meses_hist: int = 36) -> None:
    n = len(campos)
    cols = 2
    linhas = int(np.ceil(n / cols))
    fig, axes = plt.subplots(linhas, cols, figsize=(10, 2.9 * linhas), dpi=150, squeeze=False)
    fig.patch.set_facecolor(COR["superficie"])
    for ax, campo in zip(axes.ravel(), campos):
        h = historico[historico["campo"] == campo].sort_values("mes").tail(meses_hist)
        p = previsao[previsao["campo"] == campo].sort_values("mes")
        ax.plot(h["mes"], h["petroleo_bpd"] / 1000, color=COR["texto2"], linewidth=1.6, label="Realizado")
        ax.fill_between(p["mes"], p["p10_bpd"] / 1000, p["p90_bpd"] / 1000, color=COR["s1"],
                        alpha=0.18, linewidth=0, label="Faixa P10–P90")
        ax.plot(p["mes"], p["p50_bpd"] / 1000, color=COR["s1"], linewidth=2, label="Previsão P50")
        _estilo(ax, campo)
        ax.set_ylim(bottom=0)
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.tick_params(axis="x", labelsize=8)
    for ax in axes.ravel()[n:]:
        ax.axis("off")
    alcas, rotulos = axes[0, 0].get_legend_handles_labels()
    fig.legend(alcas, rotulos, frameon=False, fontsize=9, loc="upper right", ncol=3,
               labelcolor=COR["texto2"], bbox_to_anchor=(0.99, 0.995))
    fig.suptitle("Produção de petróleo por campo (mil bbl/dia): histórico e previsão",
                 x=0.01, ha="left", fontsize=12, fontweight="bold", color=COR["texto"])
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(destino, facecolor=COR["superficie"])
    plt.close(fig)


def cascata_ponte(ponte: pd.DataFrame, destino: Path, titulo: str) -> None:
    prev = ponte["receita_prevista"].sum() / 1e9
    vol = ponte["efeito_volume"].sum() / 1e9
    prc = ponte["efeito_preco"].sum() / 1e9
    fx = ponte["efeito_cambio"].sum() / 1e9
    real = ponte["receita_realizada"].sum() / 1e9
    nomes = ["Receita prevista", "Volume", "Preço (Brent)", "Câmbio", "Receita realizada"]
    valores = [prev, vol, prc, fx, real]
    fig, ax = _fig(9, 4.4)
    acumulado = prev
    for i, (n, v) in enumerate(zip(nomes, valores)):
        if i in (0, 4):
            ax.bar(i, v, color=COR["mudo"], width=0.55)
            ax.text(i, v, f"R$ {v:,.1f} bi", ha="center", va="bottom", fontsize=9, color=COR["texto"])
        else:
            base = acumulado if v >= 0 else acumulado + v
            ax.bar(i, abs(v), bottom=base, color=COR["pos"] if v >= 0 else COR["neg"], width=0.55)
            ax.text(i, max(acumulado, acumulado + v), f"{v:+,.1f}", ha="center", va="bottom",
                    fontsize=9, color=COR["texto"])
            acumulado += v
    ax.set_xticks(range(5), nomes)
    _estilo(ax, titulo, "R$ bilhões; azul aumenta e vermelho reduz a receita")
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    fig.savefig(destino, facecolor=COR["superficie"])
    plt.close(fig)

"""Da produção para o dinheiro: preço por campo, receita, royalties, PE e ponte de variação."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .precos import M3_BBL, norm
from .unidades import unidade

Z90 = 1.2816
K_PADRAO = 0.92   # preço de referência ANP médio ≈ 92% do Brent (2025)


# --------------------------------------------------------------------------
# Alíquotas e volumes por subcampo
# --------------------------------------------------------------------------
def aliquotas(raiz: Path):
    f = raiz / "config" / "aliquotas_campos.csv"
    tab = {}
    if f.exists():
        t = pd.read_csv(f, comment="#")
        tab = dict(zip(t.campo.map(norm), t.aliquota.astype(float)))

    def regra(campo):
        c = norm(campo)
        if c in tab:
            return tab[c]
        return 0.15 if (c.endswith("_eco") or c.startswith("anc_")) else 0.10
    return regra


def volumes_campo(pocos: pd.DataFrame) -> pd.DataFrame:
    v = pocos.groupby(["campo", "mes"]).agg(oleo_bpd=("petroleo_bpd", "sum"), gas_mil=("gas_mil_m3d", "sum")).reset_index()
    v["campo_n"] = v.campo.map(norm)
    v["unidade"] = v.campo.map(unidade)
    dias = v.mes.dt.days_in_month
    v["oleo_m3"] = v.oleo_bpd * dias / M3_BBL
    v["gas_m3"] = v.gas_mil * dias * 1000
    return v


# --------------------------------------------------------------------------
# Preços
# --------------------------------------------------------------------------
class Precos:
    """Preço do petróleo por campo em R$/m³: o publicado pela ANP quando existe;
    senão, Brent × k × fator do campo × câmbio."""

    def __init__(self, prp, prgn, ptax, brent, vol):
        self.prp = prp.set_index(["campo_n", "mes"])["preco"]
        self.prgn = prgn.set_index(["campo_n", "mes"])["preco"]
        self.ptax = ptax
        self.brent = brent.set_index("mes")["brent_usd"]
        self.tipo_brent = brent.set_index("mes")["tipo"]
        v = vol.merge(prp, on=["campo_n", "mes"], how="inner")
        v = v[v.oleo_m3 > 0]
        idx = v.groupby("mes").apply(lambda g: np.average(g.preco, weights=g.oleo_m3))
        self.indice_brl = idx                                     # R$/m³ médio nacional
        self.indice_usd = idx / ptax.reindex(idx.index) / M3_BBL   # US$/bbl
        ult = idx.index.max()
        rec = v[v.mes > ult - pd.DateOffset(months=12)].copy()
        rec["rel"] = rec.preco / rec.mes.map(idx)
        self.fator = rec.groupby("campo_n").apply(lambda g: np.average(g.rel, weights=g.oleo_m3))
        comum = self.indice_usd.index.intersection(self.brent.index)
        self.k = float((self.indice_usd[comum] / self.brent[comum]).mean()) if len(comum) >= 2 else K_PADRAO
        self.ultimo_prp = ult
        g = vol.merge(prgn, on=["campo_n", "mes"], how="inner")
        g = g[g.mes > g.mes.max() - pd.DateOffset(months=12)]
        self.gas_recente = g.groupby("campo_n").preco.mean()
        self.gas_medio = float(np.average(g.preco, weights=g.gas_m3 + 1)) if len(g) else 1.0

    def petroleo(self, campo_n, mes, brent_usd=None, fx=None):
        if brent_usd is None and (campo_n, mes) in self.prp.index:
            return self.prp[(campo_n, mes)]
        b = brent_usd if brent_usd is not None else self.brent.get(mes, np.nan)
        f = fx if fx is not None else self.ptax.get(mes, self.ptax.iloc[-1])
        return b * self.k * self.fator.get(campo_n, 1.0) * f * M3_BBL

    def gas(self, campo_n, mes):
        if (campo_n, mes) in self.prgn.index:
            return self.prgn[(campo_n, mes)]
        return self.gas_recente.get(campo_n, self.gas_medio)


# --------------------------------------------------------------------------
# Royalties históricos e calibração contra a arrecadação nacional
# --------------------------------------------------------------------------
def royalties_historicos(vol, precos: Precos, regra_aliq) -> pd.DataFrame:
    v = vol[vol.mes >= "2009-01-01"].copy()
    v["prp"] = [precos.petroleo(c, m) for c, m in zip(v.campo_n, v.mes)]
    v["prgn"] = [precos.gas(c, m) for c, m in zip(v.campo_n, v.mes)]
    v["aliq"] = v.campo.map(regra_aliq)
    v["receita"] = v.oleo_m3 * v.prp + v.gas_m3 * v.prgn
    v["royalties"] = v.receita * v.aliq
    return v


def calibrar(hist: pd.DataFrame, nacional: pd.DataFrame):
    n = hist.groupby("mes").royalties.sum().rename("calculado").to_frame().join(nacional.set_index("mes"), how="inner")
    n = n[n.calculado > 0]
    recente = n.tail(12)
    lam = float((recente.royalties / recente.calculado).median())
    n["ajustado"] = n.calculado * lam
    n["erro_pct"] = n.ajustado / n.royalties - 1
    return lam, n


def taxa_pe(hist: pd.DataFrame, pe: pd.DataFrame) -> pd.Series:
    """Taxa efetiva de PE por campo = PE pago / receita bruta, últimos 4 trimestres publicados."""
    if pe.empty:
        return pd.Series(dtype=float)
    h = hist.copy()
    h["trimestre"] = h.mes.dt.to_period("Q").dt.start_time
    rec = h.groupby(["campo_n", "trimestre"]).receita.sum()
    p = pe.copy()
    p["trimestre"] = p.trimestre.dt.to_period("Q").dt.start_time
    p = p.groupby(["campo_n", "trimestre"]).pe.sum()
    ult = p.index.get_level_values(1).max()
    jan = [ult - pd.DateOffset(months=3 * i) for i in range(4)]
    p4 = p[p.index.get_level_values(1).isin(jan)].groupby(level=0).sum()
    r4 = rec[rec.index.get_level_values(1).isin(jan)].groupby(level=0).sum()
    return (p4 / r4.reindex(p4.index)).replace([np.inf, -np.inf], np.nan).dropna().clip(0, 0.6)


# --------------------------------------------------------------------------
# Projeção com Monte Carlo
# --------------------------------------------------------------------------
def cenarios_mercado(precos: Precos, meses_fut, n_sim=2000, bloco=3, semente=7):
    """Brent: cenário base (config) × choques históricos; câmbio: último PTAX × choques.
    Os choques de petróleo e câmbio são sorteados do mesmo mês histórico, o que
    preserva a correlação entre eles. Usa o índice de preço da ANP em US$ (2009+)
    e o Brent de 2026 como histórico de variações."""
    ind = precos.indice_usd.dropna()
    fx = precos.ptax
    r_p = np.log(ind).diff()
    b26 = precos.brent[precos.tipo_brent == "realizado"]
    r_p = pd.concat([r_p, np.log(b26).diff()[~b26.index.isin(r_p.index)]]).dropna().sort_index()
    r_f = np.log(fx).diff().reindex(r_p.index)
    ok = r_f.notna()
    rp, rf = (r_p[ok] - r_p[ok].mean()).to_numpy(), (r_f[ok] - r_f[ok].mean()).to_numpy()
    n = len(meses_fut)
    rng = np.random.default_rng(semente)
    base_b = np.array([precos.brent.get(m, np.nan) for m in meses_fut])
    base_b = pd.Series(base_b).ffill().bfill().to_numpy()
    fx0 = fx.iloc[-1]
    # meses com Brent já realizado não recebem choque; o câmbio usa PTAX realizado quando existe
    realizado = np.array([precos.tipo_brent.get(m, "") == "realizado" for m in meses_fut])
    fx_real = np.array([fx.get(m, np.nan) for m in meses_fut])
    B = np.empty((n_sim, n)); F = np.empty((n_sim, n))
    for s in range(n_sim):
        idx = []
        while len(idx) < n:
            i = rng.integers(0, len(rp) - bloco)
            idx.extend(range(i, i + bloco))
        idx = np.array(idx[:n])
        cb = rp[idx].copy(); cb[realizado] = 0.0
        cf = rf[idx].copy(); cf[~np.isnan(fx_real)] = 0.0
        B[s] = base_b * np.exp(np.cumsum(cb))
        F[s] = np.where(np.isnan(fx_real), fx0 * np.exp(np.cumsum(cf)), fx_real)
    return B, F, base_b, fx0


def projetar(prev: pd.DataFrame, vol: pd.DataFrame, precos: Precos, regra_aliq, lam: float, pe_taxa: pd.Series,
             operadores: dict, n_sim=2000, semente=11, rho: float = 0.0):
    """prev: unidade, mes, p10, p50, p90 (bbl/dia). Retorna (por unidade, por operadora, total Brasil)."""
    meses = pd.DatetimeIndex(sorted(prev.mes.unique()))
    B, F, base_b, fx0 = cenarios_mercado(precos, meses, n_sim)
    rng = np.random.default_rng(semente)
    ult = vol.mes.max()
    rec = vol[vol.mes > ult - pd.DateOffset(months=12)]
    dias = meses.days_in_month.to_numpy()

    linhas, tot, cen_op = [], {}, {}
    total_rec = np.zeros((n_sim, len(meses))); total_roy = np.zeros((n_sim, len(meses)))
    # Valor central: volume P50 × cenário base de preço (Brent base e câmbio mediano). A mediana da receita
    # simulada não serve como centro: quando a faixa de volume é assimétrica (P10 muito abaixo do P50),
    # a mediana do produto volume × preço fica abaixo de P50 × preço base e o viés cresce com o horizonte.
    fx_med = np.median(F, axis=0)
    cen_rec = np.zeros(len(meses)); cen_roy = np.zeros(len(meses))
    z_comum = rng.standard_normal((n_sim, 1))     # choque comum: unidades erram juntas (correlação rho)
    for u, g in prev.groupby("unidade"):
        g = g.set_index("mes").reindex(meses)
        p50 = g.p50.to_numpy().clip(1e-6); p10 = g.p10.to_numpy().clip(1e-6); p90 = g.p90.to_numpy().clip(1e-6)
        s_lo, s_hi = np.log(p50 / p10) / Z90, np.log(p90 / p50) / Z90
        z = np.sqrt(rho) * z_comum + np.sqrt(1 - rho) * rng.standard_normal((n_sim, 1))
        prod = p50[None, :] * np.exp(np.where(z < 0, s_lo, s_hi) * z)       # bbl/dia
        sub = rec[rec.unidade == u].groupby("campo_n").agg(o=("oleo_m3", "sum"), gm=("gas_m3", "sum"),
                                                           campo=("campo", "first"))
        if sub.o.sum() <= 0:
            continue
        sub["share"] = sub.o / sub.o.sum()
        rgo = sub.gm.sum() / sub.o.sum()                                    # m³ gás / m³ óleo
        oleo_m3 = prod * dias[None, :] / M3_BBL
        receita = np.zeros_like(oleo_m3); roy = np.zeros_like(oleo_m3); pe = np.zeros(len(meses))
        oleo_c = p50 * dias / M3_BBL; rec_cen = np.zeros(len(meses)); roy_cen = np.zeros(len(meses))
        for c, r in sub.iterrows():
            pr = B * precos.k * precos.fator.get(c, 1.0) * F * M3_BBL                # R$/m³
            gas_c = precos.gas_recente.get(c, precos.gas_medio)
            rec_c = oleo_m3 * r.share * pr + oleo_m3 * r.share * rgo * gas_c
            receita += rec_c
            roy += rec_c * regra_aliq(r.campo) * lam
            pr_c = base_b * precos.k * precos.fator.get(c, 1.0) * fx_med * M3_BBL
            rc_c = oleo_c * r.share * pr_c + oleo_c * r.share * rgo * gas_c
            rec_cen += rc_c; roy_cen += rc_c * regra_aliq(r.campo) * lam
            pe += rc_c * pe_taxa.get(c, 0.0)
        op = operadores.get(u, "Outras")
        tot.setdefault(op, [np.zeros_like(receita), np.zeros_like(roy)])
        tot[op][0] += receita; tot[op][1] += roy
        total_rec += receita; total_roy += roy
        cen_rec += rec_cen; cen_roy += roy_cen
        cen_op.setdefault(op, [np.zeros(len(meses)), np.zeros(len(meses))])
        cen_op[op][0] += rec_cen; cen_op[op][1] += roy_cen
        for j, m in enumerate(meses):
            linhas.append(dict(unidade=u, operador=op, mes=m, producao_p10=p10[j], producao_p50=p50[j],
                               producao_p90=p90[j],
                               receita_p10=np.percentile(receita[:, j], 10), receita_p50=rec_cen[j],
                               receita_p90=np.percentile(receita[:, j], 90),
                               royalties_p10=np.percentile(roy[:, j], 10), royalties_p50=roy_cen[j],
                               royalties_p90=np.percentile(roy[:, j], 90), pe_estimada=pe[j]))

    def resumo(rec_, roy_, crec, croy, nome):
        # p50 = valor central (volume P50 × preço base); p10/p90 = percentis da simulação
        return [dict(grupo=nome, mes=m, receita_p10=min(np.percentile(rec_[:, j], 10), crec[j]), receita_p50=crec[j],
                     receita_p90=max(np.percentile(rec_[:, j], 90), crec[j]), royalties_p10=min(np.percentile(roy_[:, j], 10), croy[j]),
                     royalties_p50=croy[j], royalties_p90=max(np.percentile(roy_[:, j], 90), croy[j]))
                for j, m in enumerate(meses)]
    por_op = pd.DataFrame([x for op, (a, b) in tot.items() for x in resumo(a, b, *cen_op[op], op)])
    brasil = pd.DataFrame(resumo(total_rec, total_roy, cen_rec, cen_roy, "Brasil (unidades modeladas)"))
    mercado = pd.DataFrame({"mes": meses, "brent_base": base_b, "brent_p10": np.percentile(B, 10, 0),
                            "brent_p90": np.percentile(B, 90, 0), "ptax_p50": np.percentile(F, 50, 0),
                            "ptax_p10": np.percentile(F, 10, 0), "ptax_p90": np.percentile(F, 90, 0)})
    return pd.DataFrame(linhas), por_op, brasil, mercado


# --------------------------------------------------------------------------
# Ponte de variação (previsto × realizado)
# --------------------------------------------------------------------------
def ponte(bt_origem: pd.DataFrame, vol: pd.DataFrame, precos: Precos) -> pd.DataFrame:
    """bt_origem: previsões do backtest numa origem (unidade, mes_alvo, ml, real).
    Premissa da previsão: preço (US$/bbl) e câmbio do mês de origem constantes."""
    o = bt_origem.origem.iloc[0]
    linhas = []
    for _, r in bt_origem.iterrows():
        sub = vol[(vol.unidade == r.unidade) & (vol.mes <= o) & (vol.mes > o - pd.DateOffset(months=12))]
        if sub.oleo_m3.sum() <= 0:
            continue
        share = sub.groupby("campo_n").oleo_m3.sum() / sub.oleo_m3.sum()
        p_prev = sum(w * precos.petroleo(c, o) for c, w in share.items()) / M3_BBL / precos.ptax[o]
        p_real = sum(w * precos.petroleo(c, r.mes_alvo) for c, w in share.items()) / M3_BBL / precos.ptax[r.mes_alvo]
        d = r.mes_alvo.days_in_month
        linhas.append(dict(unidade=r.unidade, mes=r.mes_alvo, bbl_prev=r.ml * d, bbl_real=r.real * d,
                           preco_prev=p_prev, preco_real=p_real, fx_prev=precos.ptax[o], fx_real=precos.ptax[r.mes_alvo]))
    d = pd.DataFrame(linhas)
    d["receita_prevista"] = d.bbl_prev * d.preco_prev * d.fx_prev
    d["receita_realizada"] = d.bbl_real * d.preco_real * d.fx_real
    d["efeito_volume"] = (d.bbl_real - d.bbl_prev) * d.preco_prev * d.fx_prev
    d["efeito_preco"] = d.bbl_real * (d.preco_real - d.preco_prev) * d.fx_prev
    d["efeito_cambio"] = d.bbl_real * d.preco_real * (d.fx_real - d.fx_prev)
    d["origem"] = o
    return d

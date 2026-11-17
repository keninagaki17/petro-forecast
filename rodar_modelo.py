"""
rodar_modelo.py — pipeline completo: base → torneio de métodos → previsão → royalties → relatório.

    python rodar_modelo.py               # usa dados_brutos/ (coleta_dados.py)
    python rodar_modelo.py --reusar      # reaproveita as amostras já calculadas

Saídas em saidas/ (lidas pelo painel: streamlit run app.py)
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src import acompanhamento, amostras as amo, capacidade, dados, graficos, modelo, participacoes as partic, precos as pr, rampa, receita as rc, royalties_municipios
from src.unidades import unidade

RAIZ = Path(__file__).resolve().parent


def carregar_pocos(pasta: Path) -> pd.DataFrame:
    bruto = pasta / "anp" / "producao_mar"
    if bruto.exists() and any(bruto.rglob("*.csv")):
        d = dados.carregar_producao(bruto)
    else:
        pacote = pasta / "pocos_mes.csv.gz"
        print(f"  (usando {pacote.name})")
        d = pd.read_csv(pacote)
        d["mes"] = pd.to_datetime(d["mes"].astype(str).str[:7] + "-01")
    return dados.completar_compartilhados(d, RAIZ)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", default=str(RAIZ / "dados_brutos"))
    ap.add_argument("--saidas", default=str(RAIZ / "saidas"))
    ap.add_argument("--reusar", action="store_true")
    ap.add_argument("--sims", type=int, default=2000)
    a = ap.parse_args()
    pasta, saidas = Path(a.dados), Path(a.saidas)
    saidas.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    print("[1/7] Base de produção")
    pocos = carregar_pocos(pasta)
    tot = pocos.groupby("mes").petroleo_bpd.sum()
    lacunas = [m.strftime("%Y-%m") for m in pd.date_range(tot.index.min(), tot.index.max(), freq="MS")
               if tot.get(m, 0) <= 0]
    ultimo = pocos.mes.max()
    print(f"  {pocos.poco.nunique():,} poços, {pocos.campo.nunique()} campos, até {ultimo:%Y-%m}; "
          f"meses sem dados: {len(lacunas)}")

    print("[2/7] Amostras (métodos simples + variáveis)")
    arq = saidas / "amostras.pkl"
    if a.reusar and arq.exists():
        df = pd.read_pickle(arq)
    else:
        df = amo.construir(pocos)
        df.to_pickle(arq)
    df = modelo.preparar(df)
    print(f"  {len(df):,} linhas, {df.unidade.nunique()} unidades")

    print("[3/7] Torneio (backtest mensal desde 2010)")
    origens = sorted(df.loc[(df.origem >= "2010-01-01") & df.real.notna(), "origem"].unique())
    df["ml"] = modelo.backtest(df, origens, passo_meses=6)
    cap = capacidade.tabela_capacidade(pocos, RAIZ)
    df = capacidade.aplicar_teto(df, cap, ["ml"])
    bt = df[df.origem.isin(origens)].copy()
    # combinação com o ingênuo nos primeiros meses: pesos escolhidos só com origens até 2018
    dev = bt[(bt.origem < "2019-01-01") & bt.real.notna()]
    if dev.empty:
        dev = bt[bt.real.notna()]
    pesos = modelo.pesos_combinacao(dev)
    bt["final"] = modelo.combinar(bt, pesos)
    # plataformas novas: no backtest, simula conhecer a data de entrada (como os anúncios de hoje)
    hist_rampa = rampa.historico_rampas(pocos, RAIZ)
    bt = rampa.somar_projetos_backtest(bt, hist_rampa, ["final", "m_ingenuo"])
    metodos = {"m_ingenuo": "Ingênuo (repete o último mês)", "m_media3": "Média dos últimos 3 meses",
               "m_arps": "Curva de declínio (Arps) da unidade", "m_arps_pocos": "Arps poço a poço",
               "m_ets": "Suavização exponencial (ETS)", "ml": "ML (LightGBM híbrido + teto de capacidade)",
               "final": "ML + ingênuo nos meses iniciais",
               "m_ingenuo_proj": "Ingênuo + plataformas novas",
               "final_proj": "Modelo final (ML + plataformas novas)"}
    periodos = {"Tudo": bt.origem >= "2010-01-01",
                "2010–2018": bt.origem < "2019-01-01",
                "2022 em diante": bt.origem >= "2022-01-01"}
    tabelas = {}
    for nome, m in periodos.items():
        if m.any():
            t = modelo.metricas(bt[m], list(metodos)).rename(index=metodos)
            tabelas[nome] = t
            print(f"\n  {nome}\n{t.round(4).to_string()}")
    por_h = modelo.metricas_por_h(bt, list(metodos)).rename(columns=metodos)
    por_h.to_csv(saidas / "backtest_por_horizonte.csv", index=False)
    pd.concat(tabelas, names=["periodo", "metodo"]).to_csv(saidas / "torneio.csv")
    bt[["unidade", "origem", "h", "mes_alvo", "base", "real", "porte"] + list(metodos)].to_csv(
        saidas / "backtest_previsoes.csv.gz", index=False, compression="gzip")

    # Faixas: calibradas no passado e testadas no período recente (honesto)
    corte = pd.Timestamp("2022-01-01")
    janela = pd.Timestamp("2014-01-01")      # erros da última década (era do pré-sal)
    q_antigo = modelo.quantis_erro(bt[(bt.mes_alvo < corte) & (bt.mes_alvo >= janela)], "final_proj")
    recente = modelo.aplicar_faixas(bt[(bt.origem >= corte) & bt.real.notna()], q_antigo, "final_proj")
    cobertura = float(((recente.real >= recente.p10) & (recente.real <= recente.p90)).mean())
    q_final = modelo.quantis_erro(bt[bt.mes_alvo >= janela], "final_proj")
    print(f"\n  cobertura P10–P90 no período recente: {cobertura:.1%}")
    anual, anual_det = modelo.erro_anual(bt, ["m_ingenuo", "m_arps", "m_ets", "final", "m_ingenuo_proj", "final_proj"])
    anual.rename(index=metodos).to_csv(saidas / "erro_anual.csv")
    print(anual.rename(index=metodos).round(4).to_string())
    rho = modelo.correlacao_erros(bt, "final_proj")
    print(f"  correlação média dos erros entre unidades: {rho:.2f}")

    print("[4/7] Modelo final e previsão de 18 meses")
    final = modelo.treinar(df[df.real.notna()])
    atual = df[df.origem == df.origem.max()].copy()
    atual["ml"] = modelo.prever(final, atual)
    atual = capacidade.aplicar_teto(atual.drop(columns="capacidade"), cap, ["ml"])
    atual["final"] = modelo.combinar(atual, pesos)
    prev = modelo.aplicar_faixas(atual, q_final, "final")
    prev = capacidade.aplicar_teto(prev.drop(columns="capacidade"), cap, ["p10", "p50", "p90"])
    prev = prev.rename(columns={"mes_alvo": "mes"})[["unidade", "bacia", "mes", "h", "base", "ultimo",
                                                     "m_arps", "p10", "p50", "p90"]]
    fat = pd.concat([modelo.fatores(final, atual[atual.h == h]) for h in (6, 12)])
    fat.to_csv(saidas / "fatores_previsao.csv", index=False)

    # Plataformas anunciadas (curva de rampa aprendida do histórico)
    av_rampa = rampa.avaliar(hist_rampa)
    av_rampa.to_csv(saidas / "rampa_validacao.csv", index=False)
    rampa.curva(hist_rampa).to_csv(saidas / "curva_rampa.csv")
    rampa.resumo_plataformas(hist_rampa).to_csv(saidas / "rampas_plataformas.csv", index=False)
    erro_rampa = {"curva": float(av_rampa.erro_curva.sum() / av_rampa.real.sum()),
                  "linear": float(av_rampa.erro_linear.sum() / av_rampa.real.sum()), "n": int(len(av_rampa))}
    print(f"  rampa: erro {erro_rampa['curva']:.1%} (curva aprendida) vs {erro_rampa['linear']:.1%} (linear), "
          f"{erro_rampa['n']} plataformas")
    projetos = pd.read_csv(RAIZ / "config" / "projetos.csv", comment="#")
    proj = rampa.projetar(projetos, hist_rampa, pd.DatetimeIndex(sorted(prev.mes.unique())))
    proj.to_csv(saidas / "previsao_projetos.csv", index=False)
    soma = proj.groupby(["unidade", "mes"])[["p10", "p50", "p90"]].sum()
    prev = prev.set_index(["unidade", "mes"])
    prev["projetos_p50"] = soma["p50"].reindex(prev.index).fillna(0.0)
    for c in ("p10", "p50", "p90"):
        prev[c] = prev[c] + soma[c].reindex(prev.index).fillna(0.0)
    prev = prev.reset_index()
    cfg_op = pd.read_csv(RAIZ / "config" / "operadores.csv", comment="#")  # reserva, se faltar a planilha da ANP
    operadores = dict(zip(cfg_op.unidade, cfg_op.operador))
    prev["operador"] = prev.unidade.map(operadores).fillna("Outras")
    prev.to_csv(saidas / "previsao_producao.csv", index=False)
    imp = pd.Series(final.feature_importances_, index=modelo.FEATS + modelo.REL).sort_values(ascending=False)
    imp.rename("importancia").to_csv(saidas / "importancia_variaveis.csv")

    print("[5/7] Preços, royalties e calibração")
    pg = pasta / "anp" / "participacoes_governamentais"
    if not pg.exists():
        pg = pasta / "anp_extra" / "participacoes_governamentais"
    merc = pasta / "mercado"
    vol = rc.volumes_campo(pocos)
    part_base = partic.participacoes_base(RAIZ, pasta / "anp" / "concessionarios")
    aip = partic.carregar_aip(RAIZ)
    part = None if part_base is None else partic.aplicar_aip(part_base, aip)
    if part is not None:
        operadores = {**operadores, **partic.operador_por_unidade(part, vol)}
        prev["operador"] = prev.unidade.map(operadores).fillna("Outras")
        prev.to_csv(saidas / "previsao_producao.csv", index=False)
        part.to_csv(saidas / "participacoes_campo.csv", index=False)
        partic.pesos_unidade(vol, part).to_csv(saidas / "pesos_unidade_empresa.csv", index=False)
        print(f"  participações: {part.campo.nunique()} campos, {part.empresa.nunique()} empresas")
    precos = rc.Precos(pr.precos_petroleo(pg), pr.precos_gas(pg), pr.ptax(merc), pr.brent(RAIZ, merc), vol)
    regra = rc.aliquotas(RAIZ)
    # histórico de preços (base da aba de premissas do painel): Brent, câmbio e preço médio da ANP em US$
    pd.DataFrame({"brent": precos.brent, "ptax": precos.ptax, "anp_usd": precos.indice_usd}).rename_axis("mes").reset_index()\
        .to_csv(saidas / "precos_historicos.csv", index=False)
    hist = rc.royalties_historicos(vol, precos, regra)
    lam, calib = rc.calibrar(hist, pr.royalties_nacional(pg))
    calib.to_csv(saidas / "calibracao_royalties.csv")
    # receita e royalties realizados por campo (base do previsto × realizado em R$ no painel)
    rh = hist[hist.mes >= hist.mes.max() - pd.DateOffset(months=60)].groupby(["unidade", "mes"])[["receita", "royalties"]].sum().reset_index()
    rh["royalties"] = rh.royalties * lam
    rh.to_csv(saidas / "receita_historica.csv", index=False)
    pe_taxa = rc.taxa_pe(hist, pr.pe_por_campo(pg))
    print(f"  k (preço ANP / Brent) = {precos.k:.3f}; fator de calibração = {lam:.3f}")
    rec22 = calib[calib.index >= "2022-01-01"]
    print(f"  erro médio absoluto mensal vs arrecadação (2022+): {rec22.erro_pct.abs().mean():.1%}")

    print("[6/7] Receita e royalties projetados (Monte Carlo)")
    por_u, por_op, brasil, mercado = rc.projetar(prev, vol, precos, regra, lam, pe_taxa, operadores,
                                                 n_sim=a.sims, rho=rho)
    por_u.to_csv(saidas / "previsao_receita_royalties.csv", index=False)
    por_op.to_csv(saidas / "previsao_por_operadora.csv", index=False)
    brasil.to_csv(saidas / "previsao_brasil.csv", index=False)
    mercado.to_csv(saidas / "cenario_mercado.csv", index=False)
    guidance = None
    if part is not None:
        hist_liq = partic.liquida_historica(vol, part_base, aip)
        prev_liq = partic.liquida_prevista(por_u, vol, part)
        hist_liq.to_csv(saidas / "producao_liquida_historica.csv", index=False)
        prev_liq.to_csv(saidas / "previsao_liquida_empresas.csv", index=False)
        # Petrobras: ano corrente = meses realizados + previsão, comparado à meta divulgada
        ano = ultimo.year
        cfg_g = RAIZ / "config" / "metas_empresas.csv"
        if cfg_g.exists():
            metas = pd.read_csv(cfg_g, comment="#")
            res = []
            for _, mt in metas[metas.ano == ano].iterrows():
                real = hist_liq[(hist_liq.empresa == mt.empresa) & (hist_liq.mes.dt.year == ano)]
                fut = prev_liq[(prev_liq.empresa == mt.empresa) & (prev_liq.mes.dt.year == ano)]
                serie = pd.concat([real.set_index("mes").oleo_liq, fut.set_index("mes").producao_liq])
                serie = serie[~serie.index.duplicated()]
                dias = pd.Series(serie.index.days_in_month, index=serie.index)
                media = float((serie * dias).sum() / dias.sum()) if len(serie) == 12 else float("nan")
                ant = hist_liq[(hist_liq.empresa == mt.empresa) & (hist_liq.mes.dt.year == ano - 1)].oleo_liq.mean()
                fator = mt.realizado_ano_anterior_bpd / ant if mt.realizado_ano_anterior_bpd > 0 else 1.0
                res.append(dict(empresa=mt.empresa, ano=ano, meta_bpd=mt.meta_bpd,
                                modelo_base_anp_bpd=media, fator_escopo=fator, modelo_ajustado_bpd=media * fator,
                                meses_realizados=len(real), fonte=mt.fonte))
            guidance = pd.DataFrame(res)
            guidance.to_csv(saidas / "comparacao_metas.csv", index=False)
            print(guidance.round(3).to_string(index=False))

    # Ponte: origem mais recente com 12 meses realizados
    o12 = sorted(bt.loc[(bt.h == 12) & bt.real.notna(), "origem"].unique())
    pt = None
    if o12:
        o = pd.Timestamp(o12[-1])
        janela = bt[(bt.origem == o) & (bt.h <= 12) & bt.real.notna()]
        pt = rc.ponte(janela.assign(ml=janela["final_proj"]), vol, precos)
        pt.to_csv(saidas / "ponte_variacao.csv", index=False)

    print("[7/7] Gráficos e relatório")
    graficos.erro_por_horizonte(por_h, saidas / "erro_por_horizonte.png")
    top = (prev[prev.h == 1].sort_values("p50", ascending=False).unidade.head(6).tolist())
    hist_u = pocos.assign(unidade=pocos.campo.map(unidade)).groupby(["unidade", "mes"]).petroleo_bpd.sum().reset_index()
    validos = tot[tot > 0].index
    hist_u[hist_u.mes.isin(validos)].to_csv(saidas / "base_unidades.csv", index=False)
    hist_u = hist_u[hist_u.mes.isin(validos)]
    # previsto × realizado: guarda a previsão desta rodada e compara as anteriores com o que já foi publicado
    acompanhamento.arquivar(prev, saidas, ultimo)
    prev_real = acompanhamento.comparar(saidas, hist_u, bt, ultimo)
    prev_real.to_csv(saidas / "previsto_realizado.csv.gz", index=False)
    # royalties por município e estado: fatias estimadas pelo histórico da ANP aplicadas à previsão por campo
    h_roy = hist[hist.mes >= "2015-01-01"].assign(royalties=lambda d: d.royalties * lam)\
        .groupby(["unidade", "campo_n", "mes"], as_index=False)[["receita", "royalties"]].sum()
    h_roy.to_csv(saidas / "royalties_campo_historico.csv", index=False)
    pc = pocos[pocos.mes >= "2015-01-01"].assign(uf=lambda d: d.poco.str.extract(r"-([A-Z]{2})S?$")[0])
    campo_uf = pc.groupby(["campo", "uf"]).petroleo_bpd.sum().reset_index().sort_values("petroleo_bpd")\
        .drop_duplicates("campo", keep="last")
    campo_uf.to_csv(saidas / "campo_uf.csv", index=False)
    serie_b, res_b = royalties_municipios.montar(pg, h_roy, dict(zip(campo_uf.campo.str.upper(), campo_uf.uf)),
                                                 por_u, brasil, prev_real)
    serie_b.to_csv(saidas / "royalties_beneficiarios.csv", index=False)
    res_b.to_csv(saidas / "royalties_beneficiarios_resumo.csv", index=False)
    hist_u.columns = ["campo", "mes", "petroleo_bpd"]
    graficos.leque_campos(hist_u, prev.rename(columns={"unidade": "campo", "p10": "p10_bpd", "p50": "p50_bpd",
                                                      "p90": "p90_bpd"}), top, saidas / "previsao_maiores.png")
    if pt is not None:
        graficos.cascata_ponte(pt, saidas / "ponte_variacao.png",
                               f"Receita de petróleo prevista em {pt.origem.iloc[0]:%m/%Y} × realizada (12 meses)")
    graficos.calibracao(calib, saidas / "calibracao_royalties.png")

    resumo = dict(rho=rho, rampa=erro_rampa, anual=anual.round(4).to_dict(orient="index"), pesos_combinacao={int(k): float(v) for k, v in pesos.items()}, ultimo_mes=f"{ultimo:%Y-%m}", lacunas=lacunas, n_pocos=int(pocos.poco.nunique()),
                  n_unidades=int(df.unidade.nunique()), n_origens=len(origens), cobertura_p10_p90=cobertura,
                  k_preco_brent=precos.k, fator_calibracao=lam, ultimo_preco_anp=f"{precos.ultimo_prp:%Y-%m}",
                  erro_calibracao_2022=float(rec22.erro_pct.abs().mean()),
                  torneio={k: v.round(4).to_dict(orient="index") for k, v in tabelas.items()})
    (saidas / "resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\nPronto em {time.time() - t0:,.0f}s")


if __name__ == "__main__":
    main()

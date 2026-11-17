"""Painel web do projeto.  Rodar:  streamlit run app.py"""
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

RAIZ = Path(__file__).resolve().parent
S = RAIZ / "saidas"
AZUL, CINZA, LARANJA, VERDE, VERMELHO = "#2a78d6", "#52514e", "#eb6834", "#1baf7a", "#e34948"

st.set_page_config(page_title="Previsão de produção e royalties — offshore Brasil", layout="wide")


def br(x, casas=1):
    return f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


@st.cache_data
def ler(nome, **kw):
    return pd.read_csv(S / nome, **kw)


resumo = json.loads((S / "resumo.json").read_text(encoding="utf-8"))
prev = ler("previsao_producao.csv", parse_dates=["mes"])
rec = ler("previsao_receita_royalties.csv", parse_dates=["mes"])
base = ler("base_unidades.csv", parse_dates=["mes"])
brasil = ler("previsao_brasil.csv", parse_dates=["mes"])
por_op = ler("previsao_por_operadora.csv", parse_dates=["mes"])

st.title("Previsão de produção, receita e royalties — petróleo offshore no Brasil")
st.caption(f"Dados públicos da ANP até {resumo['ultimo_mes']}. Previsão para os próximos 18 meses, "
           "com faixa de incerteza P10–P90. Projeto educacional; não é recomendação de investimento.")

# ------------------------------------------------------------------ filtros
ops = ["Todas"] + sorted(prev.operador.unique())
c1, c2 = st.columns([1, 2])
op = c1.selectbox("Operadora", ops)
unids = prev if op == "Todas" else prev[prev.operador == op]
ordem = unids[unids.h == 1].sort_values("p50", ascending=False).unidade.tolist()
sel = c2.multiselect("Unidades (campos)", ordem, default=ordem[:1] if op == "Todas" else ordem)
if not sel:
    sel = ordem

p = prev[prev.unidade.isin(sel)].groupby("mes")[["p10", "p50", "p90"]].sum().reset_index()
h = base[base.unidade.isin(sel)].groupby("mes").petroleo_bpd.sum().reset_index()
h = h[h.mes >= h.mes.max() - pd.DateOffset(months=48)]
r = rec[rec.unidade.isin(sel)]

k1, k2, k3, k4 = st.columns(4)
p12 = p.head(12)
k1.metric("Produção média prevista, 12 meses", f"{br(p12.p50.mean() / 1000, 0)} mil bbl/d",
          f"{br((p12.p50.mean() / h.tail(3).petroleo_bpd.mean() - 1) * 100)}% vs últimos 3 meses")
k2.metric("Receita bruta prevista, 12 meses (P50)", f"R$ {br(r[r.mes.isin(p12.mes)].receita_p50.sum() / 1e9)} bi")
k3.metric("Royalties previstos, 12 meses (P50)", f"R$ {br(r[r.mes.isin(p12.mes)].royalties_p50.sum() / 1e9)} bi")
k4.metric("Participação especial estimada, 12 meses", f"R$ {br(r[r.mes.isin(p12.mes)].pe_estimada.sum() / 1e9)} bi")
if len(sel) > 1:
    st.caption("Com mais de uma unidade selecionada, a faixa P10–P90 é a soma das faixas individuais "
               "(conservadora). Os totais por operadora e Brasil na aba Royalties usam a simulação conjunta.")

aba1, aba_emp, aba2, aba3, aba4, aba5 = st.tabs(["Produção", "Por empresa", "Receita e royalties",
                                                 "Acurácia do modelo", "Previsto × realizado", "Premissas"])

with aba1:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=p.mes, y=p.p90 / 1000, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=p.mes, y=p.p10 / 1000, fill="tonexty", fillcolor="rgba(42,120,214,0.18)",
                             line=dict(width=0), name="Faixa P10–P90"))
    fig.add_trace(go.Scatter(x=h.mes, y=h.petroleo_bpd / 1000, line=dict(color=CINZA, width=2), name="Realizado"))
    fig.add_trace(go.Scatter(x=p.mes, y=p.p50 / 1000, line=dict(color=AZUL, width=2.5), name="Previsão P50"))
    fig.update_layout(height=430, yaxis_title="mil bbl/dia", hovermode="x unified", margin=dict(t=20),
                      legend=dict(orientation="h", y=1.08))
    st.plotly_chart(fig, width="stretch")
    proj = ler("previsao_projetos.csv", parse_dates=["mes"])
    proj = proj[proj.unidade.isin(sel)]
    if not proj.empty:
        st.markdown("**Plataformas anunciadas incluídas na previsão** (curva de rampa aprendida do histórico)")
        resumo_p = proj.groupby("instalacao").apply(lambda g: pd.Series({
            "1º óleo (P50)": g.loc[g.p50 > 0, "mes"].min().strftime("%m/%Y") if (g.p50 > 0).any() else "após o horizonte",
            "Produção no último mês (mil bbl/d, P50)": round(g.p50.iloc[-1] / 1000, 0)}))
        st.dataframe(resumo_p, width="stretch")
    fat = ler("fatores_previsao.csv")
    fat = fat[fat.unidade.isin(sel)]
    if not fat.empty:
        st.markdown("**Por que o modelo prevê isso?** Principais fatores da previsão de cada unidade "
                    "(contribuição de cada variável, em % da produção atual)")
        f2 = fat.pivot_table(index="unidade", columns="h", values="fatores", aggfunc="first")
        f2.columns = [f"Em {c} meses" for c in f2.columns]
        st.dataframe(f2, width="stretch")
    tab = prev[prev.h.isin([1, 6, 12, 18])].pivot_table(index=["unidade", "operador"], columns="h", values="p50")
    tab.columns = [f"P50 em {c} meses" for c in tab.columns]
    st.dataframe((tab / 1000).round(1).sort_values(tab.columns[0], ascending=False), width="stretch")

with aba_emp:
    if (S / "previsao_liquida_empresas.csv").exists():
        hl = ler("producao_liquida_historica.csv", parse_dates=["mes"])
        pl = ler("previsao_liquida_empresas.csv", parse_dates=["mes"])
        top = pl.groupby("empresa").producao_liq.mean().sort_values(ascending=False)
        top = [e for e in top.index if e != "Outras"][:12]
        emp = st.selectbox("Empresa", top, index=top.index("TotalEnergies") if "TotalEnergies" in top else 0)
        h2 = hl[(hl.empresa == emp) & (hl.mes >= hl.mes.max() - pd.DateOffset(months=36))]
        p2 = pl[pl.empresa == emp]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=h2.mes, y=h2.oleo_liq / 1000, line=dict(color=CINZA, width=2), name="Realizado"))
        fig.add_trace(go.Scatter(x=p2.mes, y=p2.producao_liq / 1000, line=dict(color=AZUL, width=2.5), name="Previsão P50"))
        fig.update_layout(height=380, yaxis_title="mil bbl/dia", margin=dict(t=20), hovermode="x unified",
                          legend=dict(orientation="h", y=1.08))
        st.plotly_chart(fig, width="stretch")
        p12 = p2.head(12)
        c1, c2, c3 = st.columns(3)
        c1.metric("Produção da parte da empresa, 12 meses", f"{br(p12.producao_liq.mean() / 1000, 0)} mil bbl/d")
        c2.metric("Receita bruta, 12 meses (P50)", f"R$ {br(p12.receita_liq.sum() / 1e9)} bi")
        c3.metric("Royalties + PE, 12 meses", f"R$ {br((p12.royalties_liq.sum() + p12.pe_liq.sum()) / 1e9)} bi")
        part = ler("participacoes_campo.csv")
        tab = part[part.empresa == emp][["campo", "pct", "operador"]].sort_values("pct", ascending=False)
        tab["pct"] = (tab.pct * 100).round(1)
        tab.columns = ["Campo", "Participação (%)", "É a operadora"]
        st.dataframe(tab, width="stretch", hide_index=True)
        st.caption("Participação no contrato (working interest), segundo a Relação de Concessionários da ANP. "
                   "Nos contratos de partilha, a empresa ainda entrega à União a parcela de excedente em óleo, "
                   "que não está descontada aqui.")
        if (S / "comparacao_metas.csv").exists():
            cm = ler("comparacao_metas.csv")
            for _, r in cm.iterrows():
                st.info(f"**{r.empresa} {int(r.ano)}**: meta divulgada {br(r.meta_bpd / 1e6, 2)} milhões bbl/d. "
                        f"Modelo ({int(r.meses_realizados)} meses realizados + previsão): "
                        f"{br(r.modelo_ajustado_bpd / 1e6, 2)} milhões bbl/d no escopo da empresa "
                        f"({br(r.modelo_base_anp_bpd / 1e6, 2)} na base marítima da ANP).")
    else:
        st.write("Sem a Relação de Concessionários da ANP em dados_brutos/anp/concessionarios.")

with aba2:
    st.subheader("Royalties previstos por operadora (R$ milhões por mês, P50)")
    piv = por_op.pivot_table(index="mes", columns="grupo", values="royalties_p50") / 1e6
    fig = go.Figure()
    for i, c in enumerate(piv.sum().sort_values(ascending=False).index):
        fig.add_trace(go.Bar(x=piv.index, y=piv[c], name=c))
    fig.update_layout(barmode="stack", height=400, margin=dict(t=20), legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, width="stretch")
    b = brasil
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=b.mes, y=b.royalties_p90 / 1e9, line=dict(width=0), showlegend=False))
    fig.add_trace(go.Scatter(x=b.mes, y=b.royalties_p10 / 1e9, fill="tonexty", fillcolor="rgba(42,120,214,0.18)",
                             line=dict(width=0), name="P10–P90"))
    fig.add_trace(go.Scatter(x=b.mes, y=b.royalties_p50 / 1e9, line=dict(color=AZUL, width=2.5), name="P50"))
    fig.update_layout(title="Royalties — total das unidades modeladas (R$ bilhões/mês)", height=360, margin=dict(t=50))
    st.plotly_chart(fig, width="stretch")
    st.image(str(S / "calibracao_royalties.png"))
    st.caption(f"O cálculo de royalties reproduz a arrecadação publicada pela ANP com erro médio de "
               f"{resumo['erro_calibracao_2022']:.1%} por mês desde 2022 (fator de calibração "
               f"{resumo['fator_calibracao']:.3f}).")

with aba3:
    st.subheader("Torneio de métodos (backtest: cada previsão usa só dados anteriores à data)")
    t = pd.read_csv(S / "torneio.csv")
    periodo = st.radio("Período das origens", t.periodo.unique(), horizontal=True)
    tt = t[t.periodo == periodo].drop(columns="periodo").set_index("metodo")
    st.dataframe(tt.style.format("{:.1%}"), width="stretch")
    st.image(str(S / "erro_por_horizonte.png"))
    st.subheader("Erro no nível do orçamento anual")
    st.caption("Previsão feita em dezembro para a média do ano seguinte, como num budget anual.")
    an = pd.read_csv(S / "erro_anual.csv", index_col=0)
    st.dataframe(an[["WAPE anual por unidade", "Erro anual da carteira"]].style.format("{:.1%}"), width="stretch")
    st.subheader("Curva de rampa de plataformas novas")
    rv = resumo.get("rampa", {})
    if rv:
        st.caption(f"Validação deixando cada plataforma de fora ({rv['n']} plataformas desde 2010): erro de "
                   f"{rv['curva']:.0%} com a curva aprendida contra {rv['linear']:.0%} supondo rampa linear de 12 meses.")
    st.caption(f"WAPE = soma dos erros absolutos ÷ soma do realizado (pondera pelo volume). "
               f"Erro da carteira = erro da soma de todas as unidades. Cobertura da faixa P10–P90 no período "
               f"recente: {resumo['cobertura_p10_p90']:.0%} (ideal ≈ 80%).")

with aba4:
    if (S / "previsto_realizado.csv.gz").exists():
        pr = ler("previsto_realizado.csv.gz", parse_dates=["mes"])
        st.subheader("Previsto × realizado")
        hsel = st.radio("Previsão feita quantos meses antes?", [1, 3, 6, 12], index=2, horizontal=True)
        t = pr[pr.h == hsel].groupby("mes")[["previsto", "ingenuo", "real"]].sum() / 1e3
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=t.index, y=t.real, name="Realizado", line=dict(width=2.5)))
        fig.add_trace(go.Scatter(x=t.index, y=t.previsto, name="Modelo", line=dict(color=LARANJA, width=2)))
        fig.add_trace(go.Scatter(x=t.index, y=t.ingenuo, name="Repetir o último mês", line=dict(color="gray", dash="dot")))
        fig.update_layout(height=340, margin=dict(t=30), yaxis_title="mil bbl/d")
        st.plotly_chart(fig, width="stretch")
        u12 = t.tail(12)
        c1, c2, c3 = st.columns(3)
        c1.metric("Erro médio em 12 meses (modelo)", f"{br(((u12.previsto - u12.real).abs() / u12.real).mean() * 100)}%")
        c2.metric("Repetir o último mês", f"{br(((u12.ingenuo - u12.real).abs() / u12.real).mean() * 100)}%")
        c3.metric("Viés do modelo", f"{br(((u12.previsto - u12.real) / u12.real).mean() * 100)}%")
        publ = (pr.fonte == "publicada").mean()
        st.caption(f"Previsões publicadas e guardadas em saidas/historico: {publ:.0%} das linhas. O restante é teste retroativo "
                   "(o que o modelo teria previsto na data, treinado só com dados anteriores). A cada rodada mensal, "
                   "a previsão é guardada e passa a entrar aqui quando o realizado é publicado.")
    if (S / "ponte_variacao.png").exists():
        st.image(str(S / "ponte_variacao.png"))
        pt = ler("ponte_variacao.csv", parse_dates=["mes"])
        g = pt.groupby("unidade")[["receita_prevista", "efeito_volume", "efeito_preco", "efeito_cambio",
                                   "receita_realizada"]].sum().sort_values("receita_realizada", ascending=False) / 1e6
        st.dataframe(g.round(0), width="stretch")
        st.caption("Premissa da previsão: preço e câmbio do mês de origem constantes. "
                   "A soma dos três efeitos fecha exatamente com a variação total.")

with aba5:
    m = ler("cenario_mercado.csv", parse_dates=["mes"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=m.mes, y=m.brent_p90, line=dict(width=0), showlegend=False))
    fig.add_trace(go.Scatter(x=m.mes, y=m.brent_p10, fill="tonexty", fillcolor="rgba(235,104,52,0.15)",
                             line=dict(width=0), name="P10–P90"))
    fig.add_trace(go.Scatter(x=m.mes, y=m.brent_base, line=dict(color=LARANJA, width=2.5), name="Cenário base"))
    fig.update_layout(title="Brent (US$/bbl)", height=330, margin=dict(t=50))
    st.plotly_chart(fig, width="stretch")
    st.markdown(f"""
- **Preço por campo**: Brent × {resumo['k_preco_brent']:.3f} (relação entre o preço de referência da ANP e o Brent)
  × fator do campo (prêmio ou desconto do campo nos últimos 12 meses publicados, até {resumo['ultimo_preco_anp']}).
- **Câmbio**: último PTAX, com variações sorteadas junto com as do petróleo (preserva a correlação).
- **Alíquotas**: 10% concessão e cessão onerosa; 15% partilha (_ECO, ANC_ e Mero). Arquivo `config/aliquotas_campos.csv`.
- **Participação especial**: taxa efetiva de cada campo nos últimos 4 trimestres publicados × receita prevista.
- **Operadoras**: `config/operadores.csv` (a conferir).
- **Limitações**: o modelo não sabe de projetos futuros (novos FPSOs ainda não instalados); a incerteza de produção
  é sorteada de forma independente entre unidades.
""")

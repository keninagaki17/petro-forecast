"""Royalties distribuídos a municípios e estados (ANP) e a ligação com a previsão por campo."""
from pathlib import Path
import numpy as np
import pandas as pd
from . import precos as pr


def _carregar(pasta: Path, padrao: str, chave: list[str]) -> pd.DataFrame:
    partes = []
    for f in sorted(pasta.glob(padrao)):
        d = pr._ler(f)
        if "competencia" not in d.columns:
            continue
        cols = [c for c in d.columns if c.startswith("royalties")]
        x = pd.DataFrame({"competencia": pr._mes_excel(d["competencia"]), "caixa": pr._mes_excel(d["caixa"])})
        for c in chave:
            x[c] = d[c].astype(str).str.strip().str.lower()
        if "municipio" in chave:
            # 2024 em diante a ANP grava "marica-rj"; antes, "marica": fica o nome sem a UF e sem acento
            x["municipio"] = (x["municipio"].str.replace(r"-[a-z]{2}$", "", regex=True)
                              .str.normalize("NFKD").str.encode("ascii", "ignore").str.decode("ascii").str.strip())
        x["minimos"] = pr._num(d[cols[0]]) if cols else 0.0
        x["excedentes"] = pr._num(d[cols[1]]).fillna(0) if len(cols) > 1 else 0.0
        partes.append(x)
    r = pd.concat(partes).dropna(subset=["competencia"])
    r["royalties"] = r.minimos.fillna(0) + r.excedentes.fillna(0)
    # um mesmo mês pode aparecer em dois arquivos anuais: fica uma linha por beneficiário e competência
    return r.groupby(["competencia"] + chave, as_index=False).agg(caixa=("caixa", "max"), minimos=("minimos", "max"),
                                                                excedentes=("excedentes", "max"), royalties=("royalties", "max"))


def municipios(pg: Path) -> pd.DataFrame:
    return _carregar(pg / "royalties-municipios", "*.csv", ["municipio", "estado"])


def estados(pg: Path) -> pd.DataFrame:
    """Arquivo largo (uma coluna por estado): vira uma linha por estado e competência."""
    partes = []
    for f in sorted((pg / "royalties-estados").glob("*.csv")):
        d = pr._ler(f)
        if "competencia" not in d.columns:
            continue
        ufs = [c for c in d.columns if c not in ("competencia", "caixa") and not c.startswith("unnamed") and c.strip()]
        x = d[["competencia", "caixa"] + ufs].melt(["competencia", "caixa"], var_name="estado", value_name="royalties")
        x["competencia"] = pr._mes_excel(x["competencia"]); x["caixa"] = pr._mes_excel(x["caixa"])
        x["royalties"] = pr._num(x["royalties"])
        partes.append(x.dropna(subset=["competencia"]))
    r = pd.concat(partes)
    return r.groupby(["competencia", "estado"], as_index=False).agg(caixa=("caixa", "max"), royalties=("royalties", "max"))


# --------------------------------------------------------------------------
# Ligação campo → beneficiário
# --------------------------------------------------------------------------
# A lei reparte os royalties de cada campo por linhas geográficas do IBGE e pelas instalações de embarque.
# Em vez de reproduzir a regra, a fatia de cada beneficiário em cada grupo de campos é estimada pelo
# histórico (mínimos quadrados não negativos), com os últimos 24 meses: as fatias mudam devagar, conforme
# novos poços entram em outras áreas, e uma janela curta acompanha essa mudança (testado em 3 anos).
JANELA = 24
LIMITE_GRUPO = 50e6          # unidade com royalties médios acima de R$ 50 mi/mês entra sozinha na regressão

# Lei 12.734/2012 (suspensa por liminar do STF desde 2013), regime de concessão no mar, percentuais finais:
# municípios confrontantes 4% (hoje ~26,25% somando a parcela de 5% e a excedente) e estados confrontantes
# 20% (hoje ~26,25%). Fonte: MPRJ, Relatório Técnico Distribuição das Rendas Petrolíferas (2020).
FATOR_LEI_12734 = {"municipio": 4 / 26.25, "estado": 20 / 26.25}

NOMES = {"marica": "Maricá", "saquarema": "Saquarema", "macae": "Macaé", "araruama": "Araruama", "niteroi": "Niterói",
         "arraial do cabo": "Arraial do Cabo", "campos dos goytacazes": "Campos dos Goytacazes", "cabo frio": "Cabo Frio",
         "sao sebastiao": "São Sebastião", "rio de janeiro": "Rio de Janeiro", "sao joao da barra": "São João da Barra",
         "angra dos reis": "Angra dos Reis", "armacao dos buzios": "Armação dos Búzios", "ilhabela": "Ilhabela",
         "rio das ostras": "Rio das Ostras", "casimiro de abreu": "Casimiro de Abreu", "mage": "Magé",
         "iguaba grande": "Iguaba Grande", "parati": "Paraty", "quissama": "Quissamã", "guapimirim": "Guapimirim",
         "itaborai": "Itaboraí", "cachoeiras de macacu": "Cachoeiras de Macacu", "duque de caxias": "Duque de Caxias",
         "mangaratiba": "Mangaratiba", "carapebus": "Carapebus", "itaguai": "Itaguaí", "silva jardim": "Silva Jardim",
         "presidente kennedy": "Presidente Kennedy", "marataizes": "Marataízes", "guararema": "Guararema",
         "itapemirim": "Itapemirim", "caraguatatuba": "Caraguatatuba", "linhares": "Linhares", "riachuelo": "Riachuelo",
         "sao francisco de itabapoana": "São Francisco de Itabapoana", "rio claro": "Rio Claro", "cubatao": "Cubatão",
         "coari": "Coari", "volta redonda": "Volta Redonda", "bertioga": "Bertioga", "vitoria": "Vitória",
         "anchieta": "Anchieta", "aracruz": "Aracruz", "serra": "Serra", "vila velha": "Vila Velha",
         "santos": "Santos", "ubatuba": "Ubatuba", "guaruja": "Guarujá", "praia grande": "Praia Grande", "sao goncalo": "São Gonçalo"}
ESTADOS = {"rio de janeiro": "RJ", "sao paulo": "SP", "espirito santo": "ES"}
NOME_UF = {"RJ": "Estado do Rio de Janeiro", "SP": "Estado de São Paulo", "ES": "Estado do Espírito Santo"}


def nome(municipio: str, uf: str) -> str:
    return f"{NOMES.get(municipio, municipio.title())} ({uf.upper()})"


def grupos(unidades_mes: pd.DataFrame, campo_uf: dict, campo_da_unidade: dict, corte: pd.Timestamp) -> dict:
    """Unidades grandes ficam sozinhas; o resto é somado por UF de confrontação."""
    rec = unidades_mes.loc[corte - pd.DateOffset(months=12):corte].mean()
    uf = lambda u: campo_uf.get(str(campo_da_unidade.get(u, "")).upper(), "RJ")
    return {u: (u if rec.get(u, 0) >= LIMITE_GRUPO else f"Demais {uf(u)}") for u in unidades_mes.columns}


def fatias(Y: pd.DataFrame, X: pd.DataFrame, corte: pd.Timestamp, janela: int = JANELA) -> pd.DataFrame:
    """Fatia de cada beneficiário (coluna de Y) em cada grupo (coluna de X), com os meses antes de `corte`."""
    from scipy.optimize import nnls
    w = (X.index < corte) & (X.index >= corte - pd.DateOffset(months=janela))
    out = {}
    for c in Y.columns:
        s, _ = nnls(X[w].values / 1e6, Y.loc[X.index[w], c].values / 1e6)
        out[c] = s
    return pd.DataFrame(out, index=X.columns).T


def montar(pg: Path, hist: pd.DataFrame, campo_uf: dict, prev_rr: pd.DataFrame, brasil: pd.DataFrame,
           prev_real: pd.DataFrame, n_mun: int = 40) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Série mensal por beneficiário (realizado ANP, estimado, previsto) e resumo com o teste fora da amostra.

    hist: royalties modelados por campo (unidade, campo_n, mes, royalties), já calibrados.
    prev_rr: previsão por unidade (unidade, mes, royalties_p50). brasil: faixa total (mes, royalties_p10/p50/p90).
    prev_real: previsto × realizado de produção por unidade (unidade, mes, h, previsto, real)."""
    mun, est = municipios(pg), estados(pg)
    ult = min(mun.competencia.max(), est.competencia.max())
    corte = ult + pd.DateOffset(months=1)
    R = hist.pivot_table(index="mes", columns="unidade", values="royalties", aggfunc="sum").fillna(0.0)
    R = R.loc[:, R.sum() > 0]
    campo_da_unidade = hist.groupby("unidade").campo_n.first().to_dict()
    gmap = grupos(R.loc[:ult], campo_uf, campo_da_unidade, corte)
    uf_de = lambda u: campo_uf.get(str(campo_da_unidade.get(u, "")).upper(), "RJ")
    gm = lambda u: gmap.get(u, f"Demais {uf_de(u)}")
    X = R.T.groupby(gm).sum().T

    # beneficiários: os maiores municípios dos últimos 12 meses e os três estados produtores
    rec12 = mun[mun.competencia > ult - pd.DateOffset(months=12)].groupby(["municipio", "estado"]).royalties.sum()
    # só municípios dos estados com produção no mar (RJ, SP, ES): nos demais, a maior parte vem de campos em terra,
    # que este modelo não prevê
    rec12 = rec12[rec12.index.get_level_values("estado").isin(["rj", "sp", "es"])]
    top = rec12.sort_values(ascending=False).head(n_mun).index
    Y = {}
    for mu, uf in top:
        s = mun[(mun.municipio == mu) & (mun.estado == uf)].groupby("competencia").royalties.sum()
        Y[(nome(mu, uf), "Município", uf.upper())] = s
    for e_nome, uf in ESTADOS.items():
        s = est[est.estado == e_nome].groupby("competencia").royalties.sum()
        Y[(NOME_UF[uf], "Estado", uf)] = s
    Y = pd.DataFrame(Y).reindex(X.index).fillna(0.0).loc[:ult]
    S = fatias(Y, X.loc[:ult], corte)

    # previsto 6 meses antes: fatias estimadas até a origem e volume previsto ao preço realizado de cada unidade
    p6 = prev_real[prev_real.h == 6].merge(R.stack().rename("roy").reset_index(), on=["unidade", "mes"], how="left")
    p6 = p6[(p6.real > 0) & p6.roy.notna()]
    p6["roy_prev"] = p6.previsto * p6.roy / p6.real
    Xp = p6.assign(g=p6.unidade.map(gm)).pivot_table(index="mes", columns="g", values="roy_prev", aggfunc="sum").reindex(columns=X.columns).fillna(0.0)
    prev6 = {}
    for t in [m for m in Xp.index if ult - pd.DateOffset(months=23) <= m <= ult]:
        St = fatias(Y, X.loc[:ult], t - pd.DateOffset(months=5))      # dado até a origem (t − 6)
        prev6[t] = St.values @ Xp.loc[t].values
    prev6 = pd.DataFrame(prev6, index=S.index).T

    # teste fora da amostra (só a fatia): estima até 12 meses antes do último dado e compara os 12 meses seguintes
    c12 = corte - pd.DateOffset(months=12)
    S12 = fatias(Y, X.loc[:ult], c12)
    jan = (X.index >= c12) & (X.index <= ult)
    teste = pd.DataFrame({"real": Y.loc[X.index[jan]].sum(), "prev": pd.Series(S12.values @ X.loc[jan].sum().values, index=S.index)})
    teste["erro_teste"] = (teste.prev / teste.real - 1) * 100

    # futuro: meses com produção publicada e royalties estimados; depois, a previsão do modelo
    Xe = X.loc[X.index > ult]
    fut = prev_rr.assign(g=prev_rr.unidade.map(gm)).pivot_table(index="mes", columns="g", values="royalties_p50", aggfunc="sum").reindex(columns=X.columns).fillna(0.0)
    fut = fut.loc[fut.index > Xe.index.max()]
    b = brasil.set_index("mes")
    lo = (b.royalties_p10 / b.royalties_p50).reindex(fut.index); hi = (b.royalties_p90 / b.royalties_p50).reindex(fut.index)

    linhas = []
    for i, (ent, tipo, uf) in enumerate(S.index):
        fat = FATOR_LEI_12734["municipio" if tipo == "Município" else "estado"]
        base = dict(entidade=ent, tipo=tipo, uf=uf)
        for t in Y.index[Y.index > ult - pd.DateOffset(months=35)]:
            linhas.append(dict(base, competencia=t, origem="realizado", valor=Y.loc[t, (ent, tipo, uf)],
                               previsto6=prev6.loc[t].iloc[i] if t in prev6.index else np.nan))
        for t in Xe.index:
            linhas.append(dict(base, competencia=t, origem="estimado", valor=float(S.iloc[i].values @ Xe.loc[t].values)))
        for t in fut.index:
            v = float(S.iloc[i].values @ fut.loc[t].values)
            linhas.append(dict(base, competencia=t, origem="previsto", valor=v, p10=v * lo[t], p90=v * hi[t], lei=v * fat))
    serie = pd.DataFrame(linhas)
    serie["recebimento"] = serie.competencia + pd.DateOffset(months=2)        # a ANP repassa dois meses depois

    res = []
    for i, (ent, tipo, uf) in enumerate(S.index):
        s = serie[serie.entidade == ent]
        r12 = s[s.origem == "realizado"].tail(12).valor.sum()
        f = s[s.origem == "previsto"].head(12)
        p6r = s[(s.origem == "realizado") & s.previsto6.notna()].tail(12)
        res.append(dict(entidade=ent, tipo=tipo, uf=uf, ult12=r12, prox12=f.valor.sum(), lei12=f.lei.sum(),
                        var_pct=(f.valor.sum() / r12 - 1) * 100 if r12 else np.nan,
                        erro6=(p6r.previsto6 - p6r.valor).abs().sum() / p6r.valor.sum() * 100 if len(p6r) else np.nan,
                        erro_teste=teste.loc[(ent, tipo, uf), "erro_teste"]))
    return serie, pd.DataFrame(res)

"""
coleta_dados.py — Etapa 1 do MVP: previsão de produção e royalties (óleo e gás, Brasil)

O que faz:
  1. Baixa os dados públicos da ANP (produção por poço no mar, royalties,
     participação especial, preços de referência).
  2. Baixa câmbio (PTAX mensal, Banco Central) e Brent (FRED).
  3. Gera um perfil de cada arquivo (colunas, tipos, linhas, amostra) em
     dados_brutos/perfil_dados.txt, que serve para desenhar o modelo.

Como rodar (Windows, Mac ou Linux, Python 3.10+):
    pip install requests pandas openpyxl
    python coleta_dados.py                 # produção do mar a partir de 2010
    python coleta_dados.py --desde 2005    # puxa mais histórico
    python coleta_dados.py --sem-producao  # pula os arquivos grandes de produção

Os arquivos já baixados são reaproveitados (só baixa o que falta).
No fim, envie no chat:
  - dados_brutos/perfil_dados.txt
  - dados_brutos/manifesto.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests

BASE = Path(__file__).resolve().parent / "dados_brutos"

HEADERS = {
    # O gov.br às vezes recusa clientes sem User-Agent de navegador.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

ANP = "https://www.gov.br/anp/pt-br"

# Páginas da ANP onde os links são lidos. Os nomes dos arquivos mudam de ano
# para ano (hífen/underscore, singular/plural), então o script lê os links da
# página em vez de montar as URLs na mão.
FONTES_ANP = [
    {
        "nome": "producao_mar",
        "pagina": f"{ANP}/centrais-de-conteudo/dados-abertos/fase-de-desenvolvimento-e-producao",
        "padrao": r"/pm/[^\"'\s]+\.csv",
        "filtrar_ano": True,  # arquivos grandes: respeita --desde
    },
    {
        "nome": "participacoes_governamentais",
        "pagina": f"{ANP}/centrais-de-conteudo/dados-abertos/participacoes-governamentais",
        "padrao": r"/arquivos/pg/[^\"'\s]+\.(?:csv|docx)",
        "filtrar_ano": False,
    },
    {
        "nome": "concessionarios",
        "pagina": f"{ANP}/centrais-de-conteudo/dados-abertos/relacao-de-concessionarios",
        "padrao": r"^(?![^\"']*pais)[^\"']*concession[^\"']*\.csv",
        "filtrar_ano": False,
    },
    {
        "nome": "preco_referencia_petroleo_mensal",
        "pagina": f"{ANP}/assuntos/royalties-e-outras-participacoes/preco-de-referencia-do-petroleo",
        "padrao": r"/arq-royalties/prp/[^\"'\s]+\.xlsx",
        "filtrar_ano": False,
    },
]

# Série SGS 3698: dólar (venda), média mensal (PTAX).
URL_PTAX = (
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.3698/dados"
    "?formato=json&dataInicial=01/01/2000"
)
# Brent diário (EIA via FRED), em US$/barril.
URL_BRENT = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU"


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def get(url: str, tentativas: int = 4, timeout: int = 120) -> requests.Response:
    ultimo_erro = None
    for i in range(1, tentativas + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r
            ultimo_erro = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            ultimo_erro = str(e)
        time.sleep(2 * i)
    raise RuntimeError(f"Falha ao baixar {url}: {ultimo_erro}")


def anos_no_nome(nome: str) -> list[int]:
    return [int(a) for a in re.findall(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", nome)]


def baixar(url: str, destino: Path, manifesto: list[dict]) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and destino.stat().st_size > 0:
        status = "ja_existia"
    else:
        try:
            r = get(url)
            destino.write_bytes(r.content)
            status = "baixado"
        except RuntimeError as e:
            status = f"erro: {e}"
    tamanho = destino.stat().st_size if destino.exists() else 0
    manifesto.append(
        {
            "url": url,
            "arquivo": str(destino.relative_to(BASE)),
            "tamanho_kb": round(tamanho / 1024, 1),
            "status": status,
            "data": datetime.now().isoformat(timespec="seconds"),
        }
    )
    print(f"  [{status[:10]:<10}] {destino.name} ({tamanho / 1024:,.0f} KB)")


# --------------------------------------------------------------------------
# Coleta
# --------------------------------------------------------------------------
def coletar_anp(desde: int, sem_producao: bool, manifesto: list[dict]) -> None:
    for fonte in FONTES_ANP:
        if sem_producao and fonte["nome"] == "producao_mar":
            continue
        print(f"\n== {fonte['nome']} ==")
        try:
            html = get(fonte["pagina"]).text
        except RuntimeError as e:
            print(f"  ERRO ao ler a página: {e}")
            manifesto.append({"url": fonte["pagina"], "arquivo": "", "tamanho_kb": 0,
                              "status": f"erro_pagina: {e}", "data": ""})
            continue

        hrefs = re.findall(r"""href\s*=\s*["']([^"']+)["']""", html, flags=re.I)
        links = sorted({urljoin(fonte["pagina"], h.strip()) for h in hrefs
                        if re.search(fonte["padrao"], h)})
        if fonte["filtrar_ano"]:
            links = [u for u in links if anos_no_nome(u.rsplit("/", 1)[-1])
                     and max(anos_no_nome(u.rsplit("/", 1)[-1])) >= desde]
        print(f"  {len(links)} arquivo(s) encontrado(s)")

        for url in links:
            # Mantém a subpasta de origem para evitar colisão de nomes
            partes = url.split("/")
            sub = partes[-2] if len(partes) > 1 else ""
            destino = BASE / "anp" / fonte["nome"] / sub / partes[-1]
            baixar(url, destino, manifesto)


def coletar_mercado(manifesto: list[dict]) -> None:
    print("\n== mercado (PTAX e Brent) ==")
    destino = BASE / "mercado"
    destino.mkdir(parents=True, exist_ok=True)

    # PTAX mensal
    try:
        dados = get(URL_PTAX).json()
        df = pd.DataFrame(dados)
        df["data"] = pd.to_datetime(df["data"], dayfirst=True)
        df["ptax_venda_media"] = pd.to_numeric(df["valor"])
        df[["data", "ptax_venda_media"]].to_csv(destino / "ptax_mensal.csv", index=False)
        status = f"baixado ({len(df)} meses)"
    except Exception as e:  # noqa: BLE001
        status = f"erro: {e}"
    print(f"  PTAX: {status}")
    manifesto.append({"url": URL_PTAX, "arquivo": "mercado/ptax_mensal.csv",
                      "tamanho_kb": 0, "status": status, "data": datetime.now().isoformat()})

    # Brent: diário -> média mensal
    try:
        r = get(URL_BRENT)
        (destino / "brent_diario.csv").write_bytes(r.content)
        df = pd.read_csv(destino / "brent_diario.csv")
        df.columns = ["data", "brent_usd"]
        df["data"] = pd.to_datetime(df["data"])
        df["brent_usd"] = pd.to_numeric(df["brent_usd"], errors="coerce")
        mensal = (df.dropna().set_index("data")["brent_usd"]
                  .resample("MS").mean().round(2).reset_index())
        mensal.to_csv(destino / "brent_mensal.csv", index=False)
        status = f"baixado ({len(mensal)} meses)"
    except Exception as e:  # noqa: BLE001
        status = f"erro: {e}"
    print(f"  Brent: {status}")
    manifesto.append({"url": URL_BRENT, "arquivo": "mercado/brent_mensal.csv",
                      "tamanho_kb": 0, "status": status, "data": datetime.now().isoformat()})


# --------------------------------------------------------------------------
# Perfil das bases (o que eu preciso para desenhar o modelo)
# --------------------------------------------------------------------------
def ler_tabela(caminho: Path) -> pd.DataFrame:
    if caminho.suffix.lower() == ".xlsx":
        return pd.read_excel(caminho, nrows=2000)
    ultimo = None
    for enc in ("utf-8-sig", "latin-1"):
        for sep in (";", ","):
            try:
                df = pd.read_csv(caminho, sep=sep, encoding=enc, low_memory=False)
                if df.shape[1] > 1:
                    return df
            except Exception as e:  # noqa: BLE001
                ultimo = e
    raise ValueError(f"não consegui ler: {ultimo}")


def gerar_perfil() -> None:
    saida = BASE / "perfil_dados.txt"
    arquivos = sorted(p for p in BASE.rglob("*") if p.suffix.lower() in (".csv", ".xlsx")
                      and p.name not in ("manifesto.csv", "brent_diario.csv"))

    # Para arquivos repetidos por ano, perfila o mais recente e o mais antigo
    # de cada pasta; nos demais registra só o tamanho, para o txt não explodir.
    por_pasta: dict[Path, list[Path]] = {}
    for a in arquivos:
        por_pasta.setdefault(a.parent, []).append(a)

    with saida.open("w", encoding="utf-8") as f:
        f.write(f"Perfil gerado em {datetime.now():%Y-%m-%d %H:%M}\n")
        for pasta, lista in por_pasta.items():
            f.write("\n" + "=" * 90 + f"\nPASTA: {pasta.relative_to(BASE)} ({len(lista)} arquivos)\n")
            detalhar = {lista[0], lista[-1]}
            for a in lista:
                if a not in detalhar:
                    f.write(f"\n- {a.name}: {a.stat().st_size / 1024:,.0f} KB (sem detalhe)\n")
                    continue
                f.write(f"\n--- {a.name} ({a.stat().st_size / 1024:,.0f} KB)\n")
                try:
                    df = ler_tabela(a)
                    f.write(f"linhas: {len(df):,} | colunas: {df.shape[1]}\n")
                    for c in df.columns:
                        exemplo = df[c].dropna().astype(str).head(3).tolist()
                        f.write(f"  {str(c)[:60]:<60} {str(df[c].dtype):<10} "
                                f"nulos={df[c].isna().mean():.0%} ex={exemplo}\n")
                    f.write("amostra:\n")
                    f.write(df.head(3).to_string(max_colwidth=25)[:3000] + "\n")
                except Exception as e:  # noqa: BLE001
                    f.write(f"  ERRO ao ler: {e}\n")
    print(f"\nPerfil salvo em: {saida}")


# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Coleta de dados do MVP de royalties")
    ap.add_argument("--desde", type=int, default=2010,
                    help="ano inicial dos arquivos de produção (padrão: 2010)")
    ap.add_argument("--sem-producao", action="store_true",
                    help="não baixa os arquivos de produção por poço")
    args = ap.parse_args()

    BASE.mkdir(exist_ok=True)
    manifesto: list[dict] = []

    coletar_anp(args.desde, args.sem_producao, manifesto)
    coletar_mercado(manifesto)

    with (BASE / "manifesto.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["url", "arquivo", "tamanho_kb", "status", "data"])
        w.writeheader()
        w.writerows(manifesto)

    gerar_perfil()

    erros = [m for m in manifesto if str(m["status"]).startswith("erro")]
    print(f"\nConcluído: {len(manifesto) - len(erros)} ok, {len(erros)} com erro.")
    if erros:
        print("Arquivos com erro (veja manifesto.csv):")
        for m in erros:
            print(f"  - {m['url']}")
    print("\nEnvie no chat: dados_brutos/perfil_dados.txt e dados_brutos/manifesto.csv")


if __name__ == "__main__":
    sys.exit(main())

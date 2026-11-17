"""
empacotar_dados.py — baixa os dados públicos (se ainda não baixou) e gera UM
arquivo pequeno, pacote_dados.zip, para enviar no chat.

    pip install -r requirements.txt
    python empacotar_dados.py

O zip contém:
    pocos_mes.csv.gz    produção por poço e mês, já padronizada (bbl/dia)
    mercado/            Brent e PTAX mensais
    anp_extra/          royalties, participação especial e preços de referência
    perfil_dados.txt    resumo das colunas de cada arquivo original
    manifesto.csv       o que foi baixado e o que falhou
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

from src import dados

RAIZ = Path(__file__).resolve().parent
BRUTOS = RAIZ / "dados_brutos"
LIMITE_MB = 25  # tamanho máximo do zip, para caber no upload do chat


def main() -> None:
    pasta_prod = BRUTOS / "anp" / "producao_mar"
    if not any(pasta_prod.rglob("*.csv")) if pasta_prod.exists() else True:
        print("Dados ainda não baixados: rodando coleta_dados.py --desde 2005\n")
        subprocess.run([sys.executable, str(RAIZ / "coleta_dados.py"), "--desde", "2005"], check=False)

    print("\nPadronizando produção por poço")
    pocos = dados.carregar_producao(pasta_prod)
    for c in ("petroleo_bpd", "gas_mil_m3d", "agua_bpd"):
        pocos[c] = pocos[c].round(3)
    pocos["mes"] = pocos["mes"].dt.strftime("%Y-%m")
    arq_pocos = BRUTOS / "pocos_mes.csv.gz"
    pocos.to_csv(arq_pocos, index=False, compression="gzip")
    print(f"  {len(pocos):,} linhas, {pocos['poco'].nunique():,} poços, {pocos['campo'].nunique()} campos, "
          f"{pocos['mes'].min()} a {pocos['mes'].max()}")

    destino = RAIZ / "pacote_dados.zip"
    usado = 0.0
    fora = []
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        def incluir(caminho: Path, nome: str, obrigatorio: bool = False) -> None:
            nonlocal usado
            mb = caminho.stat().st_size / 1e6
            # CSV/XLSX comprimem bem; estimativa conservadora do tamanho no zip
            est = mb if caminho.suffix in (".gz", ".xlsx", ".docx") else mb * 0.25
            if not obrigatorio and usado + est > LIMITE_MB:
                fora.append(nome)
                return
            z.write(caminho, nome)
            usado += est

        incluir(arq_pocos, "pocos_mes.csv.gz", obrigatorio=True)
        for nome in ("perfil_dados.txt", "manifesto.csv"):
            if (BRUTOS / nome).exists():
                incluir(BRUTOS / nome, nome, obrigatorio=True)
        for f in sorted((BRUTOS / "mercado").glob("*_mensal.csv")) if (BRUTOS / "mercado").exists() else []:
            incluir(f, f"mercado/{f.name}", obrigatorio=True)
        extras = []
        for sub in ("participacoes_governamentais", "preco_referencia_petroleo_mensal"):
            p = BRUTOS / "anp" / sub
            if p.exists():
                extras += [f for f in p.rglob("*") if f.is_file()]
        # mais recentes primeiro, para priorizá-los se faltar espaço
        for f in sorted(extras, key=lambda x: x.name, reverse=True):
            incluir(f, "anp_extra/" + str(f.relative_to(BRUTOS / "anp")).replace("\\", "/"))
        if fora:
            z.writestr("arquivos_fora_do_pacote.txt", "\n".join(fora))

    print(f"\nPronto: {destino} ({destino.stat().st_size / 1e6:.1f} MB)")
    if fora:
        print(f"  {len(fora)} arquivo(s) extra(s) ficaram de fora por tamanho (lista dentro do zip).")
    print("Envie esse arquivo no chat.")


if __name__ == "__main__":
    main()

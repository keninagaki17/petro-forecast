"""Unidades de previsão.

A ANP às vezes divide um mesmo reservatório em vários "campos" (ex.: BÚZIOS e
BÚZIOS_ECO, o excedente da cessão onerosa; ANC_ = área não contratada) ou
renomeia campos (LULA virou TUPI). Os mesmos poços aparecem nesses nomes, então
prevemos o conjunto (a "unidade") e depois repartimos pelos subcampos para
calcular royalties, que dependem do regime de cada um.
"""

GRUPOS = {
    "TUPI": ["LULA", "TUPI", "SUL DE TUPI", "SUL DE LULA", "ANC_TUPI"],
    "BÚZIOS": ["BÚZIOS", "BÚZIOS_ECO", "TAMBUATÁ"],
    "MERO": ["MERO", "ANC_MERO"],
    "ATAPU": ["ATAPU", "ATAPU_ECO", "OESTE DE ATAPU", "ANC_NORTE_ATAPU"],
    "BERBIGÃO/SURURU": ["BERBIGÃO", "SUL DE BERBIGÃO", "NORTE DE BERBIGÃO", "SURURU",
                        "PEO-1BRSA1146RJS_IARA_ENTORNO_CCO"],
    "SÉPIA": ["SÉPIA", "SÉPIA_ECO", "SÉPIA LESTE"],
    "ITAPU": ["ITAPU", "ITAPU_ECO"],
    "SAPINHOÁ": ["SAPINHOÁ", "NORDESTE DE SAPINHOÁ", "NOROESTE DE SAPINHOÁ", "NOROESTE DE SAPINHOA",
                 "SUDOESTE DE SAPINHOÁ"],
    "JUBARTE": ["JUBARTE", "ANC_JUBARTE_NORDESTE", "ANC_JUBARTE_SUDOESTE"],
    "ARGONAUTA": ["ARGONAUTA", "ANC_ARGONAUTA_ME1"],
    "TARTARUGA VERDE": ["TARTARUGA VERDE", "TARTARUGA VERDE SUDOESTE", "TARTARUGA MESTIÇA"],
    "BACALHAU": ["BACALHAU", "BACALHAU NORTE"],
    "DOM JOÃO": ["DOM JOÃO", "DOM JOÃO MAR"],
    "CAMARUPIM": ["CAMARUPIM", "CAMARUPIM NORTE"],
}
_MAPA = {c: g for g, cs in GRUPOS.items() for c in cs}


def unidade(campo: str) -> str:
    return _MAPA.get(str(campo).strip().upper(), str(campo).strip().upper())

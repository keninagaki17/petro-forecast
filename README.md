# Petróleo no mar do Brasil: previsão, previsto × realizado e royalties

Projeto pessoal de Ken Vasconcelos, feito só com dados públicos (ANP, Banco Central e EIA).

**Painel interativo:** https://keninagaki17.github.io/petro-forecast/ (abre sem login)

Todo mês, um robô (GitHub Actions) baixa os dados da ANP, roda o modelo, guarda a previsão feita e compara
as previsões anteriores com o que de fato aconteceu. O painel mostra:

- produção, receita e royalties previstos para os próximos 18 meses, por empresa e por campo, com faixa de incerteza;
- previsto × realizado com 1, 3, 6 e 12 meses de antecedência;
- royalties de 40 municípios e 3 estados, com o cenário da Lei 12.734/2012 (em julgamento no STF);
- premissas editáveis (Brent, câmbio, produção, atraso de plataformas).

Não é recomendação de investimento.


Forecast mensal de 18 meses para cada campo marítimo brasileiro, com faixa de
incerteza (P10–P90), receita bruta, royalties e participação especial estimada.
Construído só com dados públicos: ANP (produção por poço, preços de referência,
arrecadação), Banco Central (PTAX) e EIA (Brent).

## Como rodar

```bash
pip install -r requirements.txt
python coleta_dados.py --desde 2005   # baixa os dados públicos para dados_brutos/
# baixe também a "Relação de concessionários – dados (csv)" da ANP em dados_brutos/anp/concessionarios/
python rodar_modelo.py                # torneio de métodos, previsão, royalties -> saidas/
streamlit run app.py                  # abre o painel no navegador
```

## O método (escolhido num torneio)

Para cada mês desde 2010, cada método previu os 18 meses seguintes usando **apenas
dados disponíveis naquela data** (2.565 poços, 94 unidades, 2005–2026).

| Método | Erro mensal por campo | Erro anual por campo* |
|---|---|---|
| Ingênuo (repete o último mês) | 20,2% | 15,8% |
| Curva de declínio (Arps) | 21,1% | 16,5% |
| Suavização exponencial (ETS) | 21,2% | 16,4% |
| **Modelo final** | **16,0%** | **11,7%** |

\* previsão feita em dezembro para a média do ano seguinte, como num orçamento.

O modelo final:

1. **ML híbrido**: LightGBM (perda Huber) treinado com todos os campos, usando
   sinais de engenharia (Arps do campo e poço a poço, ETS), dinâmica recente,
   poços ativos e novos, % de água, razão gás/óleo e maturidade.
2. **Teto de capacidade** das plataformas ativas (`config/capacidade_fpso.csv`).
3. **Combinação com o ingênuo** nos primeiros meses (pesos escolhidos com dados até 2018).
4. **Plataformas anunciadas** (`config/projetos.csv`) somadas com uma **curva de
   rampa aprendida** de 42 plataformas que entraram em operação desde 2010
   (erro 29% contra 33% de uma rampa linear). No backtest, simula-se conhecer a
   data de entrada das plataformas, como acontece hoje com os anúncios.
5. **Faixas P10–P90 empíricas**, calibradas para cobrir ~80% dos casos.
6. **Fatores de cada previsão** (contribuições SHAP do LightGBM) para explicar o resultado.

**Correção de dados:** nos campos com acordo de coparticipação (Búzios, Sépia,
Atapu, Itapu, Mero), o arquivo por poço da ANP traz só a parcela de um dos
contratos. A parcela faltante é recriada com os percentuais oficiais
(`config/coparticipacao.csv`). Com isso, Búzios bate com o total divulgado pela
ANP (744,3 mil bbl/d em nov/2025; 875,7 mil em jan/2026) e a base cobre ~96% da
produção marítima oficial.

## Produção por empresa

A Relação de Concessionários da ANP (`dados_brutos/anp/concessionarios/`) dá a
participação de cada empresa em cada contrato; `config/campo_contrato.csv` liga
cada campo ao seu contrato. A produção de cada empresa é a soma das suas
participações (antes do excedente em óleo da União nos contratos de partilha).

**Validação:** ajustado pelo escopo da empresa (fator calibrado em 2025), o modelo
dá 2,53 milhões bbl/d para a Petrobras no 3T25 (divulgado: 2,52) e 2,86 milhões
no 3T26 (divulgado: 2,83), fora da amostra de calibração.

## Do volume ao dinheiro

- Preço por campo = Brent × relação preço ANP/Brent × prêmio/desconto do campo.
- Royalties = receita × alíquota (10% concessão/cessão onerosa; 15% partilha),
  calibrados contra a arrecadação nacional da ANP (erro médio mensal de 1,8% desde 2022).
- Participação especial = taxa efetiva recente de cada campo × receita.
- Monte Carlo de Brent e câmbio (choques históricos sorteados juntos).
- Ponte previsto × realizado: efeitos volume, preço e câmbio.
- Previsto × realizado automático: cada rodada guarda a previsão em `saidas/historico/` e compara as anteriores
  com o que a ANP publicou depois (`saidas/previsto_realizado.csv.gz`). Antes de haver previsões guardadas,
  usa o teste retroativo.
- Visão do sócio não operador: parte de cada empresa em cada campo (`saidas/pesos_unidade_empresa.csv`).
- Entrada em operação das plataformas: meses até 80% da capacidade (`saidas/rampas_plataformas.csv`).

## Premissas editáveis (pasta config/)

| Arquivo | O que define |
|---|---|
| `brent_mensal.csv` | Brent realizado recente e cenário base |
| `aliquotas_campos.csv` | exceções de alíquota de royalties |
| `capacidade_fpso.csv` | capacidade nominal de plataformas novas |
| `operadores.csv` | operadora de cada campo |
| `projetos.csv` | plataformas anunciadas (capacidade e janela de 1º óleo) |
| `coparticipacao.csv` | percentuais dos acordos de coparticipação |
| `campo_contrato.csv` | contrato da ANP de cada campo (para a participação das empresas) |
| `participacoes_aip.csv` | participações por jazida de acordos de individualização (AIP), com data de vigência |
| `metas_empresas.csv` | metas de produção divulgadas, para comparação |

Verificação em 13/11/2026 (fontes públicas): as 13 capacidades de `capacidade_fpso.csv`, as janelas
de 1º óleo de P-80, P-82 e P-83 e os contratos dos principais campos (Mero, Berbigão/Sururu, Sapinhoá,
Lapa, Bacalhau, Atlanta, Tubarão Martelo, Wahoo). Correções: Wahoo passou para o BM-C-30; Bacalhau Norte
para Norte de Carcará; Sul/Norte de Berbigão para a Cessão Onerosa; AIPs de Berbigão e Sururu (mai/2026)
incluídos. Os demais campos de `campo_contrato.csv` seguem marcados "conferir".

## Royalties por estado e município

`src/royalties_municipios.py` liga a previsão por campo ao que cada beneficiário recebe. A divisão legal
(linhas do IBGE, instalações de embarque) não é reproduzida: a fatia de cada estado e município nos
royalties de cada grupo de campos é estimada com os últimos 24 meses publicados pela ANP (mínimos quadrados
não negativos). A janela de 24 meses venceu as de 12, 18, 30 e 84 meses e a regra "mesma fatia do total" em
três anos de teste (erro de 6% a 8% no total de 12 meses, ponderado pelos 40 maiores municípios).

Saídas: `royalties_beneficiarios.csv` (realizado, estimado com a produção já publicada, previsto com faixa,
previsão feita 6 meses antes e o cenário da Lei 12.734/2012) e `royalties_beneficiarios_resumo.csv`.

O cenário da Lei 12.734 aplica os percentuais finais da lei para contratos de concessão no mar
(municípios confrontantes de ~26,25% para 4%; estados de ~26,25% para 20%) à mesma previsão. É uma ordem de
grandeza: não inclui o que volta aos municípios pelo fundo especial (rateio do FPM).

Conferência com valores divulgados (meses de 2026 ainda fora da base): Maricá jan–jul/2026 −11%; repasse
de maio: Estado do RJ −4%, Saquarema −5%, Macaé −3%, Araruama +2%, Estado de SP −47% (Bacalhau, campo novo
sem histórico).

## Atualização automática

`.github/workflows/atualizar.yml` roda todo mês no GitHub Actions: coleta, modelo, arquivo da previsão,
comparação previsto × realizado e `painel_dados.py` (gera `saidas/painel/*.json`). Se os sites do
governo bloquearem o robô, rode `coleta_dados.py` no seu PC e envie a pasta
`dados_brutos/` para o repositório.

### Site público (GitHub Pages)

A pasta `site/` tem o painel em HTML, CSS e JavaScript (d3). `.github/workflows/site.yml` monta o site com
os arquivos de `saidas/painel/json/` e publica no GitHub Pages. Ele roda no fim da atualização mensal e
sempre que `site/` muda. `site/js/runtime.js` carrega os dados e redesenha os gráficos quando o usuário
mexe nos filtros.

Para testar no computador: copie `saidas/painel/json/*.json` para `site/data/` e rode
`python -m http.server` dentro de `site/`.

### Painel no Claude

Há também uma cópia do painel no Claude. Ela lê arquivos anexados, não o GitHub. Uma tarefa agendada no Claude, no dia 21 de
cada mês (depois do robô do dia 20), copia os arquivos de `saidas/painel/json/` do repositório para o painel.
A lista de arquivos e datasets está em `config/painel_datasets.json`. Para isso o repositório precisa ser
público (ou o GitHub estar conectado ao Claude).

## Limitações

- Plataformas novas dependem do cronograma anunciado; atrasos fora da janela configurada não são captados.
- A incerteza de produção usa choque comum entre campos (correlação medida no backtest).
- Participação especial é estimativa (depende de custos não públicos) e não entra na aba de royalties por município.
- Campos novos sem histórico de divisão (ex.: Bacalhau) têm a fatia de cada beneficiário aproximada pela dos campos do mesmo estado.
- Royalties por campo são calibrados contra o total nacional, que inclui a produção em terra.

Projeto educacional; não é recomendação de investimento.

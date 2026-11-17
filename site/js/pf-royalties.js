// Aba Royalties: quanto cada município e estado recebe, o que foi previsto e o que vem, com o cenário da Lei 12.734
(() => {
  const f0 = PF.fmt.f0, f1 = PF.fmt.f1;
  PF.st.sort.roy = {k: 'prox12', d: -1};
  const RP = () => {
    const p = dash.params() || {};
    const s = dash.data('royalties_resumo'), ok = s.status === 'ok' && s.data.some((r) => r.entidade === p.ent);
    return {ent: ok ? p.ent : 'Maricá (RJ)', lei: Number(p.lei) === 1};
  };
  const mi = (v) => v == null ? '—' : 'R$ ' + (v >= 1000 ? PF.fmt.f2(v / 1000) + ' bi' : f0(v) + ' mi');
  const confClasse = (c) => c === 'média' ? 'media' : c;

  dash.draw('rkv', (el) => { el.setAttribute('data-where', 'entidade=' + PF.enc(RP().ent)); PF.fillValue(el); });
  dash.draw('entNome', (el) => { el.textContent = RP().ent; });
  dash.draw('selEnt', (sel) => {
    const s = dash.data('royalties_resumo');
    const R = s.status === 'ok' ? s.data : [];
    const grupo = (tipo, rot) => {
      const g = document.createElement('optgroup'); g.label = rot;
      R.filter((r) => r.tipo === tipo).sort((a, b) => b.prox12 - a.prox12).forEach((r) => g.append(new Option(r.entidade, r.entidade)));
      return g;
    };
    sel.replaceChildren(grupo('Estado', 'Estados'), grupo('Município', 'Municípios'));
    sel.value = RP().ent;
    sel.onchange = () => dash.setParams({ent: sel.value});
  });

  // Frase de abertura, escrita a partir dos números da entidade escolhida
  dash.draw('txtRoy', (el) => {
    const s = dash.data('royalties_resumo'), b = dash.data('royalties_benef');
    if (s.status !== 'ok' || b.status !== 'ok') { el.textContent = ''; return; }
    const r = s.data.find((x) => x.entidade === RP().ent);
    if (!r) { el.textContent = ''; return; }
    const ini = d3.min(b.data.filter((x) => x.entidade === r.entidade && x.origem === 'previsto'), (x) => x.mes);
    const v = r.var_pct;
    el.textContent = `${r.entidade} recebeu ${mi(r.ult12)} de royalties nos 12 meses até ${PF.mLong(PF.parse(r.ult_mes))}, segundo a ANP. ` +
      `Para os 12 meses a partir de ${PF.mLong(PF.parse(ini))}, o modelo prevê ${mi(r.prox12)} (${v >= 0 ? '+' : '−'}${f0(Math.abs(v))}%). ` +
      `Se a Lei 12.734 passar a valer, esse valor previsto cai para ${mi(r.lei12)}.`;
  });

  dash.draw('confEnt', (el) => {
    const s = dash.data('royalties_resumo');
    const r = s.status === 'ok' ? s.data.find((x) => x.entidade === RP().ent) : null;
    el.className = 'pf-conf ' + (r ? confClasse(r.confianca) : '');
    el.textContent = r ? 'confiança ' + r.confianca : '';
  });

  dash.draw('chRoyEnt', (el) => {
    if (!PF.ok(el, ['royalties_benef'])) return;
    const c = RP(), c0 = PF.col(0), c1 = PF.col(1), c2 = PF.col(2), mu = 'var(--cds-chart-muted)';
    const L = PF.rows('royalties_benef').filter((r) => r.entidade === c.ent);
    const ultR = L.filter((r) => r.origem === 'realizado').slice(-1)[0];
    const ultE = L.filter((r) => r.origem === 'estimado').slice(-1)[0];
    const R = L.map((r) => {
      const o = {mes: r.mes, _x: r._x, origem: r.origem};
      if (r.origem === 'realizado') { o.real = r.valor; o.prev6 = r.previsto6; }
      if (r.origem === 'estimado') o.est = r.valor;
      if (r.origem === 'previsto') { o.p50 = r.valor; o.p10 = r.p10; o.p90 = r.p90; if (c.lei) o.lei = r.lei; }
      if (r === ultR) o.est = r.valor;                       // emenda as linhas
      if (r === ultE) { o.p50 = r.valor; o.p10 = r.valor; o.p90 = r.valor; if (c.lei) o.lei = r.valor; }
      return o;
    });
    const series = [{k: 'prev6', color: c1, w: 1.5, dash: '2 3'}, {k: 'real', color: c0, w: 2.2}, {k: 'est', color: mu, w: 2, dash: '4 3'}, {k: 'p50', color: c1, w: 2.2, dash: '6 4'}];
    if (c.lei) series.push({k: 'lei', color: c2, w: 2.2});
    PF.tchart(el, {
      rows: R, yfmt: f0, zero: true, vline: ultE ? ultE._x : null, endLabel: c.lei ? 'lei' : 'p50', band: {lo: 'p10', hi: 'p90', color: c1},
      aria: 'Royalties recebidos por ' + c.ent + ' por mês, em milhões de reais: realizado pela ANP, estimado e previsto para os próximos 18 meses',
      series,
      tip: (r) => r.origem === 'realizado'
        ? [['Recebido (ANP)', mi(r.real), c0], ['Previsto 6 meses antes', r.prev6 == null ? null : mi(r.prev6) + ' (' + PF.fmt.pct((r.prev6 / r.real - 1) * 100) + ')', c1]]
        : r.origem === 'estimado'
          ? [['Estimado', mi(r.est), mu], ['Como', 'produção publicada × preço', null]]
          : [['Previsão', mi(r.p50), c1], ['Faixa P10–P90', f0(r.p10) + '–' + f0(r.p90) + ' mi', null], ['Se a Lei 12.734 valer', r.lei == null ? null : mi(r.lei), c2]]
    });
  });

  dash.draw('tbRoy', (tb) => PF.tabela(tb, 'royalties_resumo', 'roy',
    [['entidade', String], ['ult12', f0], ['prox12', f0], ['var_pct', PF.fmt.pct], ['lei12', f0], ['erro6', (v) => f0(v) + '%'], ['confianca', String]],
    'entidade', RP().ent, (e) => { dash.setParams({ent: e}); const c = document.getElementById('card-royalties'); if (c) c.scrollIntoView({behavior: 'smooth', block: 'start'}); }));

  document.querySelectorAll('#lei-seg button[data-lei]').forEach((b) => b.addEventListener('click', () => dash.setParams({lei: Number(b.dataset.lei)})));
  dash.onData(() => { const c = RP(); document.querySelectorAll('#lei-seg button[data-lei]').forEach((b) => b.classList.toggle('on', Number(b.dataset.lei) === (c.lei ? 1 : 0))); });

  // Data do último dado de produção, para o cabeçalho
  dash.draw('ateMes', (el) => {
    const s = dash.data('historico');
    if (s.status !== 'ok' || !s.data.length) { el.textContent = '—'; return; }
    el.textContent = PF.mLong(PF.parse(d3.max(s.data, (r) => r.mes)));
  });
})();

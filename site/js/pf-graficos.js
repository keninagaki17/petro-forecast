// Visão geral
dash.draw('chBrasil', (el) => {
  if (!PF.ok(el, ['brasil_mensal'])) return;
  let R = PF.rows('brasil_mensal');
  const lastReal = d3.max(R.filter((r) => r.realizado != null), (r) => r._x);
  if (PF.st.range === '3a') { const c = d3.utcMonth.offset(lastReal, -36); R = R.filter((r) => r._x >= c); }
  const c0 = PF.col(0), c1 = PF.col(1), f = PF.fmt.f0;
  PF.tchart(el, {
    rows: R, vline: lastReal, endLabel: 'p50', yfmt: f,
    aria: 'Produção mensal de petróleo das unidades modeladas, realizada desde 2018 e prevista até março de 2028, com faixa P10–P90',
    series: [{k: 'realizado', color: c0, w: 2}, {k: 'p50', color: c1, w: 2.2, dash: '5 4'}],
    band: {lo: 'p10', hi: 'p90', color: c1},
    tip: (r) => [['Realizado', r.realizado == null ? null : f(r.realizado), c0], ['Previsão P50', r.realizado != null || r.p50 == null ? null : f(r.p50), c1],
      ['Faixa P10–P90', r.realizado != null || r.p10 == null ? null : f(r.p10) + '–' + f(r.p90), null]]
  });
});

dash.draw('chProj', (el) => {
  if (!PF.ok(el, ['projetos_mensal'])) return;
  el.replaceChildren();
  const R = PF.rows('projetos_mensal');
  const inst = [...new Set(R.map((r) => r.instalacao))];
  const meses = [...new Set(R.map((r) => r.mes))].sort();
  const data = meses.map((mm) => { const o = {mes: mm, _x: PF.parse(mm)}; inst.forEach((i) => { const r = R.find((z) => z.mes === mm && z.instalacao === i); o[i] = r ? r.p50 : 0; }); o.total = d3.sum(inst, (i) => o[i]); return o; });
  const W = Math.max(240, el.clientWidth), H = Math.round(Math.max(260, Math.min(340, W * 0.75)));
  const svg = PF.svgFor(el, W, H, 'Produção prevista das plataformas P-80, P-82 e P-83 por mês, empilhada');
  const ys = d3.scaleLinear().domain([0, d3.max(data, (d) => d.total) * 1.12 || 1]).nice();
  const yt = ys.ticks(4);
  const m = {t: 16, r: 6, b: 26, l: Math.ceil(PF.measure(svg, yt.map(PF.fmt.f0))) + 10};
  const xs = d3.scaleBand().domain(meses).range([m.l, W - m.r]).padding(0.22);
  ys.range([H - m.b, m.t]);
  svg.append('g').attr('class', 'pf-gl').selectAll('line').data(yt).join('line').attr('x1', m.l).attr('x2', W - m.r).attr('y1', ys).attr('y2', ys);
  svg.append('g').attr('class', 'pf-axis').selectAll('text').data(yt).join('text').attr('x', m.l - 8).attr('y', ys).attr('dy', '0.32em').attr('text-anchor', 'end').text(PF.fmt.f0);
  const every = Math.ceil(meses.length / Math.max(2, Math.floor((W - m.l) / 52)));
  svg.append('g').attr('class', 'pf-axis').selectAll('text').data(meses.filter((_, i) => i % every === 0)).join('text')
    .attr('x', (d) => xs(d) + xs.bandwidth() / 2).attr('y', H - 6).attr('text-anchor', 'middle').text((d) => PF.mShort(PF.parse(d)));
  const stack = d3.stack().keys(inst)(data);
  stack.forEach((layer, i) => {
    svg.append('g').style('fill', PF.col(i + 1)).selectAll('rect').data(layer).join('rect')
      .attr('x', (d) => xs(d.data.mes)).attr('width', xs.bandwidth()).attr('y', (d) => ys(d[1])).attr('height', (d) => Math.max(0, ys(d[0]) - ys(d[1]))).attr('rx', 1.5);
  });
  const last = data[data.length - 1];
  if (last && last.total > 0) svg.append('text').attr('class', 'pf-val').attr('x', xs(last.mes) + xs.bandwidth() / 2).attr('y', ys(last.total) - 5).attr('text-anchor', 'end').text(PF.fmt.f0(last.total));
  const tip = PF.makeTip(el);
  svg.append('g').selectAll('rect').data(data).join('rect').attr('x', (d) => xs(d.mes) - xs.step() * xs.paddingInner() / 2).attr('width', xs.step())
    .attr('y', m.t).attr('height', H - m.b - m.t).attr('fill', 'transparent').style('touch-action', 'pan-y')
    .on('pointerenter pointerdown', (ev, d) => tip.show(xs(d.mes) + xs.bandwidth() / 2, m.t, W, PF.mLong(d._x),
      inst.map((i, j) => [i.replace(/ \(.*\)/, ''), PF.fmt.f0(d[i]), PF.col(j + 1)]).concat([['Total', PF.fmt.f0(d.total), null]])))
    .on('pointerleave', () => tip.hide());
});

dash.draw('chTopU', (el) => {
  if (!PF.ok(el, ['unidades_resumo'])) return;
  el.replaceChildren();
  const R = dash.data('unidades_resumo').data.slice().sort((a, b) => b.prox12 - a.prox12).slice(0, 10);
  const W = Math.max(260, el.clientWidth), rh = 32, H = R.length * rh + 30;
  const svg = PF.svgFor(el, W, H, 'Produção média dos 10 maiores campos nos últimos 12 meses e nos próximos 12 meses');
  const lw = Math.ceil(PF.measure(svg, R.map((r) => PF.nome(r.unidade)))) + 12;
  const vw = Math.ceil(PF.measure(svg, R.map((r) => PF.fmt.f0(r.prox12) + '  ' + PF.fmt.pct(r.var_pct)))) + 14;
  const m = {l: lw, r: vw, t: 4, b: 24};
  const xs = d3.scaleLinear().domain([0, d3.max(R, (r) => Math.max(r.ult12, r.prox12)) * 1.04]).nice().range([m.l, W - m.r]);
  const xt = xs.ticks(Math.max(2, Math.floor((W - m.l - m.r) / 70)));
  svg.append('g').attr('class', 'pf-gl').selectAll('line').data(xt).join('line').attr('x1', xs).attr('x2', xs).attr('y1', m.t).attr('y2', H - m.b);
  svg.append('g').attr('class', 'pf-axis').selectAll('text').data(xt).join('text').attr('x', xs).attr('y', H - 6).attr('text-anchor', 'middle').text(PF.fmt.f0);
  const c1 = PF.col(1);
  const tip = PF.makeTip(el);
  const gr = svg.append('g').selectAll('g').data(R).join('g').attr('class', 'pf-hit').attr('transform', (r, i) => `translate(0,${m.t + i * rh + rh / 2})`)
    .on('click', (ev, r) => { PF.selUnit(r.unidade); PF.abrir('campos'); })
    .on('pointerenter', (ev, r) => { const i = R.indexOf(r); tip.show(xs(Math.max(r.ult12, r.prox12)), m.t + i * rh + rh, W, PF.nome(r.unidade) + ' · ' + r.operador,
      [['Últimos 12 meses', PF.fmt.f1(r.ult12), 'var(--cds-chart-muted)'], ['Próximos 12 meses', PF.fmt.f1(r.prox12), c1], ['Variação', PF.fmt.pct(r.var_pct), null], ['Royalties 12m (R$ bi)', PF.fmt.f2(r.royalties12), null]]); })
    .on('pointerleave', () => tip.hide());
  gr.append('rect').attr('class', 'pf-hl').attr('x', 0).attr('y', -rh / 2).attr('width', W).attr('height', rh).attr('fill', 'transparent').attr('rx', 4);
  gr.append('text').attr('class', 'pf-lab').attr('x', m.l - 10).attr('dy', '0.32em').attr('text-anchor', 'end').text((r) => PF.nome(r.unidade));
  gr.append('line').attr('x1', (r) => xs(r.ult12)).attr('x2', (r) => xs(r.prox12)).style('stroke', 'var(--cds-chart-muted)').attr('stroke-width', 3).attr('stroke-linecap', 'round');
  gr.append('circle').attr('r', 5).attr('cx', (r) => xs(r.ult12)).style('fill', 'var(--cds-chart-muted)');
  gr.append('circle').attr('class', 'pf-dot').attr('r', 6).attr('cx', (r) => xs(r.prox12)).style('fill', c1);
  const tv = gr.append('text').attr('class', 'pf-val').attr('x', (r) => xs(Math.max(r.ult12, r.prox12)) + 10).attr('dy', '0.32em');
  tv.append('tspan').text((r) => PF.fmt.f0(r.prox12) + '  ');
  tv.append('tspan').attr('class', (r) => r.var_pct >= 0 ? 'up' : 'down').style('fill', (r) => r.var_pct >= 0 ? 'var(--color-ok)' : 'var(--color-bad)').text((r) => PF.fmt.pct(r.var_pct));
});

// Campos
dash.draw('selU', (sel) => {
  const s = dash.data('unidades_resumo');
  const R = s.status === 'ok' ? s.data : [];
  sel.replaceChildren(...R.map((r) => new Option(PF.nome(r.unidade), r.unidade)));
  if (R.length && !R.some((r) => r.unidade === PF.st.unit)) PF.st.unit = R[0].unidade;
  sel.value = PF.st.unit || '';
  sel.onchange = () => PF.selUnit(sel.value);
});
dash.draw('chU', (el) => {
  if (!PF.ok(el, ['hist_campos', 'central_campos', 'unidades_resumo'])) return;
  const u = PF.st.unit || dash.data('unidades_resumo').data[0].unidade, h = PF.P().h;
  const c0 = PF.col(0), c1 = PF.col(1), f = PF.fmt.f1;
  const past = dash.data('hist_campos').data.filter((r) => r.unidade === u && r.h === h && r.real > 0).map((r) => ({mes: r.mes, real: r.real, prev: r.previsto}));
  const ult = past[past.length - 1];
  if (ult) Object.assign(ult, {p10: ult.real, p50: ult.real, p90: ult.real});
  const fut = dash.data('central_campos').data.filter((r) => r.unidade === u).map((r) => ({mes: r.mes, p10: r.p10, p50: r.p50, p90: r.p90}));
  const R = past.concat(fut).map((r) => Object.assign(r, {_x: PF.parse(r.mes)}));
  PF.tchart(el, {
    rows: R, vline: ult ? PF.parse(ult.mes) : null, endLabel: 'p50', yfmt: PF.fmt.f0, zero: true,
    aria: 'Produção de ' + PF.nome(u) + ': realizado, o que o modelo previu ' + h + ' meses antes e a previsão dos próximos 18 meses com faixa',
    series: [{k: 'prev', color: c1, w: 1.6, dash: '2 3'}, {k: 'real', color: c0, w: 2.2}, {k: 'p50', color: c1, dash: '6 4', w: 2.2}],
    band: {lo: 'p10', hi: 'p90', color: c1},
    tip: (r) => r.real != null && r !== ult
      ? [['Realizado', f(r.real), c0], ['Previsto ' + h + (h === 1 ? ' mês' : ' meses') + ' antes', r.prev == null ? null : f(r.prev) + ' (' + PF.fmt.pct((r.prev / r.real - 1) * 100) + ')', c1]]
      : r === ult ? [['Realizado (último mês)', f(r.real), c0]]
        : [['Previsão P50', f(r.p50), c1], ['Faixa P10–P90', f(r.p10) + '–' + f(r.p90), null]]
  });
});
PF.tabela = function (tb, id, key, cols, keyField, selected, onPick) {
  const s = dash.data(id);
  if (s.status !== 'ok') { tb.replaceChildren(); return; }
  const {k, d} = PF.st.sort[key];
  const R = s.data.slice().sort((a, b) => (typeof a[k] === 'string' ? String(a[k]).localeCompare(String(b[k]), 'pt-BR') : a[k] - b[k]) * d);
  tb.replaceChildren(...R.map((r) => {
    const tr = document.createElement('tr');
    tr.setAttribute('data-key', PF.enc(r[keyField]));
    if (r[keyField] === selected) tr.className = 'sel';
    cols.forEach(([field, f]) => {
      const td = document.createElement('td');
      const v = r[field];
      td.textContent = v == null ? '—' : f(v);
      if (typeof v === 'string') td.className = 'txt';
      if (field === 'var_pct' && v != null) td.className = v >= 0 ? 'up' : 'down';
      tr.append(td);
    });
    tr.addEventListener('click', () => onPick(r[keyField]));
    return tr;
  }));
};
dash.draw('tbU', (tb) => PF.tabela(tb, 'unidades_resumo', 'unit',
  [['unidade', PF.nome], ['operador', String], ['ult12', PF.fmt.f1], ['prox12', PF.fmt.f1], ['var_pct', PF.fmt.pct], ['receita12', PF.fmt.f2], ['royalties12', PF.fmt.f2]],
  'unidade', PF.st.unit, (u) => { PF.selUnit(u); const c = document.getElementById('card-campo'); if (c) c.scrollIntoView({behavior: 'smooth', block: 'start'}); }));

// Empresas
dash.draw('chEmp', (el) => {
  if (!PF.ok(el, ['empresas_resumo'])) return;
  el.replaceChildren();
  const R = dash.data('empresas_resumo').data.slice().sort((a, b) => b.prox12 - a.prox12);
  const W = Math.max(260, el.clientWidth), rh = 32, H = R.length * rh + 8;
  const svg = PF.svgFor(el, W, H, 'Produção líquida prevista por empresa nos próximos 12 meses');
  const lw = Math.ceil(PF.measure(svg, R.map((r) => r.empresa))) + 12;
  const vw = Math.ceil(PF.measure(svg, R.map((r) => PF.fmt.f0(r.prox12) + '  ' + PF.fmt.pct(r.var_pct)))) + 12;
  const X = d3.scaleLinear().domain([0, d3.max(R, (r) => Math.max(r.prox12, r.ult12))]).range([lw, W - vw]);
  const tip = PF.makeTip(el);
  const g = svg.append('g').selectAll('g').data(R).join('g').attr('class', 'pf-hit').attr('transform', (r, i) => `translate(0,${4 + i * rh})`)
    .on('click', (ev, r) => PF.selEmp(r.empresa))
    .on('pointerenter', (ev, r) => { const i = R.indexOf(r); tip.show(X(r.prox12), 4 + i * rh + rh, W, r.empresa,
      [['Últimos 12 meses', PF.fmt.f1(r.ult12), 'var(--cds-chart-muted)'], ['Próximos 12 meses', PF.fmt.f1(r.prox12), PF.col(0)], ['Receita 12m (R$ bi)', PF.fmt.f2(r.receita12), null], ['Royalties 12m (R$ bi)', PF.fmt.f2(r.royalties12), null]]); })
    .on('pointerleave', () => tip.hide());
  g.append('rect').attr('class', 'pf-hl').attr('x', 0).attr('width', W).attr('height', rh).attr('fill', 'transparent').attr('rx', 4);
  g.append('text').attr('class', 'pf-lab').attr('x', lw - 10).attr('y', rh / 2).attr('dy', '0.32em').attr('text-anchor', 'end')
    .style('font-weight', (r) => r.empresa === PF.st.emp ? 'var(--cds-font-weight-medium)' : null).text((r) => r.empresa);
  g.append('rect').attr('x', lw).attr('y', 7).attr('height', rh - 14).attr('rx', 3).attr('width', (r) => Math.max(2, X(r.prox12) - lw))
    .style('fill', PF.col(0)).style('opacity', (r) => !PF.st.emp || r.empresa === PF.st.emp ? 1 : 0.45);
  g.append('line').attr('x1', (r) => X(r.ult12)).attr('x2', (r) => X(r.ult12)).attr('y1', 4).attr('y2', rh - 4).style('stroke', 'var(--color-fg)').attr('stroke-width', 2);
  const tv = g.append('text').attr('class', 'pf-val').attr('x', (r) => Math.max(X(r.prox12), X(r.ult12)) + 8).attr('y', rh / 2).attr('dy', '0.32em');
  tv.append('tspan').text((r) => PF.fmt.f0(r.prox12) + '  ');
  tv.append('tspan').style('fill', (r) => r.var_pct >= 0 ? 'var(--color-ok)' : 'var(--color-bad)').text((r) => PF.fmt.pct(r.var_pct));
});
dash.draw('selE', (sel) => {
  const s = dash.data('empresas_resumo');
  const R = s.status === 'ok' ? s.data : [];
  sel.replaceChildren(...R.map((r) => new Option(r.empresa, r.empresa)));
  if (R.length && !R.some((r) => r.empresa === PF.st.emp)) PF.st.emp = R[0].empresa;
  sel.value = PF.st.emp || '';
  sel.onchange = () => PF.selEmp(sel.value);
});
dash.draw('chE', (el) => {
  if (!PF.ok(el, ['empresas_mensal', 'empresas_resumo'])) return;
  const e = PF.st.emp || dash.data('empresas_resumo').data[0].empresa;
  const R = PF.rows('empresas_mensal').filter((r) => r.empresa === e);
  const lastReal = d3.max(R.filter((r) => r.realizado != null), (r) => r._x);
  const c0 = PF.col(0), c1 = PF.col(1), f = PF.fmt.f1;
  PF.tchart(el, {
    rows: R, vline: lastReal, endLabel: 'previsto', yfmt: PF.fmt.f0, zero: true,
    aria: 'Produção líquida realizada e prevista de ' + e,
    series: [{k: 'realizado', color: c0}, {k: 'previsto', color: c1, dash: '5 4', w: 2.2}],
    tip: (r) => [['Realizado', r.realizado == null ? null : f(r.realizado), c0], ['Previsão P50', r.realizado != null || r.previsto == null ? null : f(r.previsto), c1]]
  });
});
dash.draw('tbE', (tb) => PF.tabela(tb, 'empresas_resumo', 'emp',
  [['empresa', String], ['ult12', PF.fmt.f1], ['prox12', PF.fmt.f1], ['var_pct', PF.fmt.pct], ['receita12', PF.fmt.f2], ['royalties12', PF.fmt.f2]],
  'empresa', PF.st.emp, (e) => PF.selEmp(e)));

// Receita e royalties
dash.draw('chRoy', (el) => {
  if (!PF.ok(el, ['royalties_mensal'])) return;
  el.replaceChildren();
  const R = PF.rows('royalties_mensal');
  const W = Math.max(260, el.clientWidth), H = Math.round(Math.max(260, Math.min(360, W * 0.5)));
  const svg = PF.svgFor(el, W, H, 'Royalties mensais previstos, P50 com faixa P10–P90, em bilhões de reais');
  const ys = d3.scaleLinear().domain([0, d3.max(R, (r) => r.royalties_p90) * 1.08]).nice();
  const yt = ys.ticks(5);
  const m = {t: 14, r: 6, b: 26, l: Math.ceil(PF.measure(svg, yt.map(PF.fmt.f0))) + 10};
  const xs = d3.scaleBand().domain(R.map((r) => r.mes)).range([m.l, W - m.r]).padding(0.28);
  ys.range([H - m.b, m.t]);
  svg.append('g').attr('class', 'pf-gl').selectAll('line').data(yt).join('line').attr('x1', m.l).attr('x2', W - m.r).attr('y1', ys).attr('y2', ys);
  svg.append('g').attr('class', 'pf-axis').selectAll('text').data(yt).join('text').attr('x', m.l - 8).attr('y', ys).attr('dy', '0.32em').attr('text-anchor', 'end').text(PF.fmt.f0);
  const every = Math.ceil(R.length / Math.max(2, Math.floor((W - m.l) / 52)));
  svg.append('g').attr('class', 'pf-axis').selectAll('text').data(R.filter((_, i) => i % every === 0)).join('text')
    .attr('x', (r) => xs(r.mes) + xs.bandwidth() / 2).attr('y', H - 6).attr('text-anchor', 'middle').text((r) => PF.mShort(r._x));
  svg.append('g').selectAll('rect').data(R).join('rect').attr('x', (r) => xs(r.mes)).attr('width', xs.bandwidth())
    .attr('y', (r) => ys(r.royalties_p50)).attr('height', (r) => ys(0) - ys(r.royalties_p50)).attr('rx', 2).style('fill', PF.col(0));
  const cx = (r) => xs(r.mes) + xs.bandwidth() / 2;
  svg.append('g').selectAll('line').data(R).join('line').attr('x1', cx).attr('x2', cx).attr('y1', (r) => ys(r.royalties_p10)).attr('y2', (r) => ys(r.royalties_p90))
    .style('stroke', 'var(--color-fg)').attr('stroke-width', 1.5).style('opacity', 0.55);
  svg.append('g').selectAll('circle').data(R).join('circle').attr('cx', cx).attr('cy', (r) => ys(r.royalties_p10)).attr('r', 2).style('fill', 'var(--color-fg)').style('opacity', 0.55);
  svg.append('g').selectAll('circle').data(R).join('circle').attr('cx', cx).attr('cy', (r) => ys(r.royalties_p90)).attr('r', 2).style('fill', 'var(--color-fg)').style('opacity', 0.55);
  const r0 = R[0];
  if (r0) svg.append('text').attr('class', 'pf-val').attr('x', cx(r0)).attr('y', ys(r0.royalties_p90) - 6).attr('text-anchor', 'start').text(PF.fmt.f1(r0.royalties_p50));
  const tip = PF.makeTip(el);
  svg.append('g').selectAll('rect').data(R).join('rect').attr('x', (r) => xs(r.mes) - xs.step() * xs.paddingInner() / 2).attr('width', xs.step())
    .attr('y', m.t).attr('height', H - m.b - m.t).attr('fill', 'transparent').style('touch-action', 'pan-y')
    .on('pointerenter pointerdown', (ev, r) => tip.show(cx(r), m.t, W, PF.mLong(r._x), [['Royalties P50', 'R$ ' + PF.fmt.f2(r.royalties_p50) + ' bi', PF.col(0)],
      ['Faixa P10–P90', PF.fmt.f1(r.royalties_p10) + '–' + PF.fmt.f1(r.royalties_p90), null], ['Receita bruta P50', 'R$ ' + PF.fmt.f1(r.receita_p50) + ' bi', null]]))
    .on('pointerleave', () => tip.hide());
});
dash.draw('chBrent', (el) => {
  if (!PF.ok(el, ['mercado'])) return;
  const R = PF.rows('mercado'); const c0 = PF.col(0), f = PF.fmt.f1;
  PF.tchart(el, {
    rows: R, yfmt: PF.fmt.f0, endLabel: 'brent_base',
    aria: 'Cenário de Brent em dólares por barril, base e faixa P10–P90, até março de 2028',
    series: [{k: 'brent_base', color: c0, w: 2.2}], band: {lo: 'brent_p10', hi: 'brent_p90', color: c0},
    tip: (r) => [['Brent (base)', 'US$ ' + f(r.brent_base), c0], ['Faixa P10–P90', f(r.brent_p10) + '–' + f(r.brent_p90), null], ['Câmbio (R$/US$)', PF.fmt.f2(r.ptax_p50), null]]
  });
});

// Acurácia
dash.draw('chAcc', (el) => {
  if (!PF.ok(el, ['acuracia'])) return;
  el.replaceChildren();
  const R = dash.data('acuracia').data.slice().sort((a, b) => a.wape_pct - b.wape_pct);
  const W = Math.max(260, el.clientWidth), rh = 44, H = R.length * rh + 4;
  const svg = PF.svgFor(el, W, H, 'Erro por campo de cada método de previsão, de 2022 em diante');
  const vw = Math.ceil(PF.measure(svg, R.map((r) => PF.fmt.f1(r.wape_pct) + '%'))) + 10;
  const xs = d3.scaleLinear().domain([0, d3.max(R, (r) => r.wape_pct)]).range([0, W - vw]);
  const tip = PF.makeTip(el);
  const g = svg.append('g').selectAll('g').data(R).join('g').attr('transform', (r, i) => `translate(0,${i * rh})`)
    .on('pointerenter pointerdown', (ev, r) => { const i = R.indexOf(r); tip.show(xs(r.wape_pct), i * rh + rh, W, r.metodo,
      [['Erro por campo', PF.fmt.f1(r.wape_pct) + '%', null], ['Erro da carteira', PF.fmt.f1(r.erro_carteira_pct) + '%', null], ['Viés', PF.fmt.pct(r.vies_pct), null]]); })
    .on('pointerleave', () => tip.hide());
  g.append('rect').attr('width', W).attr('height', rh).attr('fill', 'transparent');
  const fin = (r) => /^Modelo final/.test(r.metodo);
  g.append('text').attr('class', 'pf-lab').attr('x', 0).attr('y', 14).style('font-weight', (r) => fin(r) ? 'var(--cds-font-weight-medium)' : null).text((r) => r.metodo);
  g.append('rect').attr('x', 0).attr('y', 21).attr('height', 14).attr('rx', 3).attr('width', (r) => Math.max(2, xs(r.wape_pct)))
    .style('fill', (r) => fin(r) ? PF.col(0) : 'var(--cds-chart-muted)');
  g.append('text').attr('class', 'pf-val').attr('x', (r) => xs(r.wape_pct) + 6).attr('y', 28).attr('dy', '0.32em').text((r) => PF.fmt.f1(r.wape_pct) + '%');
});
dash.draw('chTrack', (el) => {
  if (!PF.ok(el, ['track_record'])) return;
  const R = PF.rows('track_record'); const c0 = PF.col(0), c1 = PF.col(1), f = PF.fmt.f0;
  PF.tchart(el, {
    rows: R, yfmt: f,
    aria: 'Produção total realizada comparada com a prevista seis meses antes pelo modelo e pelo método ingênuo, 2019 a 2026',
    series: [{k: 'ingenuo', color: 'var(--cds-chart-muted)', dash: '4 3', w: 1.5}, {k: 'modelo', color: c1, w: 1.8}, {k: 'real', color: c0, w: 2.2}],
    tip: (r) => [['Realizado', f(r.real), c0], ['Modelo', f(r.modelo) + ' (' + PF.fmt.pct((r.modelo / r.real - 1) * 100) + ')', c1], ['Repetir o último mês', f(r.ingenuo), 'var(--cds-chart-muted)']]
  });
});

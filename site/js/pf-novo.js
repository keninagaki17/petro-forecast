// Sócios campo a campo e plataformas
(() => {
  const r1 = (x) => Math.round(x * 10) / 10;
  const linha = (cells, key) => {
    const tr = document.createElement('tr');
    if (key) tr.setAttribute('data-key', key);
    cells.forEach(([t, c]) => { const td = document.createElement('td'); td.textContent = t == null ? '—' : t; if (c) td.className = c; tr.append(td); });
    return tr;
  };
  const sinal = (v) => v == null ? '' : v >= 0 ? 'up' : 'down';

  // ---- Sócios
  const empresa = () => {
    const s = dash.data('dependencia');
    if (s.status === 'ok' && s.data.length && !s.data.some((r) => r.empresa === PF.st.emp)) PF.st.emp = s.data[0].empresa;
    return PF.st.emp;
  };
  dash.draw('dkv', (el) => { const e = empresa(); if (e) el.setAttribute('data-where', 'empresa=' + PF.enc(e)); PF.fillValue(el); });
  dash.draw('chDep', (el) => {
    if (!PF.ok(el, ['dependencia'])) return;
    el.replaceChildren();
    const R = dash.data('dependencia').data.filter((r) => r.empresa !== 'Petrobras').sort((a, b) => b.prox12 - a.prox12), sel = empresa();
    const W = Math.max(260, el.clientWidth), rh = 32, Ht = R.length * rh + 6;
    const svg = PF.svgFor(el, W, Ht, 'Parcela da produção de cada sócio em campos operados pela Petrobras, pela própria empresa e por terceiros');
    const lw = Math.ceil(PF.measure(svg, R.map((r) => r.empresa))) + 12, vw = Math.ceil(PF.measure(svg, ['100%'])) + 10;
    const x = d3.scaleLinear().domain([0, 100]).range([lw, W - vw]);
    const seg = [['petrobras_pct', PF.col(0), 'Operado pela Petrobras'], ['propria_pct', PF.col(1), 'Operado pela própria empresa'], ['outros_pct', 'var(--cds-chart-muted)', 'Operado por terceiros']];
    const tip = PF.makeTip(el);
    const g = svg.append('g').selectAll('g').data(R).join('g').attr('class', 'pf-hit').attr('transform', (r, i) => `translate(0,${3 + i * rh})`)
      .on('click', (ev, r) => PF.selEmp(r.empresa))
      .on('pointerenter', (ev, r) => tip.show(x(50), 3 + R.indexOf(r) * rh + rh, W, r.empresa + ' · ' + PF.fmt.f0(r.prox12) + ' mil bbl/d', seg.map(([k, c, t]) => [t, PF.fmt.pc(r[k]), c])))
      .on('pointerleave', () => tip.hide());
    g.append('rect').attr('class', 'pf-hl').attr('width', W).attr('height', rh).attr('fill', 'transparent').attr('rx', 4);
    g.append('text').attr('class', 'pf-lab').attr('x', lw - 10).attr('y', rh / 2).attr('dy', '0.32em').attr('text-anchor', 'end')
      .style('font-weight', (r) => r.empresa === sel ? 'var(--cds-font-weight-medium)' : null).text((r) => r.empresa);
    seg.forEach(([k, c], j) => {
      const ini = (r) => d3.sum(seg.slice(0, j), ([q]) => r[q]);
      g.append('rect').attr('x', (r) => x(ini(r)) + (j ? 1 : 0)).attr('y', 8).attr('height', rh - 16).attr('width', (r) => Math.max(0, x(ini(r) + r[k]) - x(ini(r)) - (j ? 1 : 0))).style('fill', c);
    });
    g.append('text').attr('class', 'pf-val').attr('x', W - vw + 6).attr('y', rh / 2).attr('dy', '0.32em').text((r) => PF.fmt.f0(r.petrobras_pct) + '%');
  });
  dash.draw('tbSoc', (tb) => {
    const s = dash.data('socios_campos');
    if (s.status !== 'ok') { tb.replaceChildren(); return; }
    const e = empresa(), R = s.data.filter((r) => r.empresa === e).sort((a, b) => b.prox12 - a.prox12);
    tb.replaceChildren(...R.map((r) => linha([[PF.nome(r.unidade), 'txt'], [r.operador, 'txt'], [PF.fmt.pc(r.part_pct)], [PF.fmt.f1(r.ult12)], [PF.fmt.f1(r.prox12)],
      [r.var_pct == null ? null : PF.fmt.pct(r.var_pct), sinal(r.var_pct)], [PF.fmt.f2(r.receita12)]], PF.enc(r.empresa) + ',' + PF.enc(r.unidade))));
  });

  // ---- Plataformas
  dash.calc('concentracao', {
    inputs: ['crescimento', 'kpis'], title: 'De onde vem o aumento da produção',
    description: 'Os dois campos que mais crescem nos próximos 12 meses e a parte deles no aumento total, em mil bbl/d.',
    fn: (crescimento, kpis) => {
      const C = crescimento.filter((r) => r.unidade !== 'Demais campos').sort((a, b) => b.delta - a.delta), p = kpis.find((r) => r.kpi === 'producao');
      const total = p.valor - p.ref;
      return [{top1: C[0].unidade, d1: C[0].delta, top2: C[1].unidade, d2: C[1].delta, total, pct: r1((C[0].delta + C[1].delta) / total * 100)}];
    }
  });
  dash.draw('chCres', (el) => {
    if (!PF.ok(el, ['crescimento'])) return;
    el.replaceChildren();
    const R = dash.data('crescimento').data.slice().sort((a, b) => b.delta - a.delta);
    const W = Math.max(260, el.clientWidth), rh = 30, Ht = R.length * rh + 6;
    const svg = PF.svgFor(el, W, Ht, 'Variação da produção média de cada campo, próximos 12 meses contra os últimos 12');
    const lw = Math.ceil(PF.measure(svg, R.map((r) => PF.nome(r.unidade)))) + 12, vw = Math.ceil(PF.measure(svg, R.map((r) => PF.fmt.s0(r.delta)))) + 10;
    const mn = Math.min(0, d3.min(R, (r) => r.delta)), mx = Math.max(0, d3.max(R, (r) => r.delta));
    const x = d3.scaleLinear().domain([mn, mx]).range([lw + (mn < 0 ? vw : 0), W - vw]);
    const tip = PF.makeTip(el);
    svg.append('line').attr('class', 'pf-base').attr('x1', x(0)).attr('x2', x(0)).attr('y1', 0).attr('y2', Ht);
    const g = svg.append('g').selectAll('g').data(R).join('g').attr('transform', (r, i) => `translate(0,${3 + i * rh})`)
      .on('pointerenter pointerdown', (ev, r) => tip.show(x(Math.max(0, r.delta)), 3 + R.indexOf(r) * rh + rh, W, PF.nome(r.unidade),
        [['Últimos 12 meses', PF.fmt.f1(r.ult12), null], ['Próximos 12 meses', PF.fmt.f1(r.prox12), null], ['Variação', PF.fmt.s1(r.delta), null]]))
      .on('pointerleave', () => tip.hide());
    g.append('rect').attr('width', W).attr('height', rh).attr('fill', 'transparent');
    g.append('text').attr('class', 'pf-lab').attr('x', lw - 10).attr('y', rh / 2).attr('dy', '0.32em').attr('text-anchor', 'end').text((r) => PF.nome(r.unidade));
    g.append('rect').attr('y', 7).attr('height', rh - 14).attr('rx', 2).attr('x', (r) => x(Math.min(0, r.delta))).attr('width', (r) => Math.max(1, Math.abs(x(r.delta) - x(0))))
      .style('fill', (r) => r.delta >= 0 ? PF.col(0) : 'var(--cds-chart-muted)');
    g.append('text').attr('class', 'pf-val').attr('y', rh / 2).attr('dy', '0.32em').attr('x', (r) => r.delta >= 0 ? x(r.delta) + 6 : x(r.delta) - 6)
      .attr('text-anchor', (r) => r.delta >= 0 ? 'start' : 'end').text((r) => PF.fmt.s0(r.delta));
  });
  dash.draw('chCurva', (el) => {
    if (!PF.ok(el, ['curva_rampa'])) return;
    el.replaceChildren();
    const R = dash.data('curva_rampa').data, c0 = PF.col(0);
    const W = Math.max(260, el.clientWidth), Ht = Math.round(Math.max(240, Math.min(320, W * 0.55)));
    const svg = PF.svgFor(el, W, Ht, 'Percentual da capacidade atingido a cada mês depois do primeiro óleo: mediana e faixa de 46 plataformas');
    const y = d3.scaleLinear().domain([0, Math.max(100, d3.max(R, (r) => r.p90))]).nice(), yt = y.ticks(5);
    const m = {t: 14, r: 40, b: 26, l: Math.ceil(PF.measure(svg, yt.map((v) => v + '%'))) + 10};
    const x = d3.scaleLinear().domain(d3.extent(R, (r) => r.mes)).range([m.l, W - m.r]);
    y.range([Ht - m.b, m.t]);
    svg.append('g').attr('class', 'pf-gl').selectAll('line').data(yt).join('line').attr('x1', m.l).attr('x2', W - m.r).attr('y1', y).attr('y2', y);
    svg.append('g').attr('class', 'pf-axis').selectAll('text').data(yt).join('text').attr('x', m.l - 8).attr('y', y).attr('dy', '0.32em').attr('text-anchor', 'end').text((v) => v + '%');
    svg.append('g').attr('class', 'pf-axis').selectAll('text').data([1, 6, 12, 18, 24]).join('text').attr('x', x).attr('y', Ht - 6).attr('text-anchor', 'middle').text((v) => v + (v === 24 ? ' meses' : ''));
    svg.append('line').attr('class', 'pf-ref').attr('x1', m.l).attr('x2', W - m.r).attr('y1', y(80)).attr('y2', y(80));
    svg.append('path').datum(R).style('fill', c0).style('opacity', 0.16).attr('d', d3.area().x((r) => x(r.mes)).y0((r) => y(r.p10)).y1((r) => y(r.p90)));
    svg.append('path').datum(R).attr('fill', 'none').style('stroke', c0).attr('stroke-width', 2.2).attr('d', d3.line().x((r) => x(r.mes)).y((r) => y(r.p50)));
    const u = R[R.length - 1];
    svg.append('text').attr('class', 'pf-val').attr('x', x(u.mes) + 6).attr('y', y(u.p50)).attr('dy', '0.32em').text(PF.fmt.f0(u.p50) + '%');
    const g = svg.append('g').style('display', 'none').attr('pointer-events', 'none');
    const vl = g.append('line').attr('class', 'pf-cross').attr('y1', m.t).attr('y2', Ht - m.b), dot = g.append('circle').attr('class', 'pf-dot').attr('r', 4).style('fill', c0);
    const tip = PF.makeTip(el);
    const move = (ev) => {
      const [px] = d3.pointer(ev, svg.node()), r = R[d3.bisector((q) => q.mes).center(R, x.invert(px))]; if (!r) return;
      g.style('display', null); vl.attr('x1', x(r.mes)).attr('x2', x(r.mes)); dot.attr('cx', x(r.mes)).attr('cy', y(r.p50));
      tip.show(x(r.mes), m.t, W, r.mes + (r.mes === 1 ? ' mês' : ' meses') + ' após o 1º óleo', [['Mediana', PF.fmt.pc(r.p50), c0], ['Faixa P10–P90', PF.fmt.f0(r.p10) + '–' + PF.fmt.f0(r.p90) + '%', null]]);
    };
    svg.append('rect').attr('x', m.l).attr('y', 0).attr('width', Math.max(0, W - m.l - m.r)).attr('height', Ht - m.b).attr('fill', 'transparent').style('touch-action', 'pan-y')
      .on('pointermove', move).on('pointerdown', move).on('pointerleave', () => { g.style('display', 'none'); tip.hide(); });
  });
  dash.draw('tbRampas', (tb) => {
    const s = dash.data('rampas');
    if (s.status !== 'ok') { tb.replaceChildren(); return; }
    tb.replaceChildren(...s.data.map((r) => linha([[r.plataforma, 'txt'], [PF.nome(r.unidade), 'txt'], [PF.mShort(PF.parse(r.inicio))], [PF.fmt.f0(r.capacidade)],
      [r.meses_80 == null ? 'ainda não' : PF.fmt.f0(r.meses_80)], [r.pct_12 == null ? null : PF.fmt.pc(r.pct_12)], [PF.fmt.pc(r.pico_pct)]], PF.enc(r.plataforma))));
  });
})();

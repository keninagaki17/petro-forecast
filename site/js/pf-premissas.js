// Aba Premissas: o que move a receita prevista, mês a mês, e de onde vem cada número
(() => {
  const f0 = PF.fmt.f0, f1 = PF.fmt.f1, f2 = PF.fmt.f2;
  const emp = () => (dash.params() || {}).emp || 'Total';
  const nomeEmp = (e) => e === 'Total' ? 'todas as empresas' : e;
  const mm = (s) => PF.mShort(PF.parse(s));

  // Ponte da receita: últimos 12 meses realizados → próximos 12 previstos, separada em volume, preço em dólar e câmbio.
  // Receita = barris × preço em US$ × câmbio; cada efeito é a parte da variação explicada pelo seu fator (média logarítmica).
  dash.calc('ponte_receita', {
    inputs: ['receita_meses'], title: 'Ponte da receita: últimos 12 meses × próximos 12',
    description: 'Para a empresa escolhida: receita realizada dos últimos 12 meses, efeito de volume, de preço em dólar e de câmbio, e a receita prevista dos próximos 12 meses, em R$ bi.',
    fn: (rows) => {
      const L = rows.filter((r) => r.empresa === emp()).sort((a, b) => (a.mes < b.mes ? -1 : 1));
      const A = L.filter((r) => r.origem === 'realizado').slice(-12), B = L.filter((r) => r.origem === 'previsto').slice(0, 12);
      if (!A.length || !B.length) return [];
      const ag = (S) => {
        const R = d3.sum(S, (r) => r.receita), V = d3.sum(S, (r) => r.prod * r.dias) / 1e3;          // milhões de barris
        const F = R / d3.sum(S, (r) => r.receita / r.cambio);
        return {R, V, F, P: R * 1e3 / (V * F), d: d3.sum(S, (r) => r.prod * r.dias) / d3.sum(S, (r) => r.dias), b: d3.mean(S.filter((r) => r.brent != null), (r) => r.brent)};
      };
      const a = ag(A), b = ag(B), Lm = (b.R - a.R) / Math.log(b.R / a.R);
      const ef = (x0, x1) => Lm * Math.log(x1 / x0);
      const ini = {m0: A[0].mes, m1: A[A.length - 1].mes, m2: B[0].mes, m3: B[B.length - 1].mes};
      return [
        Object.assign({etapa: 'Últimos 12 meses', tipo: 'total', valor: a.R, prod: a.d, preco: a.P, cambio: a.F, brent: a.b}, ini),
        Object.assign({etapa: 'Volume', tipo: 'efeito', valor: ef(a.V, b.V)}, ini),
        Object.assign({etapa: 'Preço em US$', tipo: 'efeito', valor: ef(a.P, b.P)}, ini),
        Object.assign({etapa: 'Câmbio', tipo: 'efeito', valor: ef(a.F, b.F)}, ini),
        Object.assign({etapa: 'Próximos 12 meses', tipo: 'total', valor: b.R, prod: b.d, preco: b.P, cambio: b.F, brent: b.b}, ini)
      ];
    }
  });

  dash.draw('empNomeP', (el) => { el.textContent = nomeEmp(emp()); });
  dash.draw('txtExplica', (el) => {
    const s = dash.data('ponte_receita'), m = dash.data('receita_meses');
    if (s.status !== 'ok' || m.status !== 'ok' || !s.data.length) { el.replaceChildren(); return; }
    const [a, v, p, c, b] = s.data, var_ = (b.valor / a.valor - 1) * 100, sg = (x) => (x >= 0 ? '+' : '−') + f1(Math.abs(x));
    const p1 = document.createElement('p'), p2 = document.createElement('p'), p3 = document.createElement('p');
    p1.textContent = `Nos últimos 12 meses (${mm(a.m0)} a ${mm(a.m1)}), a receita bruta de ${nomeEmp(emp())} foi de R$ ${f1(a.valor)} bi. ` +
      `Para os próximos 12 (${mm(a.m2)} a ${mm(a.m3)}), o modelo prevê R$ ${f1(b.valor)} bi (${PF.fmt.pct(var_)}). ` +
      `A diferença vem de três fatores: volume, R$ ${sg(v.valor)} bi (produção média de ${f0(a.prod)} para ${f0(b.prod)} mil bbl/d); ` +
      `preço do petróleo em dólar, R$ ${sg(p.valor)} bi (de US$ ${f1(a.preco)} para US$ ${f1(b.preco)} por barril); ` +
      `e câmbio, R$ ${sg(c.valor)} bi (de R$ ${f2(a.cambio)} para R$ ${f2(b.cambio)}).`;
    const F = m.data.filter((r) => r.empresa === emp() && r.origem === 'previsto').sort((x, y) => (x.mes < y.mes ? -1 : 1));
    const pico = F.reduce((x, y) => (y.receita > x.receita ? y : x)), fim = F[F.length - 1];
    const pr = dash.data('precos'), real = pr.status === 'ok' && pr.data.some((r) => r.mes === pico.mes && r.brent_real != null);
    const dv = (fim.prod / pico.prod - 1) * 100, dr = (1 - fim.receita / pico.receita) * 100;
    const vol = Math.abs(dv) < 1 ? 'com a produção praticamente estável' : dv > 0 ? `mesmo com a produção subindo ${f0(dv)}%` : `com a produção caindo ${f0(-dv)}%`;
    p2.textContent = `Mês a mês, a receita prevista é maior em ${PF.mLong(PF.parse(pico.mes))} (R$ ${f1(pico.receita)} bi), com o Brent ${real ? 'realizado' : 'do cenário'} em US$ ${f0(pico.brent)}. ` +
      `Daí em diante, o cenário base da EIA leva o Brent a US$ ${f0(fim.brent)} em ${PF.mLong(PF.parse(fim.mes))}: a receita mensal ${dr >= 0 ? 'cai ' + f0(dr) : 'sobe ' + f0(-dr)}% nesse período, ${vol}. ` +
      (dv > 1 ? 'A queda vem do preço, não do volume.' : dv < -1 ? 'Preço menor e produção menor somam efeito.' : 'A variação vem do preço.');
    p3.textContent = 'Os meses de fevereiro aparecem mais baixos porque têm 28 ou 29 dias: a produção por dia é a mesma, mas o mês soma menos barris.';
    el.replaceChildren(p1, p2, p3);
  });

  // Ponte em colunas
  dash.draw('chPonte', (el) => {
    if (!PF.ok(el, ['ponte_receita'])) return;
    el.replaceChildren();
    const R = dash.data('ponte_receita').data;
    if (!R.length) return;
    let acc = 0;
    const D = R.map((r) => {
      if (r.tipo === 'total') { acc = r.valor; return Object.assign({}, r, {y0: 0, y1: r.valor}); }
      const o = Object.assign({}, r, {y0: acc, y1: acc + r.valor}); acc += r.valor; return o;
    });
    const rot = {'Últimos 12 meses': 'Últ. 12m', 'Volume': 'Volume', 'Preço em US$': 'Preço US$', 'Câmbio': 'Câmbio', 'Próximos 12 meses': 'Próx. 12m'};
    const W = Math.max(260, el.clientWidth), H = 250;
    const svg = PF.svgFor(el, W, H, 'Ponte da receita: últimos 12 meses realizados, efeitos de volume, preço em dólar e câmbio, e próximos 12 meses previstos');
    const y = d3.scaleLinear().domain([0, d3.max(D, (d) => Math.max(d.y0, d.y1)) * 1.12]).nice(), yt = y.ticks(4);
    const m = {t: 18, r: 6, b: 26, l: Math.ceil(PF.measure(svg, yt.map(f0))) + 10};
    const x = d3.scaleBand().domain(D.map((d) => d.etapa)).range([m.l, W - m.r]).padding(0.3);
    y.range([H - m.b, m.t]);
    svg.append('g').attr('class', 'pf-gl').selectAll('line').data(yt).join('line').attr('x1', m.l).attr('x2', W - m.r).attr('y1', y).attr('y2', y);
    svg.append('g').attr('class', 'pf-axis').selectAll('text').data(yt).join('text').attr('x', m.l - 8).attr('y', y).attr('dy', '0.32em').attr('text-anchor', 'end').text(f0);
    svg.append('g').attr('class', 'pf-axis').selectAll('text').data(D).join('text').attr('x', (d) => x(d.etapa) + x.bandwidth() / 2).attr('y', H - 6).attr('text-anchor', 'middle').text((d) => rot[d.etapa]);
    const col = (d) => d.tipo === 'total' ? PF.col(0) : d.valor >= 0 ? PF.col(2) : PF.col(1);
    svg.append('g').selectAll('rect').data(D).join('rect').attr('x', (d) => x(d.etapa)).attr('width', x.bandwidth())
      .attr('y', (d) => y(Math.max(d.y0, d.y1))).attr('height', (d) => Math.max(1, Math.abs(y(d.y0) - y(d.y1)))).attr('rx', 3).style('fill', col);
    svg.append('g').selectAll('text').data(D).join('text').attr('class', 'pf-val').attr('x', (d) => x(d.etapa) + x.bandwidth() / 2)
      .attr('y', (d) => y(Math.max(d.y0, d.y1)) - 5).attr('text-anchor', 'middle').text((d) => d.tipo === 'total' ? f0(d.valor) : (d.valor >= 0 ? '+' : '−') + f0(Math.abs(d.valor)));
    const tip = PF.makeTip(el);
    svg.append('g').selectAll('rect').data(D).join('rect').attr('x', (d) => x(d.etapa) - x.step() * x.paddingInner() / 2).attr('width', x.step())
      .attr('y', m.t).attr('height', H - m.b - m.t).attr('fill', 'transparent').style('touch-action', 'pan-y')
      .on('pointerenter pointerdown', (ev, d) => tip.show(x(d.etapa) + x.bandwidth() / 2, m.t, W, d.etapa, d.tipo === 'total'
        ? [['Receita', 'R$ ' + f1(d.valor) + ' bi', PF.col(0)], ['Produção média', f0(d.prod) + ' mil bbl/d', null], ['Preço médio', 'US$ ' + f1(d.preco) + '/bbl', null], ['Câmbio médio', 'R$ ' + f2(d.cambio), null]]
        : [['Efeito na receita', (d.valor >= 0 ? '+' : '−') + 'R$ ' + f1(Math.abs(d.valor)) + ' bi', col(d)]]))
      .on('pointerleave', () => tip.hide());
  });

  // Brent: realizado e cenário com faixa
  dash.draw('chPreco', (el) => {
    if (!PF.ok(el, ['precos'])) return;
    const R = PF.rows('precos'), c0 = PF.col(0), c1 = PF.col(1);
    const last = R.filter((r) => r.brent_real != null).slice(-1)[0];
    const rows = R.map((r) => r === last ? Object.assign({}, r, {brent_base: r.brent_real, brent_p10: r.brent_real, brent_p90: r.brent_real}) : r);
    PF.tchart(el, {
      rows, yfmt: f0, zero: true, vline: last ? last._x : null, endLabel: 'brent_base', h: 240,
      aria: 'Brent em dólares por barril: realizado desde 2024 e cenário base até março de 2028, com faixa P10–P90',
      series: [{k: 'brent_real', color: c0, w: 2.2}, {k: 'brent_base', color: c1, w: 2.2, dash: '6 4'}], band: {lo: 'brent_p10', hi: 'brent_p90', color: c1},
      tip: (r) => [['Brent realizado', r.brent_real == null ? null : 'US$ ' + f1(r.brent_real), c0], ['Cenário base', r.brent_real != null || r.brent_base == null ? null : 'US$ ' + f1(r.brent_base), c1],
        ['Faixa P10–P90', r.brent_real != null || r.brent_p10 == null ? null : f0(r.brent_p10) + '–' + f0(r.brent_p90), null], ['Câmbio', r.ptax == null ? null : 'R$ ' + f2(r.ptax) + (r.ptax_tipo === 'realizado' ? '' : ' (cenário)'), null]]
    });
  });

  dash.draw('tbMeses', (tb) => {
    const s = dash.data('receita_meses');
    if (s.status !== 'ok') { tb.replaceChildren(); return; }
    const R = s.data.filter((r) => r.empresa === emp()).sort((a, b) => (a.mes < b.mes ? -1 : 1));
    tb.replaceChildren(...R.map((r) => {
      const tr = document.createElement('tr'); tr.setAttribute('data-key', PF.enc(r.empresa) + ',' + r.mes);
      if (r.origem === 'previsto') tr.className = 'pf-prev';
      [[mm(r.mes), 'txt'], [r.origem === 'previsto' ? 'Previsão' : 'Realizado', 'txt'], [f0(r.prod)], [String(r.dias)], [r.brent == null ? '—' : f0(r.brent)],
        [f2(r.cambio)], [f0(r.preco_rs)], [f2(r.receita)], [f2(r.royalties)]].forEach(([t, k]) => {
        const td = document.createElement('td'); td.textContent = t; if (k) td.className = k; tr.append(td);
      });
      return tr;
    }));
  });
  dash.draw('tbFontes', (tb) => {
    const s = dash.data('fontes');
    if (s.status !== 'ok') { tb.replaceChildren(); return; }
    tb.replaceChildren(...s.data.slice().sort((a, b) => a.ordem - b.ordem).map((r) => {
      const tr = document.createElement('tr'); tr.setAttribute('data-key', String(r.ordem));
      [[r.premissa, 'txt pf-forte'], [r.valor, 'txt'], [r.fonte, 'txt pf-mudo']].forEach(([t, k]) => {
        const td = document.createElement('td'); td.textContent = t; td.className = k; tr.append(td);
      });
      return tr;
    }));
  });
})();

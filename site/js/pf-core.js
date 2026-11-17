window.PF = (() => {
  const L = d3.formatLocale({decimal: ',', thousands: '.', grouping: [3], currency: ['R$ ', '']});
  const T = d3.timeFormatLocale({dateTime: '%d/%m/%Y %H:%M', date: '%d/%m/%Y', time: '%H:%M', periods: ['', ''],
    days: ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado'], shortDays: ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'],
    months: ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'],
    shortMonths: ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']});
  const fmt = {f0: L.format(',.0f'), f1: L.format(',.1f'), f2: L.format(',.2f'),
    pct: (v) => (v > 0 ? '+' : '') + L.format(',.1f')(v) + '%', txt: (v) => String(v)};
  const parse = d3.utcParse('%Y-%m-%d');
  const mShort = T.utcFormat('%b/%y'), mLong = T.utcFormat('%b de %Y');
  const st = {unit: null, emp: null, range: 'all', sort: {unit: {k: 'prox12', d: -1}, emp: {k: 'prox12', d: -1}}, seen: new Set()};
  const col = (i) => i < 0 ? 'var(--cds-chart-muted)' : dash.colors[i % dash.colors.length];
  const enc = (s) => String(s).replace(/%/g, '%25').replace(/&/g, '%26').replace(/=/g, '%3D');
  const small = new Set(['de', 'da', 'do', 'das', 'dos', 'e']);
  const nome = (s) => String(s).toLowerCase().split(/(\s+|\/|-)/).map((w, i) => (i > 0 && small.has(w)) ? w : w.charAt(0).toUpperCase() + w.slice(1)).join('').replace(/_eco\b/i, ' (excedente)');
  const cache = new WeakMap();
  function rows(id) {
    const d = dash.data(id).data;
    if (!Array.isArray(d)) return [];
    if (!cache.has(d)) cache.set(d, d.map((r) => Object.assign({}, r, {_x: r.mes ? parse(r.mes) : null})));
    return cache.get(d);
  }
  function ok(el, ids) {
    for (const id of ids) {
      const s = dash.data(id);
      if (s.status !== 'ok') {
        el.replaceChildren();
        if (s.status === 'loading') { el.classList.add('dash-skeleton'); }
        else {
          el.classList.remove('dash-skeleton');
          if (s.status === 'error' || s.status === 'missing') { const p = document.createElement('div'); p.className = 'pf-fail'; p.textContent = 'Falha ao carregar'; el.append(p); }
        }
        return false;
      }
    }
    el.classList.remove('dash-skeleton');
    return true;
  }
  function where(el) {
    const w = el.getAttribute('data-where'); const o = {};
    if (w) w.split('&').forEach((p) => { const i = p.indexOf('='); o[decodeURIComponent(p.slice(0, i))] = decodeURIComponent(p.slice(i + 1)); });
    return o;
  }
  function fillValue(el) {
    const s = dash.data(el.dataset.source);
    if (s.status !== 'ok' || !Array.isArray(s.data)) { el.textContent = '—'; return; }
    const w = where(el);
    const r = s.data.find((x) => Object.keys(w).every((k) => String(x[k]) === w[k]));
    const v = r ? r[el.dataset.field] : null;
    if (v == null) { el.textContent = '—'; return; }
    el.textContent = (fmt[el.dataset.fmt] || fmt.f1)(v);
    if (el.dataset.good) {
      const good = el.dataset.good === 'up' ? v > 0 : v < 0;
      el.classList.toggle('up', v !== 0 && good); el.classList.toggle('down', v !== 0 && !good);
    }
  }
  function enter(el, svg) {
    if (!st.seen.has(el.id)) { st.seen.add(el.id); svg.classed('pf-enter', true); }
  }
  function svgFor(el, W, H, label) {
    const svg = d3.select(el).append('svg').attr('width', '100%').attr('height', H).attr('viewBox', `0 0 ${W} ${H}`)
      .attr('role', 'img').attr('aria-label', label).style('display', 'block').style('overflow', 'visible');
    enter(el, svg);
    return svg;
  }
  function measure(svg, texts) {
    const g = svg.append('g').attr('class', 'pf-axis');
    const w = d3.max(texts, (t) => g.append('text').text(t).node().getComputedTextLength()) || 0;
    g.remove();
    return w;
  }
  function makeTip(el) {
    const tip = document.createElement('div'); tip.className = 'pf-tip'; tip.hidden = true; el.append(tip);
    return {
      show(x, y, W, title, lines) {
        tip.replaceChildren();
        const h = document.createElement('div'); h.className = 'pf-tip-h'; h.textContent = title; tip.append(h);
        lines.forEach(([lab, val, c]) => {
          if (val == null) return;
          const r = document.createElement('div'); r.className = 'pf-tip-r';
          const sw = document.createElement('span'); sw.className = 'pf-tip-sw'; if (c) sw.style.background = c;
          const l = document.createElement('span'); l.textContent = lab;
          const b = document.createElement('b'); b.textContent = val;
          r.append(sw, l, b); tip.append(r);
        });
        tip.hidden = false;
        const tw = tip.offsetWidth;
        let left = x + 14; if (left + tw > W) left = x - tw - 14;
        tip.style.left = Math.max(0, left) + 'px'; tip.style.top = Math.max(0, y) + 'px';
      },
      hide() { tip.hidden = true; }
    };
  }
  // Gráfico de linhas no tempo, com faixa opcional e dica ao passar o dedo/mouse
  function tchart(el, o) {
    el.replaceChildren();
    const W = Math.max(260, el.clientWidth);
    const H = o.h || Math.round(Math.max(240, Math.min(370, W * 0.5)));
    const R = o.rows;
    if (!R.length) return;
    const vals = [];
    R.forEach((r) => {
      o.series.forEach((s) => { if (r[s.k] != null) vals.push(r[s.k]); });
      if (o.band && r[o.band.lo] != null) vals.push(r[o.band.lo], r[o.band.hi]);
    });
    let [mn, mx] = d3.extent(vals); const pad = (mx - mn) * 0.08 || 1;
    const ys = d3.scaleLinear().domain([o.zero ? 0 : mn - pad, mx + pad]).nice();
    const xs = d3.scaleUtc().domain(d3.extent(R, (r) => r._x));
    const svg = svgFor(el, W, H, o.aria);
    const yt = ys.ticks(H < 280 ? 4 : 5);
    const m = {t: 14, r: o.endLabel ? 46 : 12, b: 26, l: Math.ceil(measure(svg, yt.map(o.yfmt))) + 10};
    xs.range([m.l, W - m.r]); ys.range([H - m.b, m.t]);
    svg.append('g').attr('class', 'pf-gl').selectAll('line').data(yt).join('line').attr('x1', m.l).attr('x2', W - m.r).attr('y1', ys).attr('y2', ys);
    svg.append('g').attr('class', 'pf-axis').selectAll('text').data(yt).join('text').attr('x', m.l - 8).attr('y', ys).attr('dy', '0.32em').attr('text-anchor', 'end').text(o.yfmt);
    const xt = xs.ticks(Math.max(2, Math.floor((W - m.l - m.r) / 78)));
    svg.append('g').attr('class', 'pf-axis').selectAll('text').data(xt).join('text').attr('x', xs).attr('y', H - 6).attr('text-anchor', 'middle').text(mShort);
    if (o.vline) {
      const xv = xs(o.vline);
      svg.append('line').attr('class', 'pf-ref').attr('x1', xv).attr('x2', xv).attr('y1', m.t).attr('y2', H - m.b);
      const lab = svg.append('text').attr('class', 'pf-reflab').attr('y', m.t + 2).attr('dy', '0.7em').text('previsão →');
      const lw = lab.node().getComputedTextLength();
      lab.attr('x', xv + 5 + lw > W ? xv - lw - 5 : xv + 5);
    }
    if (o.band) {
      const br = R.filter((r) => r[o.band.lo] != null && r[o.band.hi] != null);
      svg.append('path').datum(br).style('fill', o.band.color).style('opacity', 0.16)
        .attr('d', d3.area().x((r) => xs(r._x)).y0((r) => ys(r[o.band.lo])).y1((r) => ys(r[o.band.hi])));
    }
    o.series.forEach((s) => {
      const sr = R.filter((r) => r[s.k] != null);
      svg.append('path').datum(sr).attr('fill', 'none').style('stroke', s.color).attr('stroke-width', s.w || 2)
        .attr('stroke-dasharray', s.dash || null).attr('stroke-linejoin', 'round').attr('stroke-linecap', 'round')
        .attr('d', d3.line().x((r) => xs(r._x)).y((r) => ys(r[s.k])));
    });
    if (o.endLabel) {
      const s = o.series.find((z) => z.k === o.endLabel);
      const last = R.filter((r) => r[o.endLabel] != null).slice(-1)[0];
      if (s && last) {
        svg.append('circle').attr('class', 'pf-dot').attr('r', 4).attr('cx', xs(last._x)).attr('cy', ys(last[o.endLabel])).style('fill', s.color);
        svg.append('text').attr('class', 'pf-val').attr('x', xs(last._x) + 7).attr('y', ys(last[o.endLabel])).attr('dy', '0.32em').text(o.yfmt(last[o.endLabel]));
      }
    }
    const g = svg.append('g').style('display', 'none').attr('pointer-events', 'none');
    const vl = g.append('line').attr('class', 'pf-cross').attr('y1', m.t).attr('y2', H - m.b);
    const dots = o.series.map((s) => g.append('circle').attr('class', 'pf-dot').attr('r', 4).style('fill', s.color));
    const tip = makeTip(el);
    const bis = d3.bisector((r) => r._x).center;
    const move = (ev) => {
      const [px] = d3.pointer(ev, svg.node());
      const r = R[bis(R, xs.invert(px))]; if (!r) return;
      const x = xs(r._x);
      g.style('display', null); vl.attr('x1', x).attr('x2', x);
      o.series.forEach((s, j) => dots[j].style('display', r[s.k] == null ? 'none' : null).attr('cx', x).attr('cy', r[s.k] == null ? 0 : ys(r[s.k])));
      tip.show(x, m.t, W, mLong(r._x), o.tip(r));
    };
    svg.append('rect').attr('x', m.l).attr('y', 0).attr('width', Math.max(0, W - m.l - m.r)).attr('height', H - m.b)
      .attr('fill', 'transparent').style('touch-action', 'pan-y')
      .on('pointermove', move).on('pointerdown', move).on('pointerleave', () => { g.style('display', 'none'); tip.hide(); });
  }
  return {fmt, parse, mShort, mLong, st, col, enc, nome, rows, ok, fillValue, svgFor, measure, makeTip, tchart};
})();

// Valores soltos (números das frases e dos cartões)
dash.draw('kv', (el) => PF.fillValue(el));
dash.draw('ukv', (el) => {
  const s = dash.data('unidades_resumo');
  if (s.status === 'ok' && s.data.length) {
    if (!s.data.some((r) => r.unidade === PF.st.unit)) PF.st.unit = s.data[0].unidade;
    el.setAttribute('data-where', 'unidade=' + PF.enc(PF.st.unit));
  }
  PF.fillValue(el);
});
dash.draw('ekv', (el) => {
  const s = dash.data('empresas_resumo');
  if (s.status === 'ok' && s.data.length) {
    if (!s.data.some((r) => r.empresa === PF.st.emp)) PF.st.emp = s.data[0].empresa;
    el.setAttribute('data-where', 'empresa=' + PF.enc(PF.st.emp));
  }
  PF.fillValue(el);
});
// Cores das legendas e dos cartões
document.querySelectorAll('.pf-sw[data-c]').forEach((e) => {
  const c = PF.col(+e.dataset.c);
  e.style.background = c; e.style.setProperty('--pf-c', c);
});
document.querySelectorAll('.pf-kpi[data-c]').forEach((e) => e.style.setProperty('--pf-accent', PF.col(+e.dataset.c)));

// Abas
(() => {
  const tabs = document.querySelectorAll('.pf-tab');
  function abrir(id) {
    document.querySelectorAll('.pf-sec').forEach((s) => { s.hidden = s.id !== id; });
    tabs.forEach((t) => { const on = t.dataset.tab === id; t.classList.toggle('on', on); t.setAttribute('aria-selected', on ? 'true' : 'false'); });
    dash.setLink(id);
  }
  PF.abrir = abrir;
  tabs.forEach((t) => t.addEventListener('click', () => abrir(t.dataset.tab)));
  const h = (location.hash || '').slice(1);
  if ([...tabs].some((t) => t.dataset.tab === h)) abrir(h);
})();

// Botões de período do gráfico principal
document.querySelectorAll('#periodo button').forEach((b) => b.addEventListener('click', () => {
  PF.st.range = b.dataset.range;
  document.querySelectorAll('#periodo button').forEach((x) => x.classList.toggle('on', x === b));
  dash.draw('chBrasil');
}));

// Ordenação das tabelas
document.querySelectorAll('.pf-table[data-sort]').forEach((tb) => {
  const key = tb.dataset.sort;
  tb.querySelectorAll('th[data-field]').forEach((th) => th.addEventListener('click', () => {
    const s = PF.st.sort[key];
    if (s.k === th.dataset.field) s.d = -s.d; else { s.k = th.dataset.field; s.d = (th.classList.contains('txt') ? 1 : -1); }
    tb.querySelectorAll('th').forEach((x) => { x.classList.remove('asc', 'desc'); });
    th.classList.add(s.d > 0 ? 'asc' : 'desc');
    dash.draw(key === 'unit' ? 'tbU' : 'tbE');
  }));
});
PF.selUnit = (u) => { PF.st.unit = u; ['selU', 'ukv', 'uakv', 'chU', 'tbU'].forEach((n) => dash.draw(n)); };
PF.selEmp = (e) => { PF.st.emp = e; ['selE', 'ekv', 'dkv', 'chE', 'chDep', 'tbSoc', 'tbE'].forEach((n) => dash.draw(n)); };

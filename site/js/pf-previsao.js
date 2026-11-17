// Aba Previsão: previsto × realizado, próximos meses e cenário do usuário, por empresa
(() => {
  const r0 = (x) => Math.round(x), r1 = (x) => Math.round(x * 10) / 10, r2 = (x) => Math.round(x * 100) / 100, r3 = (x) => Math.round(x * 1000) / 1000;
  const sig = (f) => (v) => (v > 0 ? '+' : v < 0 ? '−' : '') + f(Math.abs(v));
  PF.fmt.s0 = sig(PF.fmt.f0); PF.fmt.s1 = sig(PF.fmt.f1);
  PF.fmt.p0 = (v) => sig(PF.fmt.f0)(v) + '%';
  PF.fmt.pc = (v) => PF.fmt.f1(v) + '%';
  PF.fmt.mes = (v) => PF.mLong(PF.parse(v));
  PF.fmt.nome = PF.nome;
  PF.st.sort.sim = {k: 'd_receita', d: 1};
  // Referências fixas dos riscos
  PF.REF = {brent: 10, cambio: 0.5, atraso: 6};
  const CENTRAL = {brent_pct: 0, cambio_pct: 0, vol_pct: 0, atraso: 0, campo: '', campo_pct: 0};
  PF.P = () => {
    const p = dash.params() || {}, n = (k) => Number(p[k]) || 0, h = Number(p.h);
    const emp = p.emp || 'Total', pw = dash.data('pesos');
    const cf = p.cf && pw.status === 'ok' && pw.data.some((r) => r.empresa === emp && r.unidade === p.cf) ? p.cf : '';
    return {emp, cf, h: [1, 3, 6, 12].includes(h) ? h : 6, m: MET[p.m] ? p.m : 'producao', brent_pct: n('brent_pct'), cambio_pct: n('cambio_pct'),
      vol_pct: n('vol_pct'), atraso: n('atraso'), campo: p.campo || '', campo_pct: n('campo_pct')};
  };
  // O que o gráfico principal mostra: campos de cada dataset e formato
  const MET = {
    producao: {nome: 'Produção', u: 'mil bbl/d', real: 'real', prev: 'previsto', lo: 'p10', p50: 'p50', hi: 'p90', s: 'prod_s', c: 'prod_c',
      sub: 'Mil barris por dia. À esquerda da linha vertical, o que já aconteceu e o que o modelo tinha previsto; à direita, a previsão atual.'},
    receita: {nome: 'Receita bruta', u: 'R$ bi', real: 'receita_real', prev: 'receita_prev', lo: 'receita_p10', p50: 'receita_p50', hi: 'receita_p90', s: 'receita_s', c: 'receita_c',
      sub: 'R$ bilhões por mês, da parte da empresa. O modelo prevê a produção; o preço vem do cenário de Brent e câmbio. Por isso, no passado, o previsto é o volume previsto ao preço que de fato ocorreu.'},
    royalties: {nome: 'Royalties', u: 'R$ bi', real: 'royalties_real', prev: 'royalties_prev', lo: 'royalties_p10', p50: 'royalties_p50', hi: 'royalties_p90', s: 'royalties_s', c: 'royalties_c',
      sub: 'R$ bilhões por mês pagos ao governo sobre a parte da empresa. No passado, o previsto é o volume previsto ao preço que de fato ocorreu.'}
  };
  PF.MET = MET;
  PF.fmt.mv = (v) => (PF.P().m === 'producao' ? PF.fmt.f0 : PF.fmt.f2)(v);
  // Filtro de campo: a empresa inteira ou só a parte dela num campo
  const pesosF = (pesos, c) => c.cf ? pesos.filter((r) => r.unidade === c.cf) : pesos;
  const pesoCampo = (pesos, c) => { const r = pesos.find((x) => x.empresa === c.emp && x.unidade === c.cf); return r ? r.peso : 0; };
  PF.pesoCampo = pesoCampo;
  const ativo = (c) => c.brent_pct || c.cambio_pct || c.vol_pct || c.atraso || (c.campo && c.campo_pct);
  const rotulo = (e) => e === 'Total' ? 'Todas as empresas' : e;

  // Cenário de uma empresa: soma, campo a campo, da parte da empresa em cada campo.
  // Preço (Brent × câmbio) age em proporção sobre receita e royalties; o volume dos campos atuais sobe ou desce
  // no percentual escolhido; as plataformas novas são deslocadas no tempo; o ajuste de um campo multiplica o campo inteiro.
  PF.cenario = (sim, pesos, emp, c) => {
    const w = new Map(pesos.filter((r) => r.empresa === emp).map((r) => [r.unidade, r.peso]));
    const fP = (1 + c.brent_pct / 100) * (1 + c.cambio_pct / 100), fV = 1 + c.vol_pct / 100;
    const out = new Map();
    d3.groups(sim.filter((r) => w.has(r.unidade)), (r) => r.unidade).forEach(([u, L]) => {
      const R = L.slice().sort((a, b) => (a.mes < b.mes ? -1 : 1)), peso = w.get(u), fA = u === c.campo ? 1 + c.campo_pct / 100 : 1;
      R.forEach((r, i) => {
        const js = i - c.atraso >= 0 ? R[i - c.atraso].proj : 0, rb = r.prod > 0 ? r.receita / r.prod : 0, yb = r.prod > 0 ? r.royalties / r.prod : 0;
        const o = out.get(r.mes) || {mes: r.mes, prod_c: 0, prod_s: 0, receita_c: 0, receita_s: 0, royalties_c: 0, royalties_s: 0};
        o.prod_c += peso * r.prod; o.receita_c += peso * r.receita; o.royalties_c += peso * r.royalties;
        o.prod_s += peso * ((r.prod - r.proj) * fV + js) * fA;
        o.receita_s += peso * ((r.receita - r.proj * rb) * fV + js * rb) * fA * fP;
        o.royalties_s += peso * ((r.royalties - r.proj * yb) * fV + js * yb) * fA * fP;
        out.set(r.mes, o);
      });
    });
    return [...out.values()].sort((a, b) => (a.mes < b.mes ? -1 : 1));
  };
  const soma12 = (M) => {
    const a = M.slice(0, 12), s = (k) => d3.sum(a, (r) => r[k]), m = (k) => d3.mean(a, (r) => r[k]);
    return {prod_c: m('prod_c'), prod_s: m('prod_s'), receita_c: s('receita_c'), receita_s: s('receita_s'), royalties_c: s('royalties_c'), royalties_s: s('royalties_s')};
  };
  const brentBase = (mercado) => d3.mean(mercado.slice(0, 12), (r) => r.brent_base);
  const cambioBase = (mercado) => d3.mean(mercado.slice(0, 12), (r) => r.ptax_p50);

  dash.calc('premissas', {
    inputs: ['mercado'], title: 'Premissas do seu cenário',
    description: 'Brent e câmbio médios de 12 meses depois do ajuste escolhido, e os demais ajustes.',
    fn: (mercado) => {
      const c = PF.P();
      return [{k: 'brent', valor: r1(brentBase(mercado) * (1 + c.brent_pct / 100))}, {k: 'cambio', valor: r2(cambioBase(mercado) * (1 + c.cambio_pct / 100))},
        {k: 'vol', valor: c.vol_pct}, {k: 'atraso', valor: c.atraso}, {k: 'campo', valor: c.campo_pct}];
    }
  });
  dash.calc('cenario_mes', {
    inputs: ['sim_unidades', 'pesos'], title: 'Seu cenário, mês a mês',
    description: 'Produção (mil bbl/d), receita e royalties (R$ bi) da empresa escolhida: previsão do modelo e seu cenário.',
    fn: (sim, pesos) => { const c = PF.P(); return PF.cenario(sim, pesosF(pesos, c), c.emp, c).map((r) => ({mes: r.mes, prod_c: r1(r.prod_c), prod_s: r1(r.prod_s), receita_c: r3(r.receita_c), receita_s: r3(r.receita_s), royalties_c: r3(r.royalties_c), royalties_s: r3(r.royalties_s)})); }
  });
  dash.calc('cenario12', {
    inputs: ['sim_unidades', 'pesos'], title: 'Seu cenário, próximos 12 meses',
    description: 'Por empresa: produção média (mil bbl/d), receita e royalties (R$ bi) de 12 meses, na previsão do modelo e no seu cenário.',
    fn: (sim, pesos) => {
      const c = PF.P();
      return [...new Set(pesosF(pesos, c).map((r) => r.empresa))].map((empresa) => {
        const s = soma12(PF.cenario(sim, pesosF(pesos, c), empresa, c));
        return {empresa, prod_c: r0(s.prod_c), prod_s: r0(s.prod_s), d_prod: r0(s.prod_s - s.prod_c),
          receita_c: r1(s.receita_c), receita_s: r1(s.receita_s), d_receita: r1(s.receita_s - s.receita_c), var_pct: r1((s.receita_s / s.receita_c - 1) * 100),
          royalties_c: r1(s.royalties_c), royalties_s: r1(s.royalties_s), d_royalties: r1(s.royalties_s - s.royalties_c)};
      }).filter((r) => r.prod_c > 0 && r.receita_c > 0);
    }
  });
  dash.calc('riscos', {
    inputs: ['sim_unidades', 'pesos', 'mercado', 'central', 'central_campos'], title: 'Sensibilidades da empresa escolhida',
    description: 'Efeito em 12 meses de cada risco isolado sobre a previsão do modelo: produção em mil bbl/d, receita em R$ bi.',
    fn: (sim, pesos, mercado, central, central_campos) => {
      const k = PF.P(), emp = k.emp, pf = pesosF(pesos, k), base = soma12(PF.cenario(sim, pf, emp, CENTRAL));
      const cc = (k.cf ? central_campos.filter((r) => r.unidade === k.cf) : central.filter((r) => r.empresa === emp)).slice(0, 12);
      const p10 = d3.mean(cc, (r) => r.p10) / d3.mean(cc, (r) => r.p50) - 1;
      const efeito = (risco, c) => {
        const s = soma12(PF.cenario(sim, pf, emp, Object.assign({}, CENTRAL, c)));
        return {risco, producao: r0(s.prod_s - base.prod_c), receita: r1(s.receita_s - base.receita_c)};
      };
      return [efeito('brent', {brent_pct: -PF.REF.brent / brentBase(mercado) * 100}), efeito('cambio', {cambio_pct: -PF.REF.cambio / cambioBase(mercado) * 100}),
        efeito('atraso', {atraso: PF.REF.atraso}), efeito('p10', {vol_pct: p10 * 100})];
    }
  });
  dash.calc('acerto', {
    inputs: ['historico', 'hist_campos', 'pesos'], title: 'Acerto das previsões passadas',
    description: 'Para a empresa escolhida e cada antecedência: último mês com dado e erro médio dos últimos 12 meses, do modelo e de quem repete o último mês.',
    fn: (historico, hist_campos, pesos) => {
      const c = PF.P(), M = MET[c.m], emp = c.emp, w = c.cf ? pesoCampo(pesos, c) : 1;
      const esc = (r) => Object.assign({}, r, {previsto: r.previsto * w, ingenuo: r.ingenuo * w, real: r.real * w, [M.real]: r[M.real] * w, [M.prev]: r[M.prev] * w});
      const hist = c.cf ? hist_campos.filter((r) => r.unidade === c.cf).map((r) => Object.assign(esc(r), {empresa: emp})) : historico;
      // Para receita e royalties, "repetir o último mês" é o volume repetido ao preço realizado
      const val = (r) => ({real: r[M.real], prev: r[M.prev], ing: r.ingenuo * r[M.real] / r.real});
      return d3.groups(hist.filter((r) => r.empresa === emp && r[M.real] > 0), (r) => r.h).map(([h, L]) => {
        const R = L.slice().sort((a, b) => (a.mes < b.mes ? -1 : 1)).map(val), u = R[R.length - 1], a = R.slice(-12), um = L.reduce((x, y) => (x.mes > y.mes ? x : y)).mes;
        const erro = (k) => r1(d3.mean(a, (r) => Math.abs(r[k] - r.real) / r.real) * 100);
        return {h, mes: um, previsto: u.prev, real: u.real, desvio_pct: r1((u.real / u.prev - 1) * 100),
          erro12: erro('prev'), erro12_ingenuo: erro('ing'), vies12: r1(d3.mean(a, (r) => (r.prev - r.real) / r.real) * 100)};
      });
    }
  });

  dash.calc('acerto_campos', {
    inputs: ['hist_campos'], title: 'Acerto das previsões por campo',
    description: 'Para cada campo e antecedência: erro médio dos últimos 12 meses do modelo e de quem repete o último mês, em %.',
    fn: (hist_campos) => d3.flatRollup(hist_campos.filter((r) => r.real > 0), (L) => {
      const a = L.slice().sort((x, y) => (x.mes < y.mes ? -1 : 1)).slice(-12);
      return {erro12: r1(d3.mean(a, (r) => Math.abs(r.previsto - r.real) / r.real) * 100), erro12_ing: r1(d3.mean(a, (r) => Math.abs(r.ingenuo - r.real) / r.real) * 100)};
    }, (r) => r.unidade, (r) => r.h).map(([unidade, h, v]) => Object.assign({unidade, h}, v))
  });

  // ---- Desenhos
  const pv = (el, field, where) => { el.setAttribute('data-where', where); PF.fillValue(el); };
  dash.draw('akv', (el) => pv(el, null, 'h=' + PF.P().h));
  dash.draw('uakv', (el) => {
    const s = dash.data('unidades_resumo'), u = PF.st.unit || (s.status === 'ok' && s.data.length ? s.data[0].unidade : '');
    pv(el, null, 'unidade=' + PF.enc(u) + '&h=' + PF.P().h);
  });
  dash.draw('hNome', (el) => { const h = PF.P().h; el.textContent = h + (h === 1 ? ' mês' : ' meses'); });
  dash.draw('ckv', (el) => pv(el, null, 'empresa=' + PF.enc(PF.P().emp)));
  dash.draw('cst', (el) => { const v = PF.REF[el.dataset.k]; el.textContent = Number.isInteger(v) ? String(v) : PF.fmt.f2(v); });
  dash.draw('empNome', (el) => {
    const c = PF.P(), e = c.emp === 'Total' ? 'todas as empresas' : c.emp;
    el.textContent = !c.cf ? e : c.emp === 'Total' ? PF.nome(c.cf) + ' (campo inteiro)' : c.emp + ' em ' + PF.nome(c.cf);
  });
  dash.draw('selCf', (sel) => {
    const p = dash.data('pesos'), s = dash.data('sim_unidades'), c = PF.P();
    let L = [];
    if (p.status === 'ok' && s.status === 'ok') {
      const prod = d3.rollup(s.data, (v) => d3.mean(v.slice(0, 12), (r) => r.prod), (r) => r.unidade);
      L = p.data.filter((r) => r.empresa === c.emp).map((r) => [r.unidade, r.peso * (prod.get(r.unidade) || 0)]).filter((x) => x[1] >= 1).sort((a, b) => b[1] - a[1]);
    }
    sel.replaceChildren(new Option('Todos os campos', ''), ...L.map(([u]) => new Option(PF.nome(u), u)));
    sel.value = L.some(([u]) => u === c.cf) ? c.cf : '';
    sel.onchange = () => dash.setParams({cf: sel.value});
  });
  dash.draw('metNome', (el) => { el.textContent = MET[PF.P().m].nome; });
  dash.draw('metSub', (el) => { el.textContent = MET[PF.P().m].sub; });
  dash.draw('unidM', (el) => { el.textContent = MET[PF.P().m].u; });
  dash.draw('cenNota', (el) => {
    const c = PF.P(); el.hidden = false; if (!ativo(c)) { el.textContent = ''; return; }
    const volume = c.vol_pct || c.atraso || (c.campo && c.campo_pct);
    el.textContent = (volume || c.m !== 'producao')
      ? 'A linha verde é o seu cenário. Ele muda só a previsão daqui para a frente: as previsões já feitas continuam como estavam, para a comparação com o realizado ficar honesta.'
      : 'Brent e câmbio mudam quanto vale cada barril, não quantos barris são produzidos. Por isso a produção não se mexe: o efeito aparece em Receita e Royalties, no seletor acima do gráfico.';
  });
  dash.draw('selEmpP', (sel) => {
    const s = dash.data('pesos');
    const nomes = s.status === 'ok' ? [...new Set(s.data.map((r) => r.empresa))] : [];
    sel.replaceChildren(...nomes.map((e) => new Option(rotulo(e), e)));
    sel.value = PF.P().emp;
    sel.onchange = () => dash.setParams({emp: sel.value, cf: '', campo: '', campo_pct: 0});
  });
  dash.draw('selCampo', (sel) => {
    const p = dash.data('pesos'), s = dash.data('sim_unidades'), c = PF.P();
    let L = [];
    if (p.status === 'ok' && s.status === 'ok') {
      const prod = d3.rollup(s.data, (v) => d3.mean(v.slice(0, 12), (r) => r.prod), (r) => r.unidade);
      L = p.data.filter((r) => r.empresa === c.emp).map((r) => [r.unidade, r.peso * (prod.get(r.unidade) || 0)]).filter((x) => x[1] >= 1).sort((a, b) => b[1] - a[1]);
    }
    sel.replaceChildren(new Option('Nenhum campo', ''), ...L.map(([u]) => new Option(PF.nome(u), u)));
    sel.value = L.some(([u]) => u === c.campo) ? c.campo : '';
    sel.onchange = () => dash.setParams({campo: sel.value, campo_pct: sel.value ? c.campo_pct : 0});
  });

  // Gráfico principal: realizado, previsões feitas antes, previsão atual com faixa e seu cenário
  dash.draw('chPrev', (el) => {
    if (!PF.ok(el, ['historico', 'central', 'cenario_mes', 'hist_campos', 'central_campos', 'pesos'])) return;
    const c = PF.P(), M = MET[c.m], c0 = PF.col(0), c1 = PF.col(1), c2 = PF.col(2), din = c.m !== 'producao';
    const f = din ? PF.fmt.f2 : PF.fmt.f0, fy = din ? PF.fmt.f1 : PF.fmt.f0, fu = (v) => din ? 'R$ ' + f(v) + ' bi' : f(v);
    const w = c.cf ? pesoCampo(dash.data('pesos').data, c) : 1;
    const HP = c.cf ? dash.data('hist_campos').data.filter((r) => r.unidade === c.cf) : dash.data('historico').data.filter((r) => r.empresa === c.emp);
    const past = HP.filter((r) => r.h === c.h && r[M.real] > 0).map((r) => ({mes: r.mes, real: r[M.real] * w, prev_passada: r[M.prev] * w}));
    const cen = new Map(dash.data('cenario_mes').data.map((r) => [r.mes, r]));
    const CF = c.cf ? dash.data('central_campos').data.filter((r) => r.unidade === c.cf) : dash.data('central').data.filter((r) => r.empresa === c.emp);
    const fut = CF.map((r) => ({mes: r.mes, p10: r[M.lo] * w, p50: r[M.p50] * w, p90: r[M.hi] * w,
      cenario: ativo(c) && cen.has(r.mes) ? cen.get(r.mes)[M.s] : null}));
    const ult = past[past.length - 1];
    if (ult) Object.assign(ult, {p10: ult.real, p50: ult.real, p90: ult.real, cenario: ativo(c) ? ult.real : null});
    const R = past.concat(fut).map((r) => Object.assign(r, {_x: PF.parse(r.mes)}));
    const series = [{k: 'prev_passada', color: c1, w: 1.6, dash: '2 3'}, {k: 'real', color: c0, w: 2.2}, {k: 'p50', color: c1, w: 2.2, dash: '6 4'}];
    if (ativo(c)) series.push({k: 'cenario', color: c2, w: 2.4});
    PF.tchart(el, {
      rows: R, yfmt: fy, zero: din, vline: ult ? PF.parse(ult.mes) : null, endLabel: ativo(c) ? 'cenario' : 'p50', band: {lo: 'p10', hi: 'p90', color: c1},
      aria: M.nome + ' de ' + rotulo(c.emp) + ': realizado nos últimos 36 meses, o que o modelo previu ' + c.h + ' meses antes, a previsão dos próximos 18 meses com faixa e o cenário escolhido',
      series,
      tip: (r) => {
        if (r.real != null && r.mes !== (ult && ult.mes)) return [['Realizado', fu(r.real), c0], ['Previsto ' + c.h + (c.h === 1 ? ' mês' : ' meses') + ' antes', r.prev_passada == null ? null : fu(r.prev_passada) + ' (' + PF.fmt.pct((r.prev_passada / r.real - 1) * 100) + ')', c1]];
        if (r.mes === (ult && ult.mes)) return [['Realizado (último mês)', fu(r.real), c0]];
        return [['Previsão do modelo', fu(r.p50), c1], ['Faixa P10–P90', f(r.p10) + '–' + f(r.p90), null], ['Seu cenário', r.cenario == null ? null : fu(r.cenario), c2]];
      }
    });
  });
  dash.draw('tbCampos', (tb) => {
    const s = dash.data('pr_campos'), ce = dash.data('campos_empresa');
    if (s.status !== 'ok' || ce.status !== 'ok') { tb.replaceChildren(); return; }
    const c = PF.P(), meus = new Set(ce.data.filter((r) => r.empresa === c.emp).map((r) => r.unidade));
    const R = s.data.filter((r) => r.h === c.h && (c.cf ? r.unidade === c.cf : (c.emp === 'Total' || meus.has(r.unidade)))).sort((a, b) => b.real - a.real);
    const sinal = (v) => v == null ? '' : v >= 0 ? 'up' : 'down';
    tb.replaceChildren(...R.map((r) => {
      const tr = document.createElement('tr'); tr.setAttribute('data-key', PF.enc(r.unidade) + ',' + r.h);
      [[PF.nome(r.unidade), 'txt'], [PF.fmt.f1(r.previsto)], [PF.fmt.f1(r.real)], [PF.fmt.s1(r.desvio), sinal(r.desvio)],
        [r.desvio_pct == null ? '—' : PF.fmt.pct(r.desvio_pct), sinal(r.desvio_pct)], [r.erro12 == null ? '—' : PF.fmt.pc(r.erro12)]].forEach(([t, k]) => {
        const td = document.createElement('td'); td.textContent = t; if (k) td.className = k; tr.append(td);
      });
      return tr;
    }));
  });
  dash.draw('tbCen', (tb) => PF.tabela(tb, 'cenario12', 'sim',
    [['empresa', rotulo], ['receita_c', PF.fmt.f1], ['receita_s', PF.fmt.f1], ['d_receita', PF.fmt.s1], ['var_pct', PF.fmt.pct]],
    'empresa', PF.P().emp, (e) => dash.setParams({emp: e, campo: '', campo_pct: 0})));

  // ---- Controles: escutam e gravam as escolhas
  document.querySelectorAll('.pf-range[data-p]').forEach((el) => el.addEventListener('input', () => dash.setParams({[el.dataset.p]: Number(el.value)})));
  document.querySelectorAll('#antecedencia button[data-h], #antecedencia-campo button[data-h]').forEach((b) => b.addEventListener('click', () => dash.setParams({h: Number(b.dataset.h)})));
  document.querySelectorAll('#metrica button[data-m]').forEach((b) => b.addEventListener('click', () => dash.setParams({m: b.dataset.m})));
  const mais = document.getElementById('mais-detalhes');
  if (mais) mais.addEventListener('toggle', () => { if (mais.open) dash.draw('chAcc'); });
  document.querySelectorAll('.pf-btn[data-reset]').forEach((b) => b.addEventListener('click', () => dash.setParams(CENTRAL)));
  dash.onData(() => {
    const p = PF.P();
    document.querySelectorAll('.pf-range[data-p]').forEach((el) => {
      if (document.activeElement !== el) el.value = p[el.dataset.p];
      if (el.dataset.p === 'campo_pct') el.disabled = !p.campo;
    });
    document.querySelectorAll('#antecedencia button[data-h], #antecedencia-campo button[data-h]').forEach((b) => b.classList.toggle('on', Number(b.dataset.h) === p.h));
    document.querySelectorAll('#metrica button[data-m]').forEach((b) => b.classList.toggle('on', b.dataset.m === p.m));
  });
})();

// Motor mínimo do painel para a versão pública (GitHub Pages).
// Oferece a mesma interface que os scripts do painel usam: dash.data, dash.draw, dash.calc,
// dash.params, dash.setParams, dash.onData, dash.setLink e dash.colors.
// Os dados vêm de data/<id>.json, gerados todo mês pelo robô do repositório.
window.dash = (() => {
  const store = {};            // id -> {status, data}
  const draws = {};            // nome -> função de desenho
  const calcs = {};            // id -> {inputs, fn}
  const memo = new Map();      // resultados das contas, refeitos a cada desenho
  const ons = [];
  const params = {emp: 'Total', cf: '', h: 6, m: 'producao', brent_pct: 0, cambio_pct: 0, vol_pct: 0, atraso: 0, campo: '', campo_pct: 0, ent: '', lei: 0};
  let pend = false;

  function carregar(id) {
    store[id] = {status: 'loading', data: null};
    fetch('data/' + encodeURIComponent(id) + '.json', {cache: 'no-cache'})
      .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then((j) => { store[id] = {status: 'ok', data: Array.isArray(j) ? j : j.rows || []}; agendar(); })
      .catch(() => { store[id] = {status: 'missing', data: []}; agendar(); });
  }

  function data(id) {
    if (calcs[id]) {
      if (memo.has(id)) return memo.get(id);
      const c = calcs[id], ins = c.inputs.map(data);
      let out;
      if (ins.some((s) => s.status === 'loading')) out = {status: 'loading', data: null};
      else if (ins.some((s) => s.status !== 'ok')) out = {status: 'error', data: null};
      else {
        try { out = {status: 'ok', data: c.fn(...ins.map((s) => s.data))}; }
        catch (e) { console.error('conta ' + id, e); out = {status: 'error', data: null}; }
      }
      memo.set(id, out);
      return out;
    }
    if (!store[id]) carregar(id);
    return store[id];
  }

  const visivel = (el) => !el.closest('[hidden]') && !el.closest('details:not([open]) > :not(summary)');
  function rodar(nome) {
    document.querySelectorAll('[data-draw="' + nome + '"]').forEach((el) => {
      if (!visivel(el)) return;
      try { draws[nome](el); } catch (e) { console.error('desenho ' + nome, e); }
    });
  }
  function desenhar() {
    pend = false;
    memo.clear();
    ons.forEach((f) => { try { f(); } catch (e) { console.error(e); } });
    Object.keys(draws).forEach(rodar);
  }
  function agendar() {
    if (pend) return;
    pend = true;
    requestAnimationFrame(desenhar);
  }

  function draw(nome, fn) {
    if (fn) { draws[nome] = fn; agendar(); return; }
    if (draws[nome]) { memo.clear(); rodar(nome); }
  }

  // Redesenha quando a tela muda de tamanho ou quando um bloco "mais detalhes" abre
  let t;
  window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(agendar, 150); });
  document.addEventListener('toggle', agendar, true);

  return {
    colors: ['var(--c0)', 'var(--c1)', 'var(--c2)', 'var(--c3)', 'var(--c4)', 'var(--c5)'],
    data,
    draw,
    calc(id, o) { calcs[id] = o; agendar(); },
    params: () => Object.assign({}, params),
    setParams(o) { Object.assign(params, o); agendar(); },
    onData(fn) { ons.push(fn); agendar(); },
    setLink(id) { try { history.replaceState(null, '', '#' + id); } catch (e) { /* sem histórico */ } agendar(); }
  };
})();

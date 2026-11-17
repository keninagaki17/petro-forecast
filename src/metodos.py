"""Métodos de previsão baseados só no histórico de cada série (sem aprendizado global)."""
import warnings
import numpy as np

H = 18
_B = np.array([0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.3])
_DI = np.geomspace(0.001, 0.3, 30)
_BB, _DD = [a.ravel() for a in np.meshgrid(_B, _DI, indexing="ij")]


def _curvas(tau):
    t = tau[None, :]; b = _BB[:, None]; d = _DD[:, None]
    return np.where(b < 1e-6, -d * t, -(1.0 / np.maximum(b, 1e-9)) * np.log1p(b * d * t))


def arps(q, janela=36, minimo=6, desde_pico=True):
    """Ajusta Arps (grade b × Di) em log; retorna previsão para h=1..H ou None."""
    q = np.asarray(q[-janela:], float)
    q = q[~np.isnan(q)]
    if len(q) < minimo:
        return None
    ini = int(np.argmax(q)) if desde_pico else 0
    seg = q[ini:]
    ok = seg > 0
    if ok.sum() < minimo:
        return None
    tau = np.arange(len(seg), dtype=float)
    ly = np.log(seg[ok]); tt = tau[ok]
    cur = _curvas(tt)
    lqi = (ly[None, :] - cur).mean(1)
    sse = ((ly[None, :] - cur - lqi[:, None]) ** 2).sum(1)
    k = int(np.argmin(sse))
    tf = (len(seg) - 1 + np.arange(1, H + 1)).astype(float)
    b, d = _BB[k], _DD[k]
    lf = -d * tf if b < 1e-6 else -(1 / b) * np.log1p(b * d * tf)
    return np.exp(lqi[k] + lf)


def arps_pocos(matriz, t, janela=24):
    """Soma das curvas de Arps de cada poço ativo na origem t.
    matriz: (n_pocos, n_meses) de bbl/dia com NaN na lacuna."""
    tot = np.zeros(H)
    if matriz is None or matriz.shape[0] == 0:
        return tot
    ativos = np.where(np.nan_to_num(matriz[:, t]) > 0)[0]
    for i in ativos:
        s = matriz[i, max(0, t - janela + 1): t + 1]
        f = arps(s, janela=janela, minimo=4, desde_pico=True)
        if f is None:
            f = np.full(H, np.nanmean(s[-3:]))
        tot += f
    return tot


def ets_amortecido(q, janela=48):
    """Holt com tendência amortecida no log da produção."""
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    y = np.asarray(q[-janela:], float)
    y = y[~np.isnan(y)]
    if len(y) < 12 or (y <= 0).mean() > 0.2:
        return None
    ly = np.log(np.maximum(y, 1.0))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            m = ExponentialSmoothing(ly, trend="add", damped_trend=True,
                                     initialization_method="estimated").fit(optimized=True)
            return np.exp(m.forecast(H))
        except Exception:
            return None

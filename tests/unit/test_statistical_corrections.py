"""Correcciones estadísticas de la fase F con datos sintéticos de resultado conocido y
contraste con implementaciones externas (jsharpe y nullius) cuando están instaladas."""

from __future__ import annotations

import math

import numpy as np
import pytest

from aurum.validation import statistical_corrections as SC


def test_moments_of_known_series():
    r = np.array([0.01, -0.01, 0.02, -0.02, 0.0])
    sr, skew, kurt, t = SC.moments(r)
    assert t == 5
    assert sr == pytest.approx(0.0)
    assert skew == pytest.approx(0.0)
    assert kurt == pytest.approx(np.mean(((r - r.mean()) / r.std()) ** 4))


def test_psr_gaussian_closed_form():
    # PSR(SR=0.1, SR0=0, T=101) con retornos normales = Phi(0.1 * 10 / sqrt(1 + 0.1^2 / 2))
    expected = 0.5 * (1 + math.erf(1.0 / math.sqrt(1 + 0.005) / math.sqrt(2)))
    assert SC.psr(0.1, 0.0, 101) == pytest.approx(expected, rel=1e-12)
    assert SC.psr(0.0, 0.0, 500) == pytest.approx(0.5)


def test_pvalue_detects_skill_and_noise():
    rng = np.random.default_rng(1)
    noise = rng.normal(0, 0.01, 2500)
    skill = rng.normal(0.002, 0.01, 2500)       # Sharpe diario 0,2: inequívoco con 2 500 días
    assert SC.sharpe_pvalue(skill) < 1e-10
    assert SC.sharpe_pvalue(noise) > 0.01
    assert SC.sharpe_pvalue(-skill) > 0.999


def test_benjamini_hochberg_hand_example():
    p = np.array([0.01, 0.04, 0.03, 0.005, 0.20])
    # ordenados: 0.005, 0.01, 0.03, 0.04, 0.20 -> p*m/i = 0.025, 0.025, 0.05, 0.05, 0.20
    q = SC.benjamini_hochberg(p)
    assert q == pytest.approx([0.025, 0.05, 0.05, 0.025, 0.20])
    assert SC.benjamini_hochberg(np.array([np.nan, 0.5]))[0] == 1.0


def test_bh_controls_fdr_under_global_null():
    rng = np.random.default_rng(2)
    discoveries = [(SC.benjamini_hochberg(rng.uniform(size=200)) < 0.10).any() for _ in range(300)]
    # Con todas las nulas ciertas, P(alguna falsa) <= q (FDR = FWER en ese caso)
    assert np.mean(discoveries) <= 0.14


def test_expected_max_sharpe_grows_with_trials():
    assert SC.expected_max_sharpe(1, 0.01) == 0.0
    vals = [SC.expected_max_sharpe(n, 0.01) for n in (10, 100, 1000)]
    assert vals[0] < vals[1] < vals[2]
    # E[max] de 100 normales estándar ~ 2,51 (aproximación de Bailey y López de Prado)
    assert SC.expected_max_sharpe(100, 1.0) == pytest.approx(2.53, abs=0.03)


def test_dsr_penalizes_number_of_trials():
    rng = np.random.default_rng(3)
    r = rng.normal(0.0006, 0.01, 2500)         # Sharpe diario ~0,06
    one = SC.deflated_sharpe(r, 1, 0.0)["dsr"]
    many = SC.deflated_sharpe(r, 500, 0.02 ** 2)["dsr"]
    assert many < one


def test_pbo_noise_near_half_and_skill_near_zero():
    rng = np.random.default_rng(4)
    # Sin habilidad, la mejor variante dentro de muestra cae en la mitad mala fuera de
    # muestra al menos la mitad de las veces (CSCV la empuja algo por encima de 0,5, porque
    # dentro y fuera de muestra son complementarias).
    pbos = [SC.pbo_cscv(rng.normal(0, 0.01, (1600, 20)), 8)["pbo"] for _ in range(10)]
    assert np.mean(pbos) >= 0.45
    noise = rng.normal(0, 0.01, (1600, 20))
    skill = noise.copy()
    skill[:, 7] += 0.004                         # una variante con ventaja persistente
    out = SC.pbo_cscv(skill, 8)
    assert out["pbo"] < 0.05
    assert out["n_combos"] == math.comb(8, 4)


def test_pbo_rejects_bad_shapes():
    with pytest.raises(ValueError):
        SC.pbo_cscv(np.zeros((10, 1)), 4)
    with pytest.raises(ValueError):
        SC.pbo_cscv(np.zeros((10, 3)), 3)


# --- contraste con implementaciones externas --------------------------------------------

def test_pbo_matches_nullius():
    nl = pytest.importorskip("nullius")
    rng = np.random.default_rng(5)
    m = rng.normal(0, 0.01, (800, 12))
    m[:, 3] += 0.001
    ours = SC.pbo_cscv(m, 8)
    theirs = nl.probability_of_backtest_overfitting(m, n_splits=8, max_combos=10_000)
    assert ours["pbo"] == pytest.approx(theirs["pbo"], abs=1e-12)
    assert ours["median_logit"] == pytest.approx(theirs["median_logit"], abs=1e-12)


def test_dsr_matches_nullius():
    nl = pytest.importorskip("nullius")
    rng = np.random.default_rng(6)
    r = rng.standard_t(5, 2000) * 0.01 + 0.0008
    ours = SC.deflated_sharpe(r, 237, 0.03 ** 2)
    theirs = nl.deflated_sharpe_ratio(r, n_trials=237, var_across_trials=0.03 ** 2)
    assert ours["sr0"] == pytest.approx(theirs["sr0"], rel=1e-9)
    assert ours["dsr"] == pytest.approx(theirs["dsr"], abs=1e-9)


def test_psr_close_to_jsharpe():
    pytest.importorskip("jsharpe")
    from jsharpe.sharpe.psr import probabilistic_sharpe_ratio
    # jsharpe evalúa la varianza bajo H0 (en SR0) y divide por T; Bailey y López de Prado
    # (2012) la evalúan en el SR observado con T - 1. Con Sharpe diarios pequeños coinciden.
    for sr, t, g3, g4 in [(0.03, 2400, -0.3, 6.0), (0.05, 2400, 0.1, 4.0), (-0.02, 1000, 0.0, 3.0)]:
        assert SC.psr(sr, 0.0, t, g3, g4) == pytest.approx(
            probabilistic_sharpe_ratio(sr, 0.0, T=t, gamma3=g3, gamma4=g4), abs=0.005)

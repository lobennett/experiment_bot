"""SP11 Phase 2.1 — pink_noise convention fix.

Tests cover:
1. The new ``alpha`` parameter on PinkNoiseConfig works for direct
   construction and round-trips through from_dict/to_dict.
2. The legacy ``hurst`` parameter on from_dict still works (deprecation
   alias) AND prints to stderr.
3. The generator produces a spectrum whose log-log slope matches the
   configured alpha within tolerance.
"""
from __future__ import annotations

import io
import sys

import numpy as np
import pytest

from experiment_bot.core.config import (
    PinkNoiseConfig,
    _reset_deprecation_warnings_for_tests,
)
from experiment_bot.core.distributions import _generate_pink_noise


@pytest.fixture(autouse=True)
def _reset_deprecation_gate():
    """Reset the module-level once-gate before every test so each test
    sees a fresh stderr-warning state."""
    _reset_deprecation_warnings_for_tests()
    yield
    _reset_deprecation_warnings_for_tests()


def test_pink_noise_config_accepts_alpha_directly():
    cfg = PinkNoiseConfig(enabled=True, sd_ms=15.0, alpha=1.0, rationale="pink")
    assert cfg.alpha == 1.0
    assert cfg.sd_ms == 15.0
    assert cfg.enabled is True


def test_pink_noise_config_from_dict_with_alpha_no_warning():
    """from_dict with `alpha` should NOT emit a deprecation warning."""
    captured = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = captured
    try:
        cfg = PinkNoiseConfig.from_dict(
            {"enabled": True, "sd_ms": 10.0, "alpha": 1.0, "rationale": ""}
        )
    finally:
        sys.stderr = old_stderr
    assert cfg.alpha == 1.0
    assert "DEPRECATION" not in captured.getvalue()
    assert "WARNING" not in captured.getvalue()


def test_pink_noise_config_from_dict_with_hurst_converts_with_warning():
    """from_dict with the legacy `hurst` field converts to alpha via
    the pre-SP11 fBm convention alpha = 2*hurst − 1, AND prints a
    loud deprecation warning to stderr."""
    captured = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = captured
    try:
        cfg = PinkNoiseConfig.from_dict(
            {"enabled": True, "sd_ms": 10.0, "hurst": 1.0, "rationale": ""}
        )
    finally:
        sys.stderr = old_stderr
    # hurst=1.0 → alpha=1.0 under old convention
    assert cfg.alpha == 1.0
    msg = captured.getvalue()
    assert "DEPRECATION" in msg
    assert "hurst" in msg
    assert "alpha" in msg


def test_pink_noise_config_from_dict_with_both_uses_alpha_warns():
    """If both `alpha` and `hurst` are present, prefer alpha and warn."""
    captured = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = captured
    try:
        cfg = PinkNoiseConfig.from_dict(
            {"enabled": True, "sd_ms": 10.0, "hurst": 0.5, "alpha": 1.5, "rationale": ""}
        )
    finally:
        sys.stderr = old_stderr
    assert cfg.alpha == 1.5
    msg = captured.getvalue()
    assert "WARNING" in msg
    assert "ignoring hurst" in msg


def test_pink_noise_spectrum_slope_matches_alpha_one():
    """Synthesize a long pink (alpha=1) buffer; verify the log-log
    power-spectrum slope is approximately -1."""
    rng = np.random.default_rng(42)
    n = 8192
    pink = _generate_pink_noise(n, alpha=1.0, rng=rng)
    # Power spectrum
    fft = np.fft.rfft(pink)
    power = np.abs(fft) ** 2
    freqs = np.fft.rfftfreq(n)
    # Drop DC + tail-edge bins; fit log-log slope across the body
    mask = (freqs > 0.005) & (freqs < 0.3)
    log_f = np.log(freqs[mask])
    log_p = np.log(power[mask] + 1e-30)
    slope, _intercept = np.polyfit(log_f, log_p, 1)
    # Allow ±0.25 tolerance for finite-N spectral estimation noise
    assert -1.25 < slope < -0.75, f"alpha=1 expected slope ≈ -1, got {slope:.3f}"


def test_pink_noise_spectrum_slope_matches_alpha_two():
    """alpha=2 → red/Brownian noise → spectrum slope ≈ -2."""
    rng = np.random.default_rng(42)
    n = 8192
    brown = _generate_pink_noise(n, alpha=2.0, rng=rng)
    fft = np.fft.rfft(brown)
    power = np.abs(fft) ** 2
    freqs = np.fft.rfftfreq(n)
    mask = (freqs > 0.005) & (freqs < 0.3)
    log_f = np.log(freqs[mask])
    log_p = np.log(power[mask] + 1e-30)
    slope, _ = np.polyfit(log_f, log_p, 1)
    assert -2.3 < slope < -1.7, f"alpha=2 expected slope ≈ -2, got {slope:.3f}"


def test_pink_noise_hurst_deprecation_is_once_gated_per_process():
    """Per Phase 3 user note: the hurst→alpha deprecation warning must
    fire once per process, not on every from_dict call. Three
    consecutive hurst-using loads should produce exactly one
    DEPRECATION message."""
    captured = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = captured
    try:
        PinkNoiseConfig.from_dict(
            {"enabled": True, "sd_ms": 10.0, "hurst": 1.0, "rationale": ""}
        )
        PinkNoiseConfig.from_dict(
            {"enabled": True, "sd_ms": 12.0, "hurst": 0.75, "rationale": ""}
        )
        PinkNoiseConfig.from_dict(
            {"enabled": True, "sd_ms": 8.0, "hurst": 1.2, "rationale": ""}
        )
    finally:
        sys.stderr = old_stderr
    msg = captured.getvalue()
    assert msg.count("DEPRECATION") == 1, (
        f"expected exactly 1 DEPRECATION message, got "
        f"{msg.count('DEPRECATION')}:\n{msg}"
    )


def test_pink_noise_to_dict_round_trip():
    cfg = PinkNoiseConfig(enabled=True, sd_ms=20.0, alpha=1.0, rationale="pink-test")
    d = cfg.to_dict()
    assert d["alpha"] == 1.0
    assert "hurst" not in d
    cfg2 = PinkNoiseConfig.from_dict(d)
    assert cfg2.alpha == 1.0
    assert cfg2.sd_ms == 20.0

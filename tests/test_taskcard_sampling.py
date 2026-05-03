from experiment_bot.taskcard.sampling import sample_session_params
from hypothesis import given, strategies as st


def _tc_dict_with_dist(value, lit_range, sd):
    return {
        "response_distributions": {
            "go": {
                "value": value,
                "literature_range": lit_range,
                "between_subject_sd": sd,
            }
        }
    }


def test_sample_returns_value_when_sd_zero():
    tc = _tc_dict_with_dist(
        value={"mu": 480, "sigma": 60, "tau": 80},
        lit_range=None,
        sd=None,
    )
    out = sample_session_params(tc, seed=42)
    assert out["go"]["mu"] == 480.0
    assert out["go"]["sigma"] == 60.0
    assert out["go"]["tau"] == 80.0


def test_sample_is_deterministic_for_seed():
    tc = _tc_dict_with_dist(
        value={"mu": 480, "sigma": 60, "tau": 80},
        lit_range=None,
        sd={"mu": 50, "sigma": 10, "tau": 20},
    )
    a = sample_session_params(tc, seed=42)
    b = sample_session_params(tc, seed=42)
    assert a == b


def test_sample_clips_to_literature_range():
    tc = _tc_dict_with_dist(
        value={"mu": 480, "sigma": 60, "tau": 80},
        lit_range={"mu": [470, 490], "sigma": [55, 65], "tau": [75, 85]},
        sd={"mu": 1000, "sigma": 1000, "tau": 1000},
    )
    out = sample_session_params(tc, seed=0)
    assert 470 <= out["go"]["mu"] <= 490
    assert 55 <= out["go"]["sigma"] <= 65
    assert 75 <= out["go"]["tau"] <= 85


def test_sample_handles_missing_param():
    tc = {"response_distributions": {"go": {"value": {"mu": 480}}}}
    out = sample_session_params(tc, seed=0)
    assert out["go"] == {"mu": 480.0}


@given(
    mu=st.floats(min_value=200, max_value=1000),
    sigma=st.floats(min_value=10, max_value=200),
    tau=st.floats(min_value=10, max_value=300),
    sd_mu=st.floats(min_value=0, max_value=200),
    seed=st.integers(min_value=0, max_value=2**32 - 1),
)
def test_sample_property_finite_and_deterministic(mu, sigma, tau, sd_mu, seed):
    tc = {
        "response_distributions": {
            "go": {
                "value": {"mu": mu, "sigma": sigma, "tau": tau},
                "between_subject_sd": {"mu": sd_mu, "sigma": 0, "tau": 0},
            }
        }
    }
    a = sample_session_params(tc, seed=seed)
    b = sample_session_params(tc, seed=seed)
    assert a == b
    for _, v in a["go"].items():
        assert v == v  # not NaN
        assert v != float("inf") and v != float("-inf")

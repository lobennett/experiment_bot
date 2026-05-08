"""Tests for platform-export → canonical-trial adapters.

These adapters are analysis-side code (post-hoc data parsing); they do
not influence how the bot performs the task. Per CLAUDE.md, hardcoding
paradigm-specific schema knowledge here is allowed.
"""
from pathlib import Path

from experiment_bot.validation.platform_adapters import (
    read_expfactory_stop_signal, read_stopit_stop_signal,
)


def test_expfactory_flanker_canonicalizes_test_trials(tmp_path):
    """Flanker adapter filters to test trials and produces the canonical
    {condition, rt, correct, omission} schema the oracle expects."""
    import json
    from experiment_bot.validation.platform_adapters import read_expfactory_flanker
    sample = [
        {"trial_type": "html-keyboard-response", "trial_id": "test_trial",
         "condition": "congruent", "rt": 480, "correct_trial": 1,
         "response": "f", "correct_response": "f"},
        {"trial_type": "html-keyboard-response", "trial_id": "test_trial",
         "condition": "incongruent", "rt": 562, "correct_trial": 0,
         "response": "f", "correct_response": "j"},
        {"trial_type": "html-keyboard-response", "trial_id": "fixation",
         "condition": "", "rt": None, "correct_trial": None},  # filtered out
        {"trial_type": "html-keyboard-response", "trial_id": "test_trial",
         "condition": "incongruent", "rt": None, "correct_trial": 0,
         "response": None, "correct_response": "j"},  # omission
    ]
    ses = tmp_path / "session"
    ses.mkdir()
    (ses / "experiment_data.json").write_text(json.dumps(sample))

    trials = read_expfactory_flanker(ses)

    assert len(trials) == 3
    assert trials[0] == {"condition": "congruent", "rt": 480.0, "correct": True, "omission": False}
    assert trials[1] == {"condition": "incongruent", "rt": 562.0, "correct": False, "omission": False}
    assert trials[2] == {"condition": "incongruent", "rt": None, "correct": False, "omission": True}


def test_flanker_adapter_dispatch_registered():
    """The adapter must be reachable through PLATFORM_ADAPTERS by the
    output-directory label name (matches the regenerated TaskCard's task.name)."""
    from experiment_bot.validation.platform_adapters import (
        PLATFORM_ADAPTERS, read_expfactory_flanker,
    )
    assert any(v is read_expfactory_flanker for v in PLATFORM_ADAPTERS.values()), \
        "read_expfactory_flanker not registered in PLATFORM_ADAPTERS"


def test_expfactory_n_back_canonicalizes_test_trials(tmp_path):
    """n-back adapter:
    - filters trial_id == 'test_trial' AND condition != 'N/A' (the latter
      excludes warmup trials where the bot correctly does not respond);
    - canonicalizes condition + delay into <condition>_<delay>back
      labels matching the TaskCard's response_distributions keys."""
    import json
    from experiment_bot.validation.platform_adapters import read_expfactory_n_back
    sample = [
        {"trial_type": "html-keyboard-response", "trial_id": "test_trial",
         "condition": "match", "delay": "1", "rt": 540, "correct_trial": 1,
         "response": ".", "correct_response": "."},
        {"trial_type": "html-keyboard-response", "trial_id": "test_trial",
         "condition": "mismatch", "delay": "1", "rt": 620, "correct_trial": 0,
         "response": ".", "correct_response": ","},
        {"trial_type": "html-keyboard-response", "trial_id": "test_trial",
         "condition": "match", "delay": "2", "rt": 580, "correct_trial": 1,
         "response": ".", "correct_response": "."},
        # warmup — filtered out
        {"trial_type": "html-keyboard-response", "trial_id": "test_trial",
         "condition": "N/A", "delay": "1", "rt": None, "correct_trial": 0,
         "response": None, "correct_response": "."},
        # non-test row — filtered out
        {"trial_type": "html-keyboard-response", "trial_id": "test_fixation",
         "condition": "", "rt": None, "correct_trial": None},
        # omission on real test trial
        {"trial_type": "html-keyboard-response", "trial_id": "test_trial",
         "condition": "mismatch", "delay": "2", "rt": None, "correct_trial": 0,
         "response": None, "correct_response": ","},
    ]
    ses = tmp_path / "session"
    ses.mkdir()
    (ses / "experiment_data.json").write_text(json.dumps(sample))

    trials = read_expfactory_n_back(ses)

    assert len(trials) == 4  # 3 valid + 1 omission; warmup and fixation filtered
    assert trials[0] == {"condition": "match_1back", "rt": 540.0, "correct": True, "omission": False}
    assert trials[1] == {"condition": "mismatch_1back", "rt": 620.0, "correct": False, "omission": False}
    assert trials[2] == {"condition": "match_2back", "rt": 580.0, "correct": True, "omission": False}
    assert trials[3] == {"condition": "mismatch_2back", "rt": None, "correct": False, "omission": True}


def test_n_back_adapter_dispatch_registered():
    """The n-back adapter must be reachable through PLATFORM_ADAPTERS."""
    from experiment_bot.validation.platform_adapters import (
        PLATFORM_ADAPTERS, read_expfactory_n_back,
    )
    assert any(v is read_expfactory_n_back for v in PLATFORM_ADAPTERS.values()), \
        "read_expfactory_n_back not registered"


def test_expfactory_stop_signal_surfaces_ssd(tmp_path):
    """The poldracklab-stop-signal adapter must extract SSD from the
    platform export so the oracle can compute SSRT."""
    csv_text = (
        "trial_type,exp_stage,condition,rt,correct_trial,SSD\n"
        "poldracklab-stop-signal,test,go,520,1,\n"
        "poldracklab-stop-signal,test,stop,,1,250\n"
        "poldracklab-stop-signal,test,stop,480,0,300\n"
        "poldracklab-stop-signal,practice,go,550,1,\n"  # filtered out
    )
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "experiment_data.csv").write_text(csv_text)

    trials = read_expfactory_stop_signal(session_dir)
    assert len(trials) == 3

    go = [t for t in trials if t["condition"] == "go"]
    stop = [t for t in trials if t["condition"] == "stop"]
    assert len(go) == 1
    assert go[0]["ssd"] is None  # not a stop trial
    assert len(stop) == 2
    assert stop[0]["ssd"] == 250.0 and stop[0]["omission"] is True
    assert stop[1]["ssd"] == 300.0 and stop[1]["omission"] is False


def test_stopit_stop_signal_surfaces_ssd(tmp_path):
    """The kywch jsPsych stopit adapter must also extract SSD."""
    csv_text = (
        "block_i,signal,rt,correct,SSD\n"
        "0,no,500,true,\n"  # practice — filtered out
        "1,no,510,true,\n"
        "1,yes,,true,200\n"
        "2,yes,470,false,250\n"
    )
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "experiment_data.csv").write_text(csv_text)

    trials = read_stopit_stop_signal(session_dir)
    assert len(trials) == 3

    stop = [t for t in trials if t["condition"] == "stop"]
    assert len(stop) == 2
    assert stop[0]["ssd"] == 200.0 and stop[0]["omission"] is True
    assert stop[1]["ssd"] == 250.0 and stop[1]["omission"] is False

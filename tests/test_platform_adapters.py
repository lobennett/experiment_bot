"""Tests for platform-export → canonical-trial adapters.

These adapters are analysis-side code (post-hoc data parsing); they do
not influence how the bot performs the task. Per CLAUDE.md, hardcoding
paradigm-specific schema knowledge here is allowed.
"""
from pathlib import Path

from experiment_bot.validation.platform_adapters import (
    read_expfactory_stop_signal, read_stopit_stop_signal,
)


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

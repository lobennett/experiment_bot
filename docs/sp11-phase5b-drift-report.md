# SP11 Phase 5b — TaskCard parameter drift report

**Baseline tag:** `sp8-complete`
**Threshold:** drift > 10.0% (relative)

Per user note 4: parameter values that drift > 10% relative to their SP8 baseline are flagged for discussion before Phase 7. Calibration-effect-plus-parameter-drift is a real confound; we want to identify it before it pollutes the pre/post-cal comparison.

## expfactory_stroop

### response_distributions

| Field | Baseline | Current | Drift % | Status |
|---|---|---|---|---|
| `congruent.mu` | 530.0 | 595.0 | 12.26% | **FLAGGED** |
| `congruent.sigma` | 50.0 | 78.0 | 56.00% | **FLAGGED** |
| `congruent.tau` | 100.0 | 105.0 | 5.00% | ok |
| `incongruent.mu` | 580.0 | 655.0 | 12.93% | **FLAGGED** |
| `incongruent.sigma` | 60.0 | 85.0 | 41.67% | **FLAGGED** |
| `incongruent.tau` | 120.0 | 135.0 | 12.50% | **FLAGGED** |

**5 field(s) flagged in response_distributions** — review against the Reasoner's reasoning chain in the new TaskCard before Phase 7.

### performance

| Field | Baseline | Current | Drift % | Status |
|---|---|---|---|---|
| `accuracy.congruent` | 0.97 | 0.98 | 1.03% | ok |
| `accuracy.incongruent` | 0.92 | 0.93 | 1.09% | ok |
| `omission_rate.congruent` | 0.005 | 0.005 | 0.00% | ok |
| `omission_rate.incongruent` | 0.01 | 0.01 | 0.00% | ok |

## expfactory_stop_signal

### response_distributions

| Field | Baseline | Current | Drift % | Status |
|---|---|---|---|---|
| `go.mu` | 420.0 | 420.0 | 0.00% | ok |
| `go.sigma` | 50.0 | 55.0 | 10.00% | ok |
| `go.tau` | 110.0 | 100.0 | 9.09% | ok |
| `stop.mu` | 350.0 | 360.0 | 2.86% | ok |
| `stop.sigma` | 45.0 | 50.0 | 11.11% | **FLAGGED** |
| `stop.tau` | 85.0 | 70.0 | 17.65% | **FLAGGED** |

**2 field(s) flagged in response_distributions** — review against the Reasoner's reasoning chain in the new TaskCard before Phase 7.

### performance

| Field | Baseline | Current | Drift % | Status |
|---|---|---|---|---|
| `accuracy.go` | 0.95 | 0.95 | 0.00% | ok |
| `accuracy.stop` | 0.5 | 0.5 | 0.00% | ok |
| `omission_rate.go` | 0.02 | 0.02 | 0.00% | ok |
| `omission_rate.stop` | 0.0 | 0.0 | 0.00% | ok |

## stopit_stop_signal

### response_distributions

| Field | Baseline | Current | Drift % | Status |
|---|---|---|---|---|
| `go.mu` | 440.0 | — | — | removed |
| `go.sigma` | 40.0 | — | — | removed |
| `go.tau` | 100.0 | — | — | removed |
| `go_left.mu` | — | 440.0 | — | added |
| `go_left.sigma` | — | 55.0 | — | added |
| `go_left.tau` | — | 110.0 | — | added |
| `go_right.mu` | — | 440.0 | — | added |
| `go_right.sigma` | — | 55.0 | — | added |
| `go_right.tau` | — | 110.0 | — | added |
| `stop_signal.mu` | 380.0 | 370.0 | 2.63% | ok |
| `stop_signal.sigma` | 40.0 | 50.0 | 25.00% | **FLAGGED** |
| `stop_signal.tau` | 80.0 | 85.0 | 6.25% | ok |

**1 field(s) flagged in response_distributions** — review against the Reasoner's reasoning chain in the new TaskCard before Phase 7.

### performance

| Field | Baseline | Current | Drift % | Status |
|---|---|---|---|---|
| `accuracy.go` | 0.97 | — | — | removed |
| `accuracy.go_left` | — | 0.97 | — | added |
| `accuracy.go_right` | — | 0.97 | — | added |
| `accuracy.stop_signal` | 0.5 | 0.5 | 0.00% | ok |
| `omission_rate.go` | 0.02 | — | — | removed |
| `omission_rate.go_left` | — | 0.015 | — | added |
| `omission_rate.go_right` | — | 0.015 | — | added |
| `omission_rate.stop_signal` | 0.0 | 0.5 | inf% | **FLAGGED** |

**1 field(s) flagged in performance** — review against the Reasoner's reasoning chain in the new TaskCard before Phase 7.

## cognitionrun_stroop

### response_distributions

| Field | Baseline | Current | Drift % | Status |
|---|---|---|---|---|
| `congruent.mu` | 530.0 | 520.0 | 1.89% | ok |
| `congruent.sigma` | 50.0 | 55.0 | 10.00% | ok |
| `congruent.tau` | 100.0 | 110.0 | 10.00% | ok |
| `incongruent.mu` | 580.0 | 560.0 | 3.45% | ok |
| `incongruent.sigma` | 60.0 | 65.0 | 8.33% | ok |
| `incongruent.tau` | 140.0 | 145.0 | 3.57% | ok |

### performance

| Field | Baseline | Current | Drift % | Status |
|---|---|---|---|---|
| `accuracy.congruent` | 0.97 | 0.99 | 2.06% | ok |
| `accuracy.incongruent` | 0.93 | 0.95 | 2.15% | ok |
| `omission_rate.congruent` | 0.005 | 0.005 | 0.00% | ok |
| `omission_rate.incongruent` | 0.01 | 0.005 | 50.00% | **FLAGGED** |

**1 field(s) flagged in performance** — review against the Reasoner's reasoning chain in the new TaskCard before Phase 7.

---

**Total flagged across all paradigms:** 10

**ACTION REQUIRED:** review flagged fields with the user before launching Phase 7's measurement sweep. Calibration + parameter drift is a confound that the pre/post-cal arm split cannot disentangle.

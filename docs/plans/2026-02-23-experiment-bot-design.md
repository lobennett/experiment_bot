# Experiment Bot Design

## Overview

`experiment_bot` is a Python package that executes human-like behavior on web-based cognitive tasks. It is generalizable — not hardcoded to any specific task. Instead, it downloads task source code, sends it to Claude Opus 4.6 for analysis, and receives a structured configuration file that drives automated task execution with realistic response timing.

## Architecture: Analyze-then-Execute

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Platform    │────▶│  Claude API  │────▶│  TaskConfig  │────▶│  Executor    │
│  Adapter     │     │  Analysis    │     │  (JSON)      │     │  (Playwright)│
│  downloads   │     │  creates     │     │  cached      │     │  runs task   │
│  source code │     │  config      │     │  locally     │     │  using config│
└─────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

**Key constraint:** No API calls during trials. All stimulus-response decisions are pre-computed lookups. The bot must respond in ~300-600ms, which precludes real-time API calls.

**Fallback:** If the bot is stuck (no stimulus detected for >10 seconds), it screenshots the page and makes a Haiku API call for guidance, caching the result.

## Technology Stack

| Component | Technology |
|---|---|
| Package manager | uv |
| Browser automation | Playwright (async) |
| LLM analysis | Claude Opus 4.6 via `anthropic` SDK |
| Fallback LLM | Claude Haiku via `anthropic` SDK |
| CLI | Click |
| RT distributions | NumPy (ex-Gaussian sampling) |
| Config format | JSON |

## Package Structure

```
experiment_bot/
├── pyproject.toml
├── src/
│   └── experiment_bot/
│       ├── __init__.py
│       ├── cli.py                  # Click CLI entry point
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py           # TaskConfig dataclass
│       │   ├── executor.py         # TaskExecutor: drives Playwright
│       │   ├── analyzer.py         # Claude API analysis call
│       │   └── distributions.py    # RT sampling (ex-Gaussian, etc.)
│       ├── platforms/
│       │   ├── __init__.py
│       │   ├── base.py             # Abstract Platform adapter
│       │   ├── expfactory.py       # Experiment Factory adapter
│       │   └── psytoolkit.py       # PsyToolkit adapter
│       ├── navigation/
│       │   ├── __init__.py
│       │   ├── navigator.py        # InstructionNavigator
│       │   └── stuck.py            # StuckDetector with Haiku fallback
│       ├── prompts/
│       │   ├── __init__.py
│       │   ├── system.md           # System prompt for Claude analysis
│       │   └── schema.json         # JSON schema for TaskConfig
│       └── output/
│           ├── __init__.py
│           └── writer.py           # Output directory writer
├── cache/                          # Cached configs (.gitignored)
├── docs/
│   └── plans/
└── tests/
```

## CLI Interface

```bash
# Platform subcommands with task ID
uv run experiment-bot expfactory --task 9              # stop signal
uv run experiment-bot expfactory --task 2              # cued task switching
uv run experiment-bot psytoolkit --task stopsignal
uv run experiment-bot psytoolkit --task taskswitching_cued

# Optional overrides
uv run experiment-bot expfactory --task 9 --rt-mean 450 --accuracy 0.95

# Flags
uv run experiment-bot expfactory --task 9 --headless
uv run experiment-bot expfactory --task 9 --regenerate-config
```

## Platform Adapters

### Abstract Base

```python
class Platform(ABC):
    @abstractmethod
    async def download_source(self, task_id: str, output_dir: Path) -> SourceBundle:
        """Download task source code and description text."""

    @abstractmethod
    async def get_task_url(self, task_id: str) -> str:
        """Return the URL to launch the task."""

    @abstractmethod
    async def detect_task_phase(self, page: Page) -> TaskPhase:
        """Detect current phase: INSTRUCTIONS, PRACTICE, TEST, FEEDBACK, COMPLETE."""
```

### SourceBundle

```python
@dataclass
class SourceBundle:
    platform: str
    task_id: str
    source_files: dict[str, str]   # filename → content
    description_text: str           # scraped task description / theory
    metadata: dict                  # platform-specific extras
```

### TaskPhase

```python
class TaskPhase(Enum):
    LOADING = "loading"
    INSTRUCTIONS = "instructions"
    PRACTICE = "practice"
    FEEDBACK = "feedback"
    TEST = "test"
    ATTENTION_CHECK = "attention_check"
    COMPLETE = "complete"
```

### ExpFactory Adapter

- Fetches preview page HTML at `https://deploy.expfactory.org/preview/<id>/`
- Parses `<script>` and `<link>` tags to find `experiment.js`, CSS, and plugin files
- Downloads each file by visiting its route on `deploy.expfactory.org`
- All tasks use jsPsych — stimuli are dynamically generated in DOM
- Phase detection uses jsPsych trial type inspection

### PsyToolkit Adapter

- Downloads zip from `https://www.psytoolkit.org/doc_exp/<task_id>.zip`
- Extracts zip contents locally
- Scrapes the task library page for description text (task theory, response keys, timing)
- Tasks render on `<canvas>` — stimulus detection uses JS state variables or pixel sampling
- Phase detection uses PsyToolkit's internal state

## Claude Analysis Pipeline

### Input

The `Analyzer` sends a `SourceBundle` to Claude Opus 4.6 with:
1. **System prompt** (`prompts/system.md`): Instructs Claude to act as a cognitive psychology expert. Tells it to identify task type, extract stimulus-response mappings, recommend RT distributions from literature, and output conformant JSON.
2. **User message**: Contains source code files, description text, and metadata.
3. **Response constraint**: Must conform to `prompts/schema.json`.

### Output: TaskConfig

```json
{
  "task": {
    "name": "Stop Signal Task",
    "platform": "expfactory",
    "constructs": ["inhibitory_control", "response_inhibition"],
    "reference_literature": ["Logan et al. 1984", "Verbruggen & Logan 2008"]
  },
  "stimuli": [
    {
      "id": "go_left",
      "description": "Left-pointing arrow, no stop signal",
      "detection": {
        "method": "dom_query",
        "selector": ".stimulus-arrow-left",
        "alt_method": "text_content",
        "pattern": "←"
      },
      "response": {
        "key": "z",
        "condition": "go"
      }
    }
  ],
  "response_distributions": {
    "go_correct": {
      "distribution": "ex_gaussian",
      "params": {"mu": 450, "sigma": 60, "tau": 80},
      "unit": "ms"
    },
    "go_error": {
      "distribution": "ex_gaussian",
      "params": {"mu": 380, "sigma": 70, "tau": 100},
      "unit": "ms"
    },
    "stop_failure": {
      "distribution": "ex_gaussian",
      "params": {"mu": 400, "sigma": 50, "tau": 60},
      "unit": "ms"
    }
  },
  "performance": {
    "go_accuracy": 0.95,
    "stop_accuracy": 0.50,
    "omission_rate": 0.02,
    "practice_accuracy": 0.85
  },
  "navigation": {
    "phases": [
      {"phase": "fullscreen", "action": "click", "target": "button:contains('Continue')"},
      {"phase": "instructions", "action": "sequence", "steps": [
        {"action": "wait", "duration_ms": 3000},
        {"action": "press", "key": "Enter"}
      ]},
      {"phase": "instructions_pages", "action": "repeat", "steps": [
        {"action": "wait", "duration_ms": 5000},
        {"action": "click", "target": "button:contains('Next')"}
      ]},
      {"phase": "practice_start", "action": "press", "key": "Enter"}
    ]
  },
  "task_specific": {
    "model": "independent_race",
    "ssrt_target_ms": 250,
    "ssd_tracking": true
  }
}
```

### Caching

- Configs are cached in `cache/<platform>/<task_id>/config.json`
- Reused on subsequent runs unless `--regenerate-config` is passed
- Cache directory is `.gitignored`

## Execution Engine

### TaskExecutor Flow

1. Launch Playwright browser (headed by default)
2. Navigate to task URL
3. Execute navigation phases from config
4. Enter trial loop:
   - Poll DOM for stimulus using pre-compiled selectors
   - Match stimulus → look up response key
   - Sample RT from appropriate ex-Gaussian distribution
   - Wait sampled RT, then press key (or withhold for stop trials)
   - Log trial
5. Handle inter-block feedback and attention checks
6. Wait for completion, download data

### StimulusLookup

Pre-compiled at startup from config. Each stimulus rule has a DOM selector and expected response. The `identify()` method iterates rules and returns the first match. This is the hot path — must be fast.

For PsyToolkit canvas tasks, detection uses `page.evaluate()` to read internal state variables rather than DOM selectors.

### ResponseSampler

Samples from ex-Gaussian distributions with literature-based parameters. Enforces a 150ms floor (physiological minimum). Supports per-condition distributions (go correct, go error, stop failure, switch, repeat, congruent, incongruent).

### Stop Signal: Independent Race Model

- Go trials: sample go RT, respond after that delay
- Stop trials: SSD is set by the task's staircase. The bot samples a go RT and an SSRT. If go RT > SSD + SSRT, the bot inhibits (no response). Otherwise, it responds (failed stop). This naturally produces ~50% stop accuracy per the race model.

### Task Switching: Switch Cost & Congruency Effects

- RT distributions vary by condition: switch trials have higher mu than repeat trials
- Incongruent stimuli have higher mu than congruent
- These differences are specified in the config by Claude based on literature

### InstructionNavigator

Follows the `navigation.phases` sequence from config. Injects human-like reading delays (3-8 seconds per instruction page, jittered). Handles practice with slightly lower accuracy. Detects feedback screens and advances.

### StuckDetector

Background coroutine that monitors for inactivity. If no successful stimulus detection for >10 seconds during a trial phase:
1. Take screenshot
2. Send to Claude Haiku with context
3. Get guidance (e.g., "press spacebar to continue")
4. Cache result for similar states
5. Execute the suggested action

## Output Structure

```
output/
└── expfactory/
    └── stop_signal_rdoc/
        └── 2026-02-23_14-30-22/
            ├── config.json          # TaskConfig used
            ├── task_data.csv        # Platform's experiment data
            ├── bot_log.json         # Trial-by-trial bot behavior
            ├── run_metadata.json    # Run info, timing, errors
            └── screenshots/         # Error/stuck screenshots
```

### bot_log.json

```json
[
  {
    "trial": 1,
    "phase": "test",
    "stimulus_id": "go_left",
    "detected_at_ms": 1234567890,
    "response_key": "z",
    "sampled_rt_ms": 487,
    "actual_rt_ms": 491,
    "condition": "go"
  }
]
```

## Test Matrix

The initial validation is a 2×2 design:

| | Experiment Factory | PsyToolkit |
|---|---|---|
| **Stop Signal** | preview/9/ | stopsignal |
| **Cued Task Switching** | preview/2/ | taskswitching_cued |

Success criteria:
- Bot completes all four tasks without manual intervention
- Response time distributions match literature expectations
- Stop signal: ~50% stop accuracy, SSRT ~250ms
- Task switching: measurable switch cost and congruency effects
- Data is successfully downloaded and logged

## Dependencies

- `playwright` — browser automation
- `anthropic` — Claude API client
- `click` — CLI framework
- `numpy` — distribution sampling

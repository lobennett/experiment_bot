// SOURCE: https://github.com/jspsych/jsPsych/blob/jspsych@7.3.1/packages/plugin-instructions/src/index.ts
// TAG: jspsych@7.3.1
// LICENSE: MIT (see vendor/LICENSES.md)
// RETRIEVED: 2026-05-17
//
// Vendored as a version-pinned API reference for
// src/experiment_bot/drivers/jspsych/navigation.py. The driver uses
// this to choose the right advance mechanism for instructions screens:
//
// Key findings:
// - Button IDs: "jspsych-instructions-next" and "jspsych-instructions-back"
//   (when show_clickable_nav=true).
// - Default key_forward: "ArrowRight" (NOT Space!) — this was the
//   bug source: dispatching Space had no effect because instructions
//   ignores it.
// - Default key_backward: "ArrowLeft".
// - allow_keys defaults to true; allow_backward defaults to true.
// - The btnListener handler attaches via addEventListener("click", ...)
//   and removes itself after firing. Playwright's page.click(selector)
//   simulates a real user click (focus + mousedown + mouseup + click)
//   which reliably triggers this listener. element.click() via
//   page.evaluate may or may not, depending on browser internals.

import { JsPsych, JsPsychPlugin, ParameterType, TrialType } from "jspsych";

const info = <const>{
  name: "instructions",
  parameters: {
    /** Each element of the array is the HTML-formatted content for a single page. */
    pages: {
      type: ParameterType.HTML_STRING,
      pretty_name: "Pages",
      default: undefined,
      array: true,
    },
    /** The key the subject can press in order to advance to the next page. */
    key_forward: {
      type: ParameterType.KEY,
      pretty_name: "Key forward",
      default: "ArrowRight",
    },
    /** The key that the subject can press to return to the previous page. */
    key_backward: {
      type: ParameterType.KEY,
      pretty_name: "Key backward",
      default: "ArrowLeft",
    },
    /** If true, the subject can return to the previous page of the instructions. */
    allow_backward: {
      type: ParameterType.BOOL,
      pretty_name: "Allow backward",
      default: true,
    },
    /** If true, the subject can use keyboard keys to navigate the pages. */
    allow_keys: {
      type: ParameterType.BOOL,
      pretty_name: "Allow keys",
      default: true,
    },
    /** If true, then a "Previous" and "Next" button will be displayed beneath the instructions. */
    show_clickable_nav: {
      type: ParameterType.BOOL,
      pretty_name: "Show clickable nav",
      default: false,
    },
    /** If true, and clickable navigation is enabled, then Page x/y will be shown between the nav buttons. */
    show_page_number: {
      type: ParameterType.BOOL,
      pretty_name: "Show page number",
      default: false,
    },
    /** The text that appears before x/y (current/total) pages displayed with show_page_number. */
    page_label: {
      type: ParameterType.STRING,
      pretty_name: "Page label",
      default: "Page",
    },
    /** The text that appears on the button to go backwards. */
    button_label_previous: {
      type: ParameterType.STRING,
      pretty_name: "Button label previous",
      default: "Previous",
    },
    /** The text that appears on the button to go forwards. */
    button_label_next: {
      type: ParameterType.STRING,
      pretty_name: "Button label next",
      default: "Next",
    },
  },
};

type Info = typeof info;

/**
 * **instructions**
 *
 * jsPsych plugin to display text (including HTML-formatted strings) during the experiment.
 * Use it to show a set of pages that participants can move forward/backward through.
 *
 * @author Josh de Leeuw
 */
class InstructionsPlugin implements JsPsychPlugin<Info> {
  static info = info;

  constructor(private jsPsych: JsPsych) {}

  trial(display_element: HTMLElement, trial: TrialType<Info>) {
    var current_page = 0;
    var view_history = [];
    var start_time = performance.now();
    var last_page_update_time = start_time;

    function btnListener(evt) {
      evt.target.removeEventListener("click", btnListener);
      if (this.id === "jspsych-instructions-back") {
        back();
      } else if (this.id === "jspsych-instructions-next") {
        next();
      }
    }

    function show_current_page() {
      var html = trial.pages[current_page];
      // ... (rendering omitted for brevity, see upstream)
      if (trial.show_clickable_nav) {
        // Buttons rendered:
        //   <button id="jspsych-instructions-back" class="jspsych-btn" ...>&lt; Previous</button>
        //   <button id="jspsych-instructions-next" class="jspsych-btn" ...>Next &gt;</button>
        // Each gets addEventListener("click", btnListener).
      }
    }

    function next() {
      current_page++;
      if (current_page >= trial.pages.length) endTrial();
      else show_current_page();
    }

    function back() {
      current_page--;
      show_current_page();
    }

    // Keyboard listener via pluginAPI.getKeyboardResponse with
    // valid_responses=[key_forward, key_backward].
    // Default key_forward="ArrowRight", key_backward="ArrowLeft".

    show_current_page();
  }
}

export default InstructionsPlugin;

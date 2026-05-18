// SOURCE: https://github.com/jspsych/jsPsych/blob/jspsych@7.3.1/packages/plugin-fullscreen/src/index.ts
// TAG: jspsych@7.3.1
// LICENSE: MIT (see vendor/LICENSES.md)
// RETRIEVED: 2026-05-17
//
// Vendored as a version-pinned API reference for
// src/experiment_bot/drivers/jspsych/navigation.py.
//
// Key findings:
// - Button ID: "jspsych-fullscreen-btn", class "jspsych-btn".
// - Button label default: "Continue".
// - Click handler: addEventListener("click", () => { enterFullScreen(); endTrial(...) }).
// - NO keyboard support — must be a click.
// - After click, browser fullscreen API is invoked, then endTrial fires
//   with `delay_after` ms wait (default 1000ms). The bot's navigate
//   needs to allow time for this delay before polling loop_state.

import { JsPsych, JsPsychPlugin, ParameterType, TrialType } from "jspsych";

const info = <const>{
  name: "fullscreen",
  parameters: {
    fullscreen_mode: {
      type: ParameterType.BOOL,
      pretty_name: "Fullscreen mode",
      default: true,
    },
    message: {
      type: ParameterType.HTML_STRING,
      pretty_name: "Message",
      default:
        "<p>The experiment will switch to full screen mode when you press the button below</p>",
    },
    button_label: {
      type: ParameterType.STRING,
      pretty_name: "Button label",
      default: "Continue",
    },
    delay_after: {
      type: ParameterType.INT,
      pretty_name: "Delay after",
      default: 1000,
    },
  },
};

type Info = typeof info;

/**
 * **fullscreen**
 *
 * jsPsych plugin for toggling fullscreen mode in the browser.
 *
 * @author Josh de Leeuw
 */
class FullscreenPlugin implements JsPsychPlugin<Info> {
  static info = info;

  constructor(private jsPsych: JsPsych) {}

  trial(display_element: HTMLElement, trial: TrialType<Info>) {
    // Rendered DOM:
    //   ${trial.message}
    //   <button id="jspsych-fullscreen-btn" class="jspsych-btn">${trial.button_label}</button>
    //
    // display_element.querySelector("#jspsych-fullscreen-btn")
    //   .addEventListener("click", () => {
    //     this.enterFullScreen();
    //     this.endTrial(display_element, true, trial);
    //   });
  }
}

export default FullscreenPlugin;

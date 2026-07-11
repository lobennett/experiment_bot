## Pilot Run Diagnostic Report

### Summary
- Trials completed: 1
- Trials with stimulus match: 1/1
- Conditions observed: ['survey_response']

### Selector Results
- survey_page: 1 matches / 1 polls (100.0%)

### DOM Snapshot (after_navigation)
<div id="jspsych-content" class="jspsych-content">
    <!-- ko template: { name: "survey-content-template", afterRender: $data.implementor.koEventAfterRender } -->
  <div data-bind="css: rootCss" class="sv_main sv_default_css">
      <form onsubmit="return false;">
          <div class="sv_custom_header" data-bind="visible: !hasLogo"></div>
          <div data-bind="css: containerCss" class="sv_container">
              <!-- ko template: { name: koTitleTemplate, afterRender: koAfterRenderHeader } -->
  <!-- ko if: renderedHasHeader --><!-- /ko -->
<!-- /ko -->
              <!-- ko if: isShowingPage -->
              <div data-bind="css: bodyCss" class="sv_body sv_body--static">
                  <!-- ko if: isTimerPanelShowingOnTop && !isShowStartingPage --><!-- /ko -->
                  <!-- ko if: isShowProgressBarOnTop && !isShowStartingPage --><!-- /ko -->
                  <!-- ko if: isNavigationButtonsShowingOnTop --><!-- /ko -->
                  <!-- ko if: activePage -->
                    <div data-bind="attr: { id: activePage.id }, template: { name: 'survey-page', data: activePage, afterRender: koAfterRenderPage }" id="sp_100">
  <div data-bind="css: cssClasses.page.root" class="sv_p_root">
    <!-- ko component: { name: 'survey-element-title', params: {element: $data } } --><!-- ko if: element.hasTitle --><!-- /ko --><!-- /ko -->
    <!-- ko if: _showDescription--><!-- /ko -->
    <!-- ko template: { name: 'survey-rows', data: $data} -->
  <!-- ko foreach: { data: rows, as: 'row'} -->
    <!-- ko if: row.visible -->
      <!-- ko component: { name: $parent.survey.getRowWrapperComponentName(row), params: { componentData:  $parent.survey.getRowWrapperComponentData(row), templateData: { name: 'survey-row', data: row } } } --><!-- ko if: templateData.name -->
  <!-- ko template: { name: templateData.name, data: templateData.data, afterRender: templateData.afterRender } -->
  <div data-bind="css: row.getRowCss()" class="sv_row">
    <!-- ko template: { name: "survey-row-content", afterRender: row.rowAfterRender } -->
<!-- ko foreach: { data: row.visibleElements, as: 'question', afterRender: row.koAfterRender } --><div data-bind="css: question.koCss().questionWrapper, style: $data.rootStyle, event: {focusin: question.focusIn }" style="width: 100%; flex: 1 1 100%; min-width: 300px; max-width: initial;">
  <!-- ko if: row.isNeedRender -->
    <!-- ko component: { name: row.panel.survey.getElementWrapperComponentName(question), params: { componentData:  row.panel.survey.getElementWrapperComponentData(question), templateData: { name: question.koElementType, data: question, afterRender: $parent.koElementAfterRender } } } --><!-- ko if: templateData.name -->
  <!-- ko template: { name: templateData.name, data: templateData.data, afterRender: templateData.afterRender } -->
<div data-bind="css: question.koRootCss(), style: { paddingLeft: question.paddingLeft, paddingRight: question.paddingRight }, attr: { id: question.id, 'data-name': question.name, role: question.ariaRole, 'aria-required': question.ariaRequired, 'aria-invalid': question.ariaInvalid, 'aria-labelledby': question.hasTitle ? question.ariaTitleId : null}" class="sv_q sv_qstn" id="sq_100" data-name="P0_Q0" aria-required="false" aria-invalid="false">
  <!-- ko if: question.isErrorsModeTooltip && !question.hasParent --><!-- /ko -->
  <!-- ko if: question.hasTitleOnLeftTop --><!-- /ko -->
  <!-- ko component: { name: question.survey.getQuestionContentWrapperComponentName(question), params: { componentData:  question.survey.getElementWrapperComponentData(question), templateData: { name: 'survey-question-content', data: question } } } --><!-- ko if: templateData.name -->
  <!-- ko template: { name: templateData.name, data: templateData.data, afterRender: templateData.afterRender } -->
<div data-bind="visible: !question.isCollapsed, css: question.cssContent" role="presentation">
    <!-- ko if: question.errorLocation === 'top' && !question.isErrorsModeTooltip -->
      

### DOM Snapshot (first_stimulus_match)
<div id="jspsych-content" class="jspsych-content">
    <!-- ko template: { name: "survey-content-template", afterRender: $data.implementor.koEventAfterRender } -->
  <div data-bind="css: rootCss" class="sv_main sv_default_css">
      <form onsubmit="return false;">
          <div class="sv_custom_header" data-bind="visible: !hasLogo"></div>
          <div data-bind="css: containerCss" class="sv_container">
              <!-- ko template: { name: koTitleTemplate, afterRender: koAfterRenderHeader } -->
  <!-- ko if: renderedHasHeader --><!-- /ko -->
<!-- /ko -->
              <!-- ko if: isShowingPage -->
              <div data-bind="css: bodyCss" class="sv_body sv_body--static">
                  <!-- ko if: isTimerPanelShowingOnTop && !isShowStartingPage --><!-- /ko -->
                  <!-- ko if: isShowProgressBarOnTop && !isShowStartingPage --><!-- /ko -->
                  <!-- ko if: isNavigationButtonsShowingOnTop --><!-- /ko -->
                  <!-- ko if: activePage -->
                    <div data-bind="attr: { id: activePage.id }, template: { name: 'survey-page', data: activePage, afterRender: koAfterRenderPage }" id="sp_100">
  <div data-bind="css: cssClasses.page.root" class="sv_p_root">
    <!-- ko component: { name: 'survey-element-title', params: {element: $data } } --><!-- ko if: element.hasTitle --><!-- /ko --><!-- /ko -->
    <!-- ko if: _showDescription--><!-- /ko -->
    <!-- ko template: { name: 'survey-rows', data: $data} -->
  <!-- ko foreach: { data: rows, as: 'row'} -->
    <!-- ko if: row.visible -->
      <!-- ko component: { name: $parent.survey.getRowWrapperComponentName(row), params: { componentData:  $parent.survey.getRowWrapperComponentData(row), templateData: { name: 'survey-row', data: row } } } --><!-- ko if: templateData.name -->
  <!-- ko template: { name: templateData.name, data: templateData.data, afterRender: templateData.afterRender } -->
  <div data-bind="css: row.getRowCss()" class="sv_row">
    <!-- ko template: { nam

### Phase Detection
- complete: never fired
- loading: never fired
- instructions: never fired
- attention_check: never fired
- feedback: never fired
- practice: never fired
- test: fired on trial 0

### Trial Log (first 20)
- Trial 1: survey_page (survey_response)

import asyncio,datetime,hashlib,json,time
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parent
URL='https://deploy.expfactory.org/preview/28/'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
index=0
def log(kind,observation=None,action=None,outcome=None,refs=None,timing=None):
 global index
 with (ROOT/'events.jsonl').open('a') as f:f.write(json.dumps(dict(index=index,at=now(),kind=kind,phase_id=None,trial_id=None,observation=observation,action=action,outcome=outcome,evidence_refs=refs or [],timing=timing))+'\n')
 index+=1
BASIC='''() => ({url:location.href,text:document.body.innerText,buttons:Array.from(document.querySelectorAll('button,input,select')).filter(e=>e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})&&e.getBoundingClientRect().width>0&&e.getBoundingClientRect().height>0).map(e=>({tag:e.tagName,text:e.innerText,id:e.id,type:e.type,value:e.value}))})'''
async def main():
 m={'schema_version':'1.0','run_id':'preview28-attempt-01','mode':'generated_visible_policy','input_url':URL,'final_url':None,'started_at':now(),'ended_at':None,'status':'running','status_reason':'Transport preflight then agent-controlled instruction discovery','model':{'provider':'OpenAI','model':None,'version':None},'browser':{'tool':'Playwright Python','isolation':'dedicated browser launch'},'observation_boundary':'participant_visible','skill_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (ROOT/'protocol').iterdir()},'seed':None,'reproducibility':'Visible-policy replay given same observations; no deterministic live session guarantee','completion_evidence_refs':[],'data_export':{'status':'not_attempted','paths':[],'reason':None},'counts':{},'limitations':['Inline authoring inherited agent context; not an isolated model generation transcript.'],'artifacts_sha256':{},'authoring_context':'inherited_agent_context','authoring_transcript_path':None,'input_delivery':'Playwright ordinary keyboard/mouse input','observation_interface':'Current visible DOM rendering, computed styles and geometry; no task internals'}
 (ROOT/'run.json').write_text(json.dumps(m,indent=2)+'\n')
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(channel='chrome',headless=True);m['browser']['version']=browser.version
  page=await browser.new_page(viewport={'width':1200,'height':1000})
  await page.set_content('<div style="opacity:0">hidden-alpha</div><div style="visibility:hidden">hidden-css</div><div style="position:absolute;left:-500px">offscreen</div><p id="probe">visible</p><script>document.addEventListener("keydown",e=>document.querySelector("p").textContent=e.key)</script>')
  visible=await page.evaluate('''() => Array.from(document.querySelectorAll('div,p')).filter(e=>{const r=e.getBoundingClientRect();return e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})&&r.width>0&&r.height>0&&r.right>0&&r.bottom>0&&r.left<innerWidth&&r.top<innerHeight}).map(e=>e.innerText)''')
  assert visible==['visible'],visible
  await page.keyboard.press('Shift');assert await page.locator('#probe').inner_text()=='Shift'
  (ROOT/'policy/adapter_gate.json').write_text(json.dumps({'status':'passed','visible_fixture':visible,'opacity_css_visibility_and_offscreen_excluded':True,'ordinary_key_delivery':True,'eval_function_supported':True},indent=2)+'\n')
  print('PREFLIGHT PASSED',flush=True)
  await page.goto(URL,wait_until='domcontentloaded')
  last='';observer=None;active=False;captures=0;responses=0;start=time.monotonic();completion=False
  try:
   while time.monotonic()-start<1500:
    obs=await page.evaluate(observer or BASIC)
    if obs['url']!=URL:raise RuntimeError('Unexpected URL '+obs['url'])
    text=obs['text'];sig=json.dumps(obs,sort_keys=True)
    # Exclude clock fields from change detection; identity and rendered content remain.
    sig=json.dumps({k:v for k,v in obs.items() if k not in ['at','browser_ms']},sort_keys=True)
    if sig!=last:
     log('observation',observation=obs);last=sig
     if not obs.get('stimulus') and (obs.get('buttons') or 'press' in text.lower() or len(text)>250):
      captures+=1;label=f'boundary-{captures:03d}';(ROOT/'evidence'/f'{label}.txt').write_text(text);await page.screenshot(path=str(ROOT/'evidence'/f'{label}.png'))
      print('BOUNDARY',label,json.dumps(obs)[:5000],flush=True)
    (ROOT/'current.json').write_text(json.dumps(obs,indent=2)+'\n')
    if 'Experiment Complete' in text:
     completion=True;(ROOT/'evidence/completion.txt').write_text(text);await page.screenshot(path=str(ROOT/'evidence/completion.png'));log('completion',observation=obs,refs=['completion']);print('COMPLETED',text[:500],flush=True);break
    command_file=ROOT/'command.json'
    if command_file.exists():
     command=json.loads(command_file.read_text());command_file.rename(ROOT/f'command-{index:05d}.json')
     kind=command['kind'];print('COMMAND',kind,flush=True)
     if kind=='stop':log('error',outcome='Operator requested stop');break
     if kind=='snapshot':
      label=command['label'];(ROOT/'evidence'/f'{label}.json').write_text(json.dumps(obs,indent=2)+'\n');await page.screenshot(path=str(ROOT/'evidence'/f'{label}.png'));log('observation',observation=obs,outcome='Snapshot captured '+label)
     if kind=='inspect_visible':
      value=await page.evaluate(command['expression']);(ROOT/'evidence'/f"{command['label']}.json").write_text(json.dumps(value,indent=2)+'\n');print('VISIBLE_INSPECTION',json.dumps(value)[:6000],flush=True)
     if kind=='install_policy':
      source=(ROOT/'policy/participant.js').read_text();await page.evaluate('() => {'+source+';globalThis.__ebParticipant=createParticipant(null);return true;}');observer=(ROOT/'policy/observe.js').read_text();active=True
      m.update(policy_sha256=hashlib.sha256(source.encode()).hexdigest(),policy_path='policy/participant.js',authoring_prompt_path='policy/authoring_prompt.md',gate_report_path='policy/gate.json');print('POLICY INSTALLED',m['policy_sha256'],flush=True)
     if kind in ['press','click']:
      if command.get('expected_text')!=text:log('error',action=command,outcome='Navigation cancelled: current visible text changed')
      else:
       if kind=='press':await page.keyboard.press(command['key'])
       else:await page.get_by_role('button',name=command['text'],exact=True).click()
       log('action',observation=obs,action=command,outcome='Agent-directed navigation input delivered')
    if active and obs.get('stimulus'):
     decision=await page.evaluate('o=>globalThis.__ebParticipant.decide(o)',obs)
     if decision:
      due=time.monotonic()+decision['delay_ms']/1000
      while time.monotonic()<due:await asyncio.sleep(min(.01,due-time.monotonic()))
      check=await page.evaluate(observer)
      if check.get('stimulus') and check['stimulus']['presentation']==decision['presentation']:
       await page.keyboard.press(decision['key']);responses+=1;log('action',observation=obs,action=decision,outcome='Policy key delivered through browser')
       if responses%20==0:print('RESPONSES',responses,'ELAPSED',round(time.monotonic()-start),flush=True)
      else:log('error',observation=obs,action=decision,outcome='Stale response cancelled')
    await asyncio.sleep(.02)
  except Exception as error:log('error',outcome=repr(error));m['limitations'].append(repr(error));print('ERROR',repr(error),flush=True)
  m.update(status='completed' if completion else 'partial',ended_at=now(),final_url=page.url,status_reason='Observed terminal task page' if completion else 'Session ended without completion evidence',counts={'policy_response_actions':responses,'events':index})
  try:
   native=await page.evaluate('() => jsPsych.data.get().json()');(ROOT/'data/experiment_data.json').write_text(native);m['data_export']={'status':'available','paths':['data/experiment_data.json'],'reason':'Post-participation read-only native export'}
  except Exception as error:m['data_export']={'status':'unavailable','paths':[],'reason':repr(error)}
  (ROOT/'run.json').write_text(json.dumps(m,indent=2)+'\n');await browser.close();print('FINISHED',m['status'],responses,flush=True)
asyncio.run(main())

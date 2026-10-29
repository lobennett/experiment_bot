import asyncio, datetime, hashlib, json, re, time
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
URL = 'https://deploy.expfactory.org/preview/10/'
POLICY = (ROOT/'policy/participant.js').read_text()
OBSERVE = r'''() => {
 const state=globalThis.__ebVisibleP10||(globalThis.__ebVisibleP10={elements:new WeakMap(),next:1});
 const candidates=Array.from(document.querySelectorAll('div,span,p')).filter(el=>el.children.length===0&&el.checkVisibility()&&/^(red|blue|green)$/i.test(el.innerText.trim())&&parseFloat(getComputedStyle(el).fontSize)>30);
 const el=candidates.length===1?candidates[0]:null;let stimulus=null;
 if(el){if(!state.elements.has(el))state.elements.set(el,state.next++);const r=el.getBoundingClientRect();stimulus={text:el.innerText,color:getComputedStyle(el).color,geometry:{x:r.x,y:r.y,width:r.width,height:r.height},presentation:state.elements.get(el)};}
 return {at:new Date().toISOString(),browser_ms:performance.now(),url:location.href,stimulus,text:document.body.innerText,buttons:Array.from(document.querySelectorAll('button')).filter(e=>e.checkVisibility()&&!e.disabled).map(e=>({text:e.innerText,id:e.id}))};
}'''

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
counter=0
def log(kind, observation=None, action=None, outcome=None, evidence_refs=None, timing=None):
 global counter
 event=dict(index=counter,at=now(),kind=kind,phase_id=None,trial_id=None,observation=observation,action=action,outcome=outcome,evidence_refs=evidence_refs or [],timing=timing)
 with (ROOT/'events.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
 counter+=1

async def main():
 manifest=json.loads((ROOT/'run.json').read_text()); manifest['adapter_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 start=time.monotonic(); last=''; nav_seen=set(); responses=0; stimulus_screens=0; completion=None
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(channel='chrome',headless=True)
  page=await browser.new_page(viewport={'width':1200,'height':1000})
  manifest['browser']['version']=browser.version
  await page.set_content('<p id="probe">Input probe</p><script>document.addEventListener("keydown", e=>document.querySelector("p").textContent=e.key)</script>')
  await page.keyboard.press('Shift')
  assert await page.locator('#probe').inner_text()=='Shift'
  assert await page.evaluate('() => 2+2')==4
  (ROOT/'policy/adapter_gate.json').write_text(json.dumps({'status':'passed','read_only_eval':True,'ordinary_key_delivery':True,'host_wait':True,'policy_sha256':hashlib.sha256((ROOT/'policy/participant.js').read_bytes()).hexdigest(),'input_fixture':'Isolated preflight document before task navigation; Shift key observed in DOM'},indent=2)+'\n')
  print('PREFLIGHT PASSED',flush=True)
  await page.goto(URL,wait_until='domcontentloaded')
  await page.evaluate(POLICY+'\nglobalThis.__ebParticipant=createParticipant(null);')
  try:
   while time.monotonic()-start<720:
    observation=await page.evaluate(OBSERVE)
    if observation['url']!=URL: raise RuntimeError('Unexpected navigation '+observation['url'])
    text=observation['text']; stimulus=observation['stimulus']
    signature=json.dumps([stimulus,text,observation['buttons']],sort_keys=True)
    if signature!=last:
     log('observation',observation=observation,timing={'browser_ms':observation['browser_ms'],'clock':'browser performance.now'})
     last=signature
    if stimulus:
     if stimulus_screens<3:
      await page.screenshot(path=str(ROOT/'evidence'/f'stimulus-{stimulus_screens+1}.png'))
      stimulus_screens+=1
     decision=await page.evaluate('o => globalThis.__ebParticipant.decide(o)',observation)
     if decision:
      current=await page.evaluate(OBSERVE)
      if current['stimulus'] and current['stimulus']['presentation']==decision['presentation'] and current['stimulus']['color']==stimulus['color']:
       before=now(); await page.keyboard.press(decision['key']); responses+=1
       log('action',observation=observation,action=decision,outcome='Browser keyboard input delivered; correctness unknown until export',timing={'delivery_started_at':before,'delivery_ended_at':now(),'clock':'UTC wall clock'})
       if responses%20==0:print('RESPONSES',responses,'ELAPSED',round(time.monotonic()-start),flush=True)
      else:log('error',observation=observation,action=decision,outcome='Stale intended response cancelled')
    else:
     if re.search(r'thank you|experiment is complete|experiment complete|task complete|finished the experiment',text,re.I):
      completion=text;await page.screenshot(path=str(ROOT/'evidence/completion.png'));(ROOT/'evidence/completion.txt').write_text(text);log('completion',observation=observation,evidence_refs=['completion']);print('COMPLETION',text[:700],flush=True);break
     nav_key=json.dumps([text,observation['buttons']],sort_keys=True)
     target=next((b for b in observation['buttons'] if b['text'].strip() in ['Continue','Next >']),None)
     enter=bool(re.search(r'press\s+enter',text,re.I))
     if (target or enter) and nav_key not in nav_seen:
      nav_seen.add(nav_key);name=f'boundary-{len(nav_seen):02d}';(ROOT/'evidence'/f'{name}.txt').write_text(text);await page.screenshot(path=str(ROOT/'evidence'/f'{name}.png'))
      print('BOUNDARY',name,json.dumps(text[:1200]),flush=True)
      await asyncio.sleep(2)
      current=await page.evaluate(OBSERVE)
      if current['text']!=text:continue
      if target: await page.get_by_role('button',name=target['text'],exact=True).click();log('action',action={'type':'click','text':target['text']},outcome='Navigation input delivered')
      elif enter:await page.keyboard.press('Enter');log('action',action={'type':'key','key':'Enter'},outcome='Navigation input delivered')
    await asyncio.sleep(.02)
  except Exception as error:
   log('error',outcome=str(error));print('ERROR',repr(error),flush=True);manifest['limitations'].append(str(error))
  manifest.update(status='completed' if completion else 'partial',ended_at=now(),status_reason='Observed terminal page' if completion else 'Stopped without confirmed completion',final_url=page.url)
  try:
   native=await page.evaluate('() => jsPsych.data.get().json()')
   (ROOT/'data/experiment_data.json').write_text(native)
   manifest['data_export']={'status':'available','paths':['data/experiment_data.json'],'reason':'Post-participation read-only jsPsych native export'}
  except Exception as error:manifest['data_export']={'status':'unavailable','paths':[],'reason':str(error)}
  manifest['counts']={'policy_response_actions':responses,'agent_events':counter}
  (ROOT/'run.json').write_text(json.dumps(manifest,indent=2)+'\n')
  await browser.close()
  print('FINISHED',manifest['status'],responses,flush=True)

asyncio.run(main())

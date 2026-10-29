import sys,json,time,datetime,hashlib,traceback,select
from pathlib import Path
from playwright.sync_api import sync_playwright
R=Path(__file__).resolve().parents[1]
URL='https://deploy.expfactory.org/preview/5/'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
ix=0
def event(kind,obs=None,action=None,outcome=None,evidence_refs=None):
 global ix
 ix+=1
 e={'index':ix,'at':now(),'kind':kind,'phase_id':None,'trial_id':None,'observation':obs,'action':action,'outcome':outcome,'evidence_refs':evidence_refs or [],'timing':{'clock':'system UTC and browser performance.now','not_native_rt':True}}
 with (R/'events.jsonl').open('a') as f:f.write(json.dumps(e)+'\n')
 return e
OBSERVER='''() => {
 const ids=new WeakMap(); let next=0;
 function visible(el,rect){
   for(let e=el;e;e=e.parentElement){const s=getComputedStyle(e);if(s.display==='none'||s.visibility!=='visible'||Number(s.opacity)===0)return false;}
   if(!rect||rect.width<=0||rect.height<=0||rect.bottom<=0||rect.right<=0||rect.top>=innerHeight||rect.left>=innerWidth)return false;
   const x=Math.max(0,Math.min(innerWidth-1,rect.x+rect.width/2)),y=Math.max(0,Math.min(innerHeight-1,rect.y+rect.height/2));
   const top=document.elementFromPoint(x,y); return !!top&&(top===el||top.contains(el)||el.contains(top));
 }
 return () => {
   const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT); const parts=[];let n;
   while(n=walker.nextNode()) {const txt=n.textContent.trim();if(!txt)continue;const el=n.parentElement;if(!el||['SCRIPT','STYLE','NOSCRIPT'].includes(el.tagName))continue;
     const range=document.createRange();range.selectNodeContents(n);const rect=range.getBoundingClientRect();if(!visible(el,rect))continue;
     if(!ids.has(n))ids.set(n,++next);
     parts.push({text:txt,token:ids.get(n),rect:{x:rect.x,y:rect.y,width:rect.width,height:rect.height},tag:el.tagName});
   }
   const buttons=[...document.querySelectorAll('button,input[type=button],input[type=submit]')].filter(el=>visible(el,el.getBoundingClientRect())).map(el=>({text:el.innerText||el.value,disabled:el.disabled}));
   return {url:location.href,title:document.title,at_browser_ms:performance.now(),parts,text:parts.map(p=>p.text).join(' '),buttons,viewport:{width:innerWidth,height:innerHeight}};
 };
}'''
pw=sync_playwright().start();browser=pw.chromium.launch(headless=True);context=browser.new_context(viewport={'width':1280,'height':900});page=context.new_page()
page.goto(URL);handle=page.evaluate_handle(OBSERVER)
policy=None
last=None
start=time.monotonic()
def observe():
 global last
 o=handle.evaluate('(read)=>read()'); o['observed_at']=now()
 if o['url']!=URL:raise RuntimeError('URL changed: '+o['url'])
 signature=json.dumps([o['text'],[p['token'] for p in o['parts']]])
 if signature!=last:
  event('observation',o);last=signature
 return o
def capture(label):
 o=observe();name='evidence/'+label
 (R/(name+'.json')).write_text(json.dumps(o,indent=2));page.screenshot(path=str(R/(name+'.png')))
 print(json.dumps({'capture':label,'observation':o}),flush=True)
def command(c):
 global policy,handle
 op=c['op']
 if op=='observe':capture(c.get('label','capture'))
 elif op=='click':
  o=observe();target=c['text'];assert any(b['text']==target and not b['disabled'] for b in o['buttons']),o
  page.get_by_role('button',name=target,exact=True).click();event('action',action={'type':'click','target':target},outcome='delivered');capture(c.get('label','after-click'))
 elif op=='key':
  o=observe();page.keyboard.press(c['key']);event('action',obs=o,action={'type':'key','value':c['key'],'issuer':'agent'},outcome='delivered');capture(c.get('label','after-key'))
 elif op=='start':
  from participant import Participant
  if policy is None:policy=Participant(5)
  limit=time.monotonic()+c.get('seconds',1200);last_progress=0
  while time.monotonic()<limit:
   if select.select([sys.stdin],[],[],0)[0]:
    stop=sys.stdin.readline().strip()
    if stop:print(json.dumps({'interrupt':stop}),flush=True);break
   o=observe();a=policy.decide(o)
   if a['type']=='review':capture('review-'+str(ix));break
   if a['type']=='key':
    fresh=observe()
    if a['token'] not in [p['token'] for p in fresh['parts']]:event('error',obs=fresh,action=a,outcome='stale action cancelled');continue
    event('action',obs=o,action={**a,'issuer':'policy','delivery':'intended'})
    page.keyboard.press(a['key']);event('action',action={**a,'issuer':'policy','delivery':'actual'},outcome='delivered')
   if time.monotonic()-last_progress>10:print(json.dumps({'progress':True,'events':ix,'policy_responses':policy.responses,'text':o['text']}),flush=True);last_progress=time.monotonic()
   time.sleep(.02)
  else: print(json.dumps({'operational_limit':'loop time limit'}),flush=True)
 elif op=='export':
  (R/'data/experiment_data.json').write_text(page.evaluate('jsPsych.data.get().json()'))
  (R/'evidence/export-metadata.json').write_text(json.dumps({'at':now(),'version':page.evaluate('jsPsych.version()'),'api':'jsPsych.data.get().json()','documentation':'https://www.jspsych.org/v7/reference/jspsych-data/'},indent=2))
  print(json.dumps({'exported':True}),flush=True)
 elif op=='fixtures':
  f=context.new_page();f.set_content('<div style="position:absolute;left:10px;top:10px">VISIBLE</div><div style="display:none">DISPLAY</div><div style="visibility:hidden">VISIBILITY</div><div style="opacity:0">OPACITY</div><div style="position:absolute;top:2000px">OFFSCREEN</div><div style="position:absolute;left:10px;top:100px">OCCLUDED</div><div style="position:absolute;left:0;top:95px;width:200px;height:50px;background:black"></div>');h=f.evaluate_handle(OBSERVER);o=h.evaluate('(read)=>read()');assert o['text']=='VISIBLE',o;f.close();(R/'policy/adapter-fixtures.json').write_text(json.dumps({'passed':True,'observation':o,'checked':['visible','display:none','visibility:hidden','opacity:0','offscreen','occluded']},indent=2));print(json.dumps({'fixtures':'passed'}),flush=True)
 elif op=='end':return False
 return True
capture('001-initial')
for line in sys.stdin:
 try:
  if not command(json.loads(line)):break
 except Exception as e:
  event('error',outcome=repr(e));print(json.dumps({'error':repr(e),'traceback':traceback.format_exc()}),flush=True)
browser.close();pw.stop()

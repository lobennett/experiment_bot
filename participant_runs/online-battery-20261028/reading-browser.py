import asyncio,datetime,hashlib,json,pathlib,sys,time,shutil
from playwright.async_api import async_playwright
BASE=pathlib.Path(__file__).resolve().parent
P=BASE/'self-paced-reading'/'attempt-03'
URL='https://www.psytoolkit.org/library/experiment_pacedreading1.html'
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
async def main():
    P.mkdir(parents=True,exist_ok=True);(P/'evidence').mkdir(exist_ok=True)
    skill=pathlib.Path('skills/behavioral-participant').resolve()
    (P/'protocol').mkdir(exist_ok=True)
    for f in skill.glob('*.md'):shutil.copy2(f,P/'protocol'/f.name)
    skill=P/'protocol'
    m=dict(schema_version='1.0',run_id='self-paced-reading-attempt-03',mode='direct_browser',input_url=URL,final_url=URL,started_at=now(),ended_at=None,status='running',status_reason='Mechanical transport change: persistent browser, frame-synchronized canvas screenshots, defer analysis between words.',model={'provider':'OpenAI','model':None,'version':None},browser={'tool':'Playwright ordinary mouse/keyboard input','session':'eb-other-pointer','viewport':{'width':1200,'height':900}},observation_boundary='participant_visible',skill_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in skill.iterdir() if f.is_file()},seed=None,reproducibility='Direct model participation; no deterministic replay claim.',completion_evidence_refs=[],data_export={'status':'not_attempted','paths':[],'reason':None},counts={},limitations=['Second attempt reduces observation/input transport overhead; previous completed session retained with missed observations.'],artifacts_sha256={})
    (P/'run.json').write_text(json.dumps(m,indent=2)+'\n')
    (P/'ontology.json').write_text(json.dumps(dict(schema_version='1.0',task={'url':URL,'title':'Self-paced reading'},nodes=[],relations=[],evidence=[],unknowns=[]),indent=2)+'\n')
    (P/'summary.md').write_text('# Run in progress\n')
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(channel='chrome',headless=True)
        page=await browser.new_page(viewport={'width':1200,'height':900})
        await page.goto(URL)
        index=0
        while True:
            if index==0: command={'action':'observe'}
            else:
                line=await asyncio.to_thread(sys.stdin.readline)
                if not line:break
                command=json.loads(line)
            at=now(); tick=time.perf_counter(); act=command['action'];err=None
            try:
                if act=='click':await page.mouse.click(*command['xy'])
                elif act=='click_text':await page.get_by_role('button',name=command['text'],exact=True).click()
                elif act=='key':await page.keyboard.press(command['key'])
                elif act=='drag':
                    await page.mouse.move(*command['from']);await page.mouse.down();await page.mouse.move(*command['to'],steps=10);await page.mouse.up()
                elif act=='export':
                    vals=await page.locator('table').evaluate_all('(els)=>els.filter(el=>el.checkVisibility()).map(el=>el.innerText)')
                    (P/'data').mkdir(exist_ok=True)
                    for n,v in enumerate(vals):(P/'data'/f'export-{n}.txt').write_text(v)
                    print('EXPORT_COUNT',len(vals),flush=True)
                elif act=='finish':break
            except Exception as ex:err=str(ex)
            label=f'{index:03}_{act}';text=await page.locator('body').inner_text()
            png=P/'evidence'/f'{label}.png';txt=P/'evidence'/f'{label}.txt'
            await page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
            if await page.locator('canvas').count() and await page.locator('canvas').is_visible():await page.locator('canvas').screenshot(path=str(png))
            else:await page.screenshot(path=str(png))
            txt.write_text(text)
            o=json.loads((P/'ontology.json').read_text())
            for suffix,file,typ in [('image',png,'screenshot'),('text',txt,'visible_text')]:
                o['evidence'].append(dict(id=label+'_'+suffix,path=str(file.relative_to(P)),locator='whole screen',source_type=typ,observed_at=at,description='Participant-visible browser state after '+act))
            (P/'ontology.json').write_text(json.dumps(o,indent=2)+'\n')
            ev=dict(index=index,at=at,kind='observation' if act in ['observe','export'] else 'action',phase_id=None,trial_id=None,observation=command.get('observation'),action=command if act!='observe' else None,outcome=err or text or 'Canvas visible; consult screenshot.',evidence_refs=[label+'_image',label+'_text'],timing={'transport_ms':(time.perf_counter()-tick)*1000,'clock':'time.perf_counter','not_native_rt':True})
            with (P/'events.jsonl').open('a') as f:f.write(json.dumps(ev)+'\n')
            print(json.dumps({'index':index,'error':err,'visible_text':text,'screenshot':str(png),'transport_ms':ev['timing']['transport_ms']}),flush=True)
            index+=1
        await browser.close()
asyncio.run(main())

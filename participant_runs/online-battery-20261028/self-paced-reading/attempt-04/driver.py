import asyncio,datetime,hashlib,importlib.util,json,pathlib,shutil,time
from playwright.async_api import async_playwright

P=pathlib.Path(__file__).resolve().parent
URL='https://www.psytoolkit.org/library/experiment_pacedreading1.html'
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
spec=importlib.util.spec_from_file_location('participant',P/'policy/participant.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

async def main():
    skill=pathlib.Path('skills/behavioral-participant').resolve()
    for f in skill.glob('*.md'):shutil.copy2(f,P/'protocol'/f.name)
    gate=json.loads((P/'policy/gate.json').read_text());assert gate['passed'] and digest(P/'policy/participant.py')==gate['policy_sha256']
    m=dict(schema_version='1.0',run_id='self-paced-reading-attempt-04',mode='generated_visible_policy',input_url=URL,final_url=URL,started_at=now(),ended_at=None,status='running',status_reason='Frozen pixel-OCR participant policy, first mechanically passing candidate.',model={'provider':'OpenAI','model':None,'version':None},browser={'tool':'Playwright plus macOS Vision OCR of screenshots','session':'eb-other-ocr','viewport':{'width':1200,'height':900},'input':'ordinary keyboard press/release'},observation_boundary='participant_visible',skill_sha256={f.name:digest(f) for f in (P/'protocol').iterdir() if f.is_file()},seed=17,seed_scope='policy constructor; policy makes no random choices',reproducibility='Pinned deterministic policy and code; live browser environment is not deterministically replayable.',completion_evidence_refs=[],data_export={'status':'not_attempted','paths':[],'reason':None},counts={},limitations=['Policy receives OCR text from current rendered pixels; live responses are generated-program decisions, not per-word LLM comprehension.','Inline authoring inherited conversation context; does not claim frozen-study prompt isolation.'],artifacts_sha256={},policy_sha256=gate['policy_sha256'],policy_path='policy/participant.py',authoring_prompt_path='policy/authoring-prompt.md',gate_report_path='policy/gate.json',parent_attempt='../attempt-03',operational_limits={'max_runtime_seconds':600})
    o=dict(schema_version='1.0',task={'url':URL,'title':'Self-paced reading'},nodes=[],relations=[],evidence=[],unknowns=[])
    (P/'run.json').write_text(json.dumps(m,indent=2)+'\n');(P/'summary.md').write_text('# OCR-policy run in progress\n')
    index=0;decision_count=0;participant=module.make_participant(17);last_phase=None
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(channel='chrome',headless=True)
        page=await browser.new_page(viewport={'width':1200,'height':900})
        await page.goto(URL)

        async def observe(label):
            at=now();tick=time.perf_counter();png=P/'evidence'/f'{label}.png'
            await page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
            if await page.locator('canvas').count() and await page.locator('canvas').is_visible():await page.locator('canvas').screenshot(path=str(png))
            else:await page.screenshot(path=str(png))
            proc=await asyncio.create_subprocess_exec(str(P/'ocr'),str(png),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            stdout,stderr=await proc.communicate()
            if proc.returncode:raise RuntimeError(stderr.decode())
            blocks=json.loads(stdout);text=' '.join(x['text'] for x in blocks)
            rec={'at':at,'text':text,'blocks':blocks,'frame_id':digest(png),'capture_and_ocr_ms':(time.perf_counter()-tick)*1000}
            op=P/'evidence'/f'{label}.json';op.write_text(json.dumps(rec,indent=2)+'\n')
            refs=[]
            for suffix,path,typ in [('image',png,'screenshot'),('ocr',op,'visible_text')]:
                eid=label+'_'+suffix;refs.append(eid);o['evidence'].append(dict(id=eid,path=str(path.relative_to(P)),locator='whole captured visible surface',source_type=typ,observed_at=at,description='Rendered pixels' if typ=='screenshot' else 'Local OCR of corresponding screenshot; no task internals'))
            return rec,refs

        initial,refs=await observe('000_preflight')
        assert 'click to start' in initial['text'].lower(),initial
        (P/'adapter-gate.json').write_text(json.dumps({'passed':True,'visible_initial_control':'Click to start','capture_and_ocr_ms':initial['capture_and_ocr_ms'],'ocr_evidence':refs,'observation_input':'current screenshot pixels','canvas_visibility_check':True},indent=2)+'\n')
        await page.get_by_role('button',name='Click to start',exact=True).click()
        with (P/'events.jsonl').open('a') as f:f.write(json.dumps(dict(index=index,at=now(),kind='action',phase_id='initial',trial_id=None,observation=initial['text'],action={'kind':'navigation_click','text':'Click to start'},outcome='Normal browser click completed',evidence_refs=refs,timing=None))+'\n')
        index+=1;started=time.monotonic()
        while time.monotonic()-started<600:
            obs,refs=await observe(f'{index:03}_frame');action=participant.respond(obs)
            event=dict(index=index,at=obs['at'],kind='observation',phase_id=None,trial_id=None,observation=obs['text'],action=action,outcome=None,evidence_refs=refs,timing={'capture_and_ocr_ms':obs['capture_and_ocr_ms'],'not_native_rt':True})
            if action['kind']=='key':
                await page.keyboard.press(action['key']);decision_count+=1;event['kind']='action';event['outcome']='Normal browser key press/release delivered'
                print(json.dumps({'event':index,'observed':obs['text'],'key':action['key'],'words_observed':len(participant.words)}),flush=True)
            elif action['kind']=='done':
                m['status']='completed';m['status_reason']='Frozen OCR policy observed terminal export controls.';m['completion_evidence_refs']=refs;event['kind']='completion';event['outcome']='Native export controls observed'
            elif action['kind']=='unknown':
                m['status']='partial';m['status_reason']='Unknown nonempty screen requires agent review: '+obs['text'];event['outcome']='Stopped without guessing input'
            with (P/'events.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
            (P/'ontology.json').write_text(json.dumps(o,indent=2)+'\n');index+=1
            if action['kind'] in ['done','unknown']:break
        else:m['status']='partial';m['status_reason']='Operational runtime limit reached'
        if m['status']=='completed':
            await page.get_by_role('button',name='Show data',exact=True).click()
            table=await page.locator('table').inner_text();(P/'data').mkdir(exist_ok=True);(P/'data/native-export.tsv').write_text(table)
            final,refs=await observe(f'{index:03}_native_export')
            m['data_export']={'status':'available','paths':['data/native-export.tsv'],'reason':'Exact visible table innerText after completion and normal Show data click.'}
            o['evidence'].append(dict(id='native_export',path='data/native-export.tsv',locator='all rows',source_type='native_export',observed_at=now(),description='Native visible table exported only after completion.'))
        m['ended_at']=now();m['counts']={'events':index,'policy_key_actions':decision_count,'observed_word_displays':len(participant.words)};m['observed_words_path']='observed-words.json'
        (P/'observed-words.json').write_text(json.dumps(participant.words,indent=2)+'\n');(P/'run.json').write_text(json.dumps(m,indent=2)+'\n');(P/'ontology.json').write_text(json.dumps(o,indent=2)+'\n')
        await browser.close();print(json.dumps({'status':m['status'],'word_observations':len(participant.words),'reason':m['status_reason']}),flush=True)

asyncio.run(main())

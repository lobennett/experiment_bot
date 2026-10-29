import datetime, hashlib, json, os, pathlib, subprocess, sys, time, shutil
BASE=pathlib.Path(__file__).resolve().parent
slug,label,*args=sys.argv[1:]
p=BASE/slug/'attempt-01'; p.mkdir(parents=True,exist_ok=True); (p/'evidence').mkdir(exist_ok=True)
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
if not (p/'run.json').exists():
    skill=pathlib.Path('skills/behavioral-participant').resolve()
    (p/'protocol').mkdir(exist_ok=True)
    for f in skill.glob('*.md'):shutil.copy2(f,p/'protocol'/f.name)
    m=dict(schema_version='1.0',run_id=slug+'-attempt-01',mode='direct_browser',input_url=args[1] if args[0]=='open' else None,final_url=None,started_at=now(),ended_at=None,status='running',status_reason='Live browser evaluation started.',model={'provider':'OpenAI','model':None,'version':None},browser={'tool':'chrome-devtools-axi','session':'eb-other'},observation_boundary='participant_visible',skill_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (p/'protocol').iterdir() if f.is_file()},seed=None,reproducibility='Direct model participation; no deterministic replay claim.',completion_evidence_refs=[],data_export={'status':'not_attempted','paths':[],'reason':None},counts={},limitations=[],artifacts_sha256={})
    (p/'run.json').write_text(json.dumps(m,indent=2)+'\n')
    (p/'ontology.json').write_text(json.dumps(dict(schema_version='1.0',task={'url':m['input_url'],'title':None},nodes=[],relations=[],evidence=[],unknowns=[]),indent=2)+'\n')
    (p/'summary.md').write_text('# Run in progress\n')
at=now(); start=time.monotonic()
r=subprocess.run(['/Users/lobennett/.local/bin/chrome-devtools-axi',*args],env={**os.environ,'CHROME_DEVTOOLS_AXI_SESSION':'eb-other'},capture_output=True,text=True)
duration=(time.monotonic()-start)*1000
out=r.stdout+r.stderr
f=p/'evidence'/f'{label}.txt';f.write_text(out)
o=json.loads((p/'ontology.json').read_text()); eid='e_'+label
o['evidence'].append(dict(id=eid,path=str(f.relative_to(p)),locator='full tool snapshot',source_type='visible_text',observed_at=at,description='Browser '+args[0]+' result'))
if args[0]=='screenshot' and pathlib.Path(args[1]).exists():
    sf=pathlib.Path(args[1]).resolve()
    o['evidence'].append(dict(id=eid+'_image',path=str(sf.relative_to(p)),locator='whole screenshot',source_type='screenshot',observed_at=at,description='Participant-visible screen'))
elif args[0] in ['open','click','press','resize'] and r.returncode==0:
    sf=p/'evidence'/f'{label}.png'
    shot=subprocess.run(['/Users/lobennett/.local/bin/chrome-devtools-axi','screenshot',str(sf)],env={**os.environ,'CHROME_DEVTOOLS_AXI_SESSION':'eb-other'},capture_output=True,text=True)
    if sf.exists():
        o['evidence'].append(dict(id=eid+'_image',path=str(sf.relative_to(p)),locator='whole screenshot',source_type='screenshot',observed_at=now(),description='Participant-visible screen'))
        print('Screenshot:',sf)
(p/'ontology.json').write_text(json.dumps(o,indent=2)+'\n')
ep=p/'events.jsonl';idx=len(ep.read_text().splitlines()) if ep.exists() else 0
ev=dict(index=idx,at=at,kind='action' if args[0] in ['click','press','drag','fill','type','run'] else 'observation',phase_id=None,trial_id=None,observation=None,action={'tool':args[0],'arguments':args[1:]} if args[0] in ['click','press','drag','fill','type','run'] else None,outcome='Browser tool exit '+str(r.returncode),evidence_refs=[eid],timing={'tool_duration_ms':duration,'clock':'time.monotonic','not_native_rt':True})
with ep.open('a') as h:h.write(json.dumps(ev)+'\n')
print(out,end='');sys.exit(r.returncode)

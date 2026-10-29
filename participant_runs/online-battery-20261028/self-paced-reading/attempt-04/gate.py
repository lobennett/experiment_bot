import hashlib,importlib.util,json,pathlib,subprocess,time
P=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('participant',P/'policy/participant.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
fixtures=[('Mary','key','n'),('cooked','key','n'),('A self-paced reading task. Press space to continue.','key','Space'),('Press the n key to start see the first word. Then press the n key each time for the following words.','key','n'),('Well done...just wait until next sentence','wait',None),('Show data Copy data to clipboard','done',None),('An unexpected instruction screen','unknown',None)]
def trace():
 p=mod.make_participant(17);out=[]
 for i,(text,kind,key) in enumerate(fixtures):
  obs={'text':text,'frame_id':str(i)};r=p.respond(obs);assert r['kind']==kind,(text,r)
  if key:assert r['key']==key
  out.append(r)
 return out
tick=time.perf_counter();a=trace();b=trace();assert a==b
p=mod.make_participant(17);obs={'text':'Mary','frame_id':'same'};assert p.respond(obs)['kind']=='key';assert p.respond(obs)['kind']=='wait'
ocr=[]
for filename,expected in [('05_word.png','Mary'),('06_word.png','cooked'),('07_word.png','dinner')]:
 path=P.parent/'attempt-01/evidence'/filename;t=time.perf_counter();r=json.loads(subprocess.check_output([str(P/'ocr'),str(path)],text=True));text=' '.join(x['text'] for x in r);assert text==expected,(filename,text)
 ocr.append({'file':str(path.relative_to(P.parent.parent)),'recognized':text,'duration_ms':(time.perf_counter()-t)*1000,'source':'saved screenshot pixels'})
report={'passed':True,'candidate':1,'interface_cases':len(fixtures),'deterministic_same_seed':True,'randomness':'none; no distinct-seed assertion applicable','duplicate_frame_suppressed':True,'bounded_policy_trace_ms':(time.perf_counter()-tick)*1000,'ocr_fixture_checks':ocr,'policy_sha256':hashlib.sha256((P/'policy/participant.py').read_bytes()).hexdigest()}
(P/'policy/gate.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

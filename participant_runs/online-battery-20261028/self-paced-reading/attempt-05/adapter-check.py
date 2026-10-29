import hashlib,json,pathlib,subprocess,time
P=pathlib.Path(__file__).resolve().parent
old=P.parent/'attempt-04'
assert hashlib.sha256((P/'policy/participant.py').read_bytes()).hexdigest()==json.loads((P/'policy/gate.json').read_text())['policy_sha256']
fixtures={}
for f in sorted((old/'evidence').glob('*_frame.json')):
    r=json.loads(f.read_text());text=r['text']
    if text and 'Show data' not in text:fixtures.setdefault(text,f.with_suffix('.png'))
fixtures['is']=old/'evidence/053_frame.png'
fixtures['']=P.parent.parent/'tower-hanoi/attempt-02/evidence/001_click_text.png'
results=[]
for expected,path in fixtures.items():
    tick=time.perf_counter();r=json.loads(subprocess.check_output([str(P/'ocr'),str(path)],text=True));actual=' '.join(x['text'] for x in r)
    results.append({'source':str(path.relative_to(P.parent.parent)),'expected_from_saved_pixels':expected,'recognized':actual,'passed':actual==expected,'duration_ms':(time.perf_counter()-tick)*1000})
report={'passed':all(x['passed'] for x in results),'policy_unchanged':True,'repair':'Full-frame OCR returned no text for visibly present short word. Fall back to the observed canvas word band only when full-frame OCR is empty. No supplied word/answer vocabulary.','fixtures':results}
(P/'adapter-check.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'passed':report['passed'],'fixture_count':len(results),'failures':[x for x in results if not x['passed']]}))
assert report['passed']

import datetime, json, os, pathlib, subprocess, sys, time
p=pathlib.Path(__file__).parent
env=dict(os.environ,CHROME_DEVTOOLS_AXI_SESSION='eb-preview9')
cli='/Users/lobennett/.local/bin/chrome-devtools-axi'
code=(p/'policy/participant.js').read_text()+'\n'+(p/'policy/segment.js').read_text()
start_enter='--enter' in sys.argv
if start_enter:
    code=code.replace("let presses=0, observations=0;","const navigationText = await page.eval('() => document.body.innerText');\nif (/Press\\s+enter/i.test(navigationText)) { await page.press('Enter'); console.log(JSON.stringify({type:'navigation',key:'Enter',observed_text:navigationText})); }\nlet presses=0, observations=0;",1)
for i in range(30):
    existing=sorted((p/'evidence').glob('segment-*.jsonl'))
    n=len(existing)+1
    script=p/'policy'/f'executed-segment-{n:03d}.js';script.write_text(code)
    started=datetime.datetime.now(datetime.timezone.utc).isoformat();tick=time.monotonic()
    r=subprocess.run([cli,'run'],input=code,env=env,text=True,capture_output=True)
    path=p/'evidence'/f'segment-{n:03d}.jsonl';path.write_text(r.stdout)
    if r.stderr:(p/'evidence'/f'segment-{n:03d}.stderr.txt').write_text(r.stderr)
    parsed=[]
    for line in r.stdout.splitlines():
        try:parsed.append(json.loads(line))
        except json.JSONDecodeError:pass
    event_path=p/'events.jsonl';idx=len(event_path.read_text().splitlines())+1 if event_path.exists() else 1
    with event_path.open('a') as f:f.write(json.dumps({'index':idx,'at':started,'kind':'observation','phase_id':None,'trial_id':None,'observation':{'segment':n,'records':len(parsed)},'action':{'type':'bounded_policy_segment','script':str(script.relative_to(p))},'outcome':{'exit_code':r.returncode},'evidence_refs':[f'segment_{n:03d}'],'timing':{'clock':'host monotonic','tool_duration_seconds':time.monotonic()-tick}})+'\n')
    boundary=next((x for x in parsed if x.get('type')=='boundary'),None)
    print(json.dumps({'segment':n,'exit_code':r.returncode,'records':len(parsed),'deliveries':sum(x.get('type')=='delivery' for x in parsed),'boundary':boundary}),flush=True)
    if r.returncode or boundary:break
    code=(p/'policy/participant.js').read_text()+'\n'+(p/'policy/segment.js').read_text()

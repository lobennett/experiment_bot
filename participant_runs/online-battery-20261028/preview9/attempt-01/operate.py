import datetime, hashlib, json, os, pathlib, subprocess, sys, time
p = pathlib.Path(__file__).parent
args = sys.argv[1:]
label = args.pop(0)
now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
start = now(); tick = time.monotonic()
env = dict(os.environ, CHROME_DEVTOOLS_AXI_SESSION='eb-preview9')
r = subprocess.run(['/Users/lobennett/.local/bin/chrome-devtools-axi', *args], env=env, capture_output=True, text=True)
elapsed = time.monotonic()-tick
path = p/'evidence'/f'{label}.txt'
path.write_text(r.stdout + ('\nSTDERR:\n'+r.stderr if r.stderr else ''))
events = p/'events.jsonl'
index = len(events.read_text().splitlines())+1 if events.exists() else 1
entry = {'index':index,'at':start,'kind':'action' if args[0] in ['click','press','fill','type','open'] else 'observation','phase_id':None,'trial_id':None,'observation':None,'action':{'tool': 'chrome-devtools-axi','arguments':args},'outcome':{'exit_code':r.returncode},'evidence_refs':[label],'timing':{'tool_duration_seconds':elapsed,'clock':'python monotonic','recorded_at_source':'UTC wall clock'}}
with events.open('a') as f: f.write(json.dumps(entry)+'\n')
print(json.dumps({'label':label,'duration_seconds':elapsed,'exit_code':r.returncode}))
print(r.stdout)
if r.stderr: print(r.stderr)

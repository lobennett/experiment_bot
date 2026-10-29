import datetime,json,os,pathlib,subprocess,sys,time
p=pathlib.Path(__file__).resolve().parent
label=sys.argv[1]; args=sys.argv[2:]
env=dict(os.environ,CHROME_DEVTOOLS_AXI_SESSION='eb-preview10')
at=datetime.datetime.now(datetime.timezone.utc).isoformat(); start=time.monotonic()
script_input = pathlib.Path(args[1]).read_text() if args[0] == 'run-file' else None
command_args = ['run'] if script_input is not None else args
r=subprocess.run(['/Users/lobennett/.local/bin/chrome-devtools-axi',*command_args],input=script_input,env=env,capture_output=True,text=True)
elapsed=time.monotonic()-start
out=r.stdout+('\nSTDERR:\n'+r.stderr if r.stderr else '')
(p/'evidence'/f'{label}.txt').write_text(out)
with (p/'events.jsonl').open('a') as f:
    index=sum(1 for _ in (p/'events.jsonl').open())
    f.write(json.dumps({'index':index,'at':at,'kind':'action' if args[0] in ('click','press','fill','type') else 'observation','phase_id':None,'trial_id':None,'observation':None,'action':{'command':args} if args[0] in ('click','press','fill','type') else None,'outcome':{'returncode':r.returncode,'capture':f'evidence/{label}.txt'},'evidence_refs':[label],'timing':{'tool_duration_s':elapsed,'clock':'Python monotonic wall duration'}})+'\n')
print(out);print(json.dumps({'duration_s':elapsed,'returncode':r.returncode}))
sys.exit(r.returncode)

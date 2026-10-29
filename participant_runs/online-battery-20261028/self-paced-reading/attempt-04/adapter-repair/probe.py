import json,pathlib,subprocess,time
p=pathlib.Path(__file__).resolve().parent
out=[]
for name in ["ocr-fast","ocr-language","ocr-crop"]:
 t=time.monotonic()
 r=subprocess.run([str(p/name),str(p.parent/"evidence/053_frame.png")],capture_output=True,text=True)
 out.append({"adapter":name,"recognized":json.loads(r.stdout) if r.returncode==0 else r.stderr,"duration_ms":(time.monotonic()-t)*1000,"exit_code":r.returncode})
(p/"probe-results.json").write_text(json.dumps(out,indent=2)+"\n")
print(json.dumps(out))

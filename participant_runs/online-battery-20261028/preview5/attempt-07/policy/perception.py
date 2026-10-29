import json,re,hashlib
from pathlib import Path
RULES=Path(__file__).with_name('adapter-rules.json')
def project(o):
 raw=RULES.read_bytes();rules=json.loads(raw)
 text=' '.join(p['text'] for p in o['parts'] if not any(re.fullmatch(pattern,p['text']) for pattern in rules['reminder_patterns']))
 facts=[]
 for pattern in rules['cue_patterns']:
  match=re.search(pattern,o['text'],re.I)
  if match:
   fact='Your delay is '+match.group(1)+'.'
   text=fact+' '+text;facts.append({'source_text':match.group(0),'equivalent_text':fact})
 return {**o,'text':text,'perception_projection':{'rules_sha256':hashlib.sha256(raw).hexdigest(),'normalized_facts':facts,'text':text}}

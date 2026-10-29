import datetime,difflib,hashlib,json,pathlib,statistics,sys
P=pathlib.Path(sys.argv[1]).resolve()
m=json.loads((P/'run.json').read_text());o=json.loads((P/'ontology.json').read_text())
rows=[s.split('\t') for s in (P/'data/native-export.tsv').read_text().splitlines()]
expected=[w for r in rows for w in r[2].strip('"').split()]
observed=json.loads((P/'observed-words.json').read_text())
matched=sum(b.size for b in difflib.SequenceMatcher(a=expected,b=observed,autojunk=False).get_matching_blocks())
times=[int(v) for r in rows for v in r[3:]]
metrics=dict(native_sentence_rows=len(rows),native_word_intervals=len(times),recognized_word_observations=len(observed),sequence_matched_words=matched,all_words_match=expected==observed,intervals_equal_9999ms=times.count(9999),native_interval_min_ms=min(times),native_interval_median_ms=statistics.median(times),native_interval_max_ms=max(times),expected_native_words=expected,recognized_visible_words=observed)
(P/'coverage.json').write_text(json.dumps(metrics,indent=2)+'\n')
events=[json.loads(s) for s in (P/'events.jsonl').read_text().splitlines()]
def ref_containing(text):
 return next(e['evidence_refs'][0] for e in events if text.lower() in e.get('observation','').lower())
intro=ref_containing('self-paced');ready=ref_containing('following words');feedback=ref_containing('Well done');word=next(e['evidence_refs'][0] for e in events if e.get('observation') in observed);end=m['completion_evidence_refs'][0]
def n(i,k,l,a,r,status='observed'):return dict(id=i,kind=k,label=l,attributes=a,status=status,evidence_refs=[r])
o['nodes']=[n('intro','phase','Self-paced reading task',{},intro),n('ready','phase','Sentence-start instructions',{},ready),n('word','stimulus','Single visible word on canvas',{'recognized_count':len(observed)},word),n('advance','response','n key',{},ready),n('intro_key','response','Space key',{},intro),n('sequence','sequence','Word-by-word sentence',{'sentence_rows':len(rows),'word_count':len(times)},'native_export'),n('feedback','feedback','Wait until next sentence',{},feedback),n('end','completion','Native export controls',{},end)]
o['relations']=[dict(subject=a,predicate=b,object=c,status='observed',evidence_refs=[d]) for a,b,c,d in [('intro','accepts','intro_key',intro),('ready','specifies','advance',ready),('sequence','presents','word',word),('advance','advances','word',ready),('sequence','followed_by','feedback',feedback),('sequence','eventually_ends_with','end',end)]]
o['unknowns']=[{'question':'Does this represent human reading or comprehension?','reason':'Local OCR and a frozen procedural policy executed the responses; no human behavioral comparison or comprehension question was supplied.'}]
if matched<len(expected):o['unknowns'].append({'question':'Why was a word not recognized?','reason':'Saved screenshots and OCR output document the observation adapter limitation; see summary.'})
(P/'ontology.json').write_text(json.dumps(o,indent=2)+'\n')
m['counts'].update(native_export_trial_rows=len(rows),native_export_word_intervals=len(times),sequence_matched_words=matched,native_intervals_equal_9999ms=times.count(9999))
m['adapter_sha256']={f:hashlib.sha256((P/f).read_bytes()).hexdigest() for f in ['driver.py','ocr.swift','ocr']}
m['limitations']+=['OCR timing and input transport contribute to native response times; no timing fidelity to human readers established.','Data are exact rendered native table text, not a downloaded file.']
m['status_reason']+=f' Recognized {matched}/{len(expected)} words in native sequence order.'
(P/'run.json').write_text(json.dumps(m,indent=2)+'\n')
result='Every native word matches the saved OCR observations in order.' if expected==observed else 'Recognition coverage is incomplete; the original native data remain unchanged.'
extra=''
if (P/'adapter-repair').exists():extra='\nThe saved frame `evidence/053_frame.png` visibly contains the short word “is”, while OCR returned no text. This caused one 9999-ms interval. Offline adapter probes show full-frame accurate/fast recognition failed, while the observed word-band crop succeeded; the repair and all probes are preserved in `adapter-repair/`. The participant policy was not edited.\n'
if (P/'adapter-check.json').exists():extra='\nThe preceding run exposed a short-word OCR detection defect. This attempt keeps the exact same participant policy and adds an OCR fallback to the visibly established canvas word band when full-frame recognition is empty. The adapter passed saved-image fixtures, including the previously missed word and a blank frame, before live use (`adapter-check.json`). No expected answer or word vocabulary is injected.\n'
(P/'summary.md').write_text(f'''# Reading with a generated visible policy

A synthetic participant reached the native export controls. The [native data](data/native-export.tsv) contain {len(rows)} sentence rows and {len(times)} word intervals. The local OCR observations match **{matched}/{len(expected)} words** in native sequence order. {result} See [coverage check](coverage.json).

The model authored the participant program once, and the first mechanically passing candidate was frozen before live use. It reads OCR extracted from current screenshots, follows the observed Space/n/wait instructions, and delivers ordinary browser key presses and releases. Screenshots and recognized text are saved before each response. It cannot access task variables, future text, hidden answers, source, or native data during participation. Native export is captured only after completion.

This is `generated_visible_policy`, **not direct per-word LLM comprehension**. The authoring record acknowledges inherited conversation context rather than claiming an isolated neutral generation call. The retained policy hash is `{m['policy_sha256']}`.
{extra}
There are {times.count(9999)} native intervals equal to 9999 ms. Native intervals range from {min(times)} to {max(times)} ms; these values include OCR and browser transport and were neither adjusted nor selected to match human response times. No human reading validity is established. Every earlier attempt remains archived.
''')
print(json.dumps({k:v for k,v in metrics.items() if not k.endswith('words')}))

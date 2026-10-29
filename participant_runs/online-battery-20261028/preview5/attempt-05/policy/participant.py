"""Frozen participant; sees only visible text/geometry and observer-owned node IDs."""
import re
class Participant:
    def __init__(self,seed):
        self.seed=seed
        self.delay=1
        self.history=[]
        self.seen_letters=set()
        self.seen_cues=set()
        self.responses=0
    def decide(self,obs):
        text=obs['text'].strip()
        cue=re.search(r'(?:your delay[^.]*?\bis\s*|delay\s*[:=]\s*)([12])\b',text,re.I)
        cue_id=tuple(p['token'] for p in obs['parts'])
        if cue and cue_id not in self.seen_cues:
            self.delay=int(cue.group(1));self.history=[];self.seen_cues.add(cue_id)
        if obs['buttons'] or re.search(r'press\s+enter|please take this time|completed|thank you|finished',text,re.I):
            return {'type':'review','reason':'instruction or boundary'}
        letters=[p for p in obs['parts'] if re.fullmatch('[A-Za-z]',p['text'])]
        reminder='Match the current letter to the letter that appeared'
        remainder=' '.join(p['text'] for p in obs['parts'] if p not in letters)
        if len(letters)==1 and (not remainder.strip() or reminder in remainder):
            p=letters[0]
            if p['token'] in self.seen_letters:return {'type':'wait'}
            self.seen_letters.add(p['token']);letter=p['text'].upper()
            match=len(self.history)>=self.delay and self.history[-self.delay]==letter
            key='.' if match else ','
            self.history.append(letter);self.responses+=1
            return {'type':'key','key':key,'token':p['token'],'reason':'match' if match else 'mismatch','letter':p['text'],'delay':self.delay,'policy_wait_ms':0}
        if not text or text=='+' or re.match(r'^(Correct!?|Incorrect!?|Respond Faster!?)\b',text,re.I):return {'type':'wait'}
        return {'type':'review','reason':'unrecognized visible content'}

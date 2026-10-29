const fs=require('fs'), crypto=require('crypto');
const {createParticipant}=require('./participant.js');
const samples=[{stimulus:null},...Array.from({length:1000},(_,i)=>({stimulus:{text:['red','blue','green'][i%3],color:['rgb(255,112,112)','rgb(112,112,255)','rgb(112,255,112)'][i%3],presentation:i}}))];
function trace(seed){const p=createParticipant(seed);return samples.map(o=>{const a=p.decide(o);if(a&&!['.',',','/'].includes(a.key))throw Error('Illegal key');if(p.decide(o)!==null)throw Error('Duplicate response');return a})}
const a=trace(1),b=trace(1);if(JSON.stringify(a)!==JSON.stringify(b))throw Error('Nondeterminism');
const report={status:'passed',syntax:true,legal_inputs:true,bounded_calls:samples.length,deterministic_same_seed:true,distinct_seed_requirement:'not applicable: no random choices',observations:'Instruction-derived rendered colors and observed absence; no behavior-quality criterion',policy_sha256:crypto.createHash('sha256').update(fs.readFileSync(__dirname+'/participant.js')).digest('hex'),candidate:1};
fs.writeFileSync(__dirname+'/gate.json',JSON.stringify(report,null,2)+'\n');console.log(report);

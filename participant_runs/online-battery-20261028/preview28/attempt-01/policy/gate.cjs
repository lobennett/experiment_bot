const fs=require('fs'),crypto=require('crypto');const {createParticipant}=require('./participant.js');
const rectangles=[{width:40,height:80,color:'rgb(255, 255, 255)'},{width:80,height:40,color:'rgb(255, 255, 255)'},{width:40,height:80,color:'rgb(0, 0, 0)'}];
const input=[{stimulus:null},...Array.from({length:1000},(_,i)=>({stimulus:{presentation:i,rectangles:[rectangles[i%3]]}}))];
function run(seed){const p=createParticipant(seed);return input.map(o=>{const a=p.decide(o);if(a&&(![',','.'].includes(a.key)||!Number.isFinite(a.delay_ms)||a.delay_ms<0))throw Error('Illegal action');if(p.decide(o)!==null)throw Error('Duplicate action');return a;});}
if(JSON.stringify(run(1))!==JSON.stringify(run(1)))throw Error('Nondeterminism');
const report={status:'passed',candidate:1,syntax:true,legal_input:true,finite_nonnegative_timing:true,bounded_observations:input.length,seed_reproducibility:true,randomness:'none; seed not used',behavioral_quality_checked:false,policy_sha256:crypto.createHash('sha256').update(fs.readFileSync(__dirname+'/participant.js')).digest('hex')};fs.writeFileSync(__dirname+'/gate.json',JSON.stringify(report,null,2)+'\n');console.log(report);

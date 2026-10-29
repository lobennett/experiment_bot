const fs=require('fs'); const {makeParticipant}=require('./participant.js');
const assert=require('assert');
function trace(seed) {
 const p=makeParticipant(seed),out=[];
 const samples=[
  [{shape:null,star:false},0],
  [{shape:'square',star:false},10],
  [{shape:'square',star:false},100],
  [{shape:'square',star:false},700],
  [{shape:null,star:false},800],
  [{shape:'circle',star:false},900],
  [{shape:'circle',star:true},1000],
  [{shape:'circle',star:true},1600],
  [{shape:null,star:false},1800],
  [{shape:'square',star:false},1900],
  [{shape:null,star:false},1910]
 ];
 for(const [o,t] of samples){const a=p.step(o,t);if(a?.type==='press')assert([',','.'].includes(a.key));out.push(a);}
 return out;
}
assert.deepStrictEqual(trace(91028),trace(91028));
for(let seed=1;seed<=1000;seed++)trace(seed);
const p=makeParticipant(91028);p.step({shape:'square',star:false},0);assert.equal(p.step({shape:null,star:false},1).type,'cancel');
console.log(JSON.stringify({status:'passed',candidate:'participant.js',checks:['syntax','1000 seeds without exceptions','legal keyboard values','same seed same observation trace','stale opportunity cancellation'],behavioral_selection:false},null,2));

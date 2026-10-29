function createParticipant(seed) {
  const answered = new Set();
  return {
    decide(observation) {
      const stimulus = observation.stimulus;
      if (!stimulus || answered.has(stimulus.presentation)) return null;
      const channels = stimulus.color.match(/[\d.]+/g)?.slice(0, 3).map(Number);
      if (!channels || channels.length !== 3 || channels.some(x => !Number.isFinite(x))) return null;
      const [red, green, blue] = channels;
      let key = null;
      if (red > green && red > blue) key = ',';
      if (blue > red && blue > green) key = '.';
      if (green > red && green > blue) key = '/';
      if (key === null) return null;
      answered.add(stimulus.presentation);
      return {key, presentation: stimulus.presentation};
    }
  };
}
if (typeof module !== 'undefined') module.exports = {createParticipant};

const expectedURL='https://deploy.expfactory.org/preview/10/';
const actualURL=await page.eval(()=>location.href);
if(actualURL!==expectedURL)throw Error('Wrong page: '+actualURL);
const participant=createParticipant(null);
const start=Date.now(); let last=''; let actions=0;
console.log(JSON.stringify({kind:'segment_start',at:new Date().toISOString(),url:actualURL}));
const observe=async()=>await page.eval(()=>{
  const state=globalThis.__ebVisibleP10||(globalThis.__ebVisibleP10={elements:new WeakMap(),next:1});
  const choices=Array.from(document.querySelectorAll('div,span,p')).filter(el=>el.children.length===0&&el.checkVisibility()&&/^(red|blue|green)$/i.test(el.innerText.trim())&&parseFloat(getComputedStyle(el).fontSize)>30);
  const el=choices.length===1?choices[0]:null;
  let stimulus=null;
  if(el){if(!state.elements.has(el))state.elements.set(el,state.next++); const r=el.getBoundingClientRect();stimulus={text:el.innerText,color:getComputedStyle(el).color,geometry:{x:r.x,y:r.y,width:r.width,height:r.height},presentation:state.elements.get(el)};}
  return {at:new Date().toISOString(),browser_ms:performance.now(),url:location.href,stimulus,text:document.body.innerText};
});
while(Date.now()-start<45000){
 const o=await observe();if(o.url!==expectedURL)throw Error('Unexpected navigation: '+o.url);
 const sig=JSON.stringify([o.stimulus,o.text]);
 if(sig!==last){console.log(JSON.stringify({kind:'observation',...o}));last=sig;}
 if(!o.stimulus && /press\s+enter|finished|completed|thank you|take a break/i.test(o.text)){
   console.log(JSON.stringify({kind:'boundary',at:new Date().toISOString(),text:o.text}));break;
 }
 const action=participant.decide(o);
 if(action){const current=await observe();if(current.stimulus?.presentation===action.presentation&&current.stimulus.color===o.stimulus.color){
   const at=new Date().toISOString();await page.press(action.key);actions++;console.log(JSON.stringify({kind:'action',at,observation:o,action,delivered_at:new Date().toISOString()}));
 }else console.log(JSON.stringify({kind:'stale_cancelled',at:new Date().toISOString(),observation:o,action,current}));}
 await new Promise(resolve => setTimeout(resolve,20));
}
console.log(JSON.stringify({kind:'segment_end',at:new Date().toISOString(),actions,elapsed_ms:Date.now()-start}));

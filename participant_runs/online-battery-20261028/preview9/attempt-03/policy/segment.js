const identity=await page.eval('() => ({url:location.href,title:document.title})');
console.log(JSON.stringify({type:'identity',...identity}));
if(identity.url!=='https://deploy.expfactory.org/preview/9/')throw new Error('Wrong task URL');
await page.eval(`() => {
  if(!globalThis.__eb_preview9_participant) {
    globalThis.__eb_preview9_participant=(${makeParticipant.toString()})(91028);
  }
}`);
let presses=0, observations=0;
const end=Date.now()+50000;
while(Date.now()<end) {
  const packet=await page.eval(`() => {
    const observation=(${renderedObservation.toString()})();
    const intention=globalThis.__eb_preview9_participant.step(observation,observation.at);
    return {observation,intention};
  }`);
  observations++;
  console.log(JSON.stringify({type:'observation',...packet}));
  const o=packet.observation;
  const knownLines=new Set(['+','Correct!','Incorrect!','Respond Faster!','circle: comma key (,)','square: period key (.)','Do not respond if a star appears.']);
  const unexpectedText=o.text.split('\n').map(x=>x.trim()).filter(x=>x && !knownLines.has(x));
  if(unexpectedText.length || /Please take this time|Press enter to|experiment is over|Thank you|completed|finished/i.test(o.text)) {
    console.log(JSON.stringify({type:'boundary',text:o.text}));break;
  }
  if(packet.intention?.type==='press') {
    const check=await page.eval(renderedObservation.toString());
    if(check.shape===packet.intention.shape && !check.star) {
      await page.press(packet.intention.key);presses++;
      console.log(JSON.stringify({type:'delivery',key:packet.intention.key,opportunity:packet.intention.opportunity,at:new Date().toISOString(),verified_observation:check}));
    } else {
      console.log(JSON.stringify({type:'cancelled_delivery',reason:'visible state changed before dispatch',verified_observation:check}));
    }
  }
  await new Promise(r=>setTimeout(r,20));
}
console.log(JSON.stringify({type:'segment_end',observations,presses}));

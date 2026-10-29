function makeParticipant(seed) {
  let state = seed >>> 0;
  const random = () => {
    state ^= state << 13; state ^= state >>> 17; state ^= state << 5;
    return (state >>> 0) / 4294967296;
  };
  let active = null, pending = null, finished = false, opportunity = 0;
  return {
    step(observation, now) {
      const shape = observation.shape;
      if (!shape) {
        const cancelled = pending;
        active = null; pending = null; finished = false;
        return cancelled ? {type:'cancel',reason:'stimulus disappeared',opportunity} : null;
      }
      if (shape !== active) {
        active = shape; finished = false; opportunity++;
        const settling = 190 + 210 * random() * random();
        pending = {key:shape === 'circle' ? ',' : '.',due:now+settling,shape,opportunity};
      }
      if (observation.star && !finished) {
        pending = null; finished = true;
        return {type:'withhold',opportunity,reason:'visible star'};
      }
      if (pending && now >= pending.due) {
        const action = pending; pending = null; finished = true;
        return {type:'press',...action};
      }
      return null;
    }
  };
}

function renderedObservation() {
  const images = [...document.querySelectorAll('img')].filter(el => {
    const r = el.getBoundingClientRect();
    return el.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}) && r.width>20 && r.height>20 && r.bottom>0 && r.right>0 && r.top<innerHeight && r.left<innerWidth;
  }).map(el => {
    const r=el.getBoundingClientRect();
    const canvas=document.createElement('canvas'); canvas.width=64; canvas.height=64;
    const ctx=canvas.getContext('2d'); ctx.drawImage(el,0,0,64,64);
    const pixels=ctx.getImageData(0,0,64,64).data;
    let count=0,minX=64,minY=64,maxX=-1,maxY=-1;
    for(let y=0;y<64;y++) for(let x=0;x<64;x++) {
      const i=(y*64+x)*4;
      if(pixels[i+3]>64 && (pixels[i]+pixels[i+1]+pixels[i+2])/3>180) {
        count++; minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);
      }
    }
    const occupancy=count ? count/((maxX-minX+1)*(maxY-minY+1)) : 0;
    return {rect:{x:r.x,y:r.y,width:r.width,height:r.height},white_pixel_occupancy:occupancy,white_pixel_count:count};
  });
  const candidates=images.filter(x=>x.white_pixel_occupancy>0.65);
  const main=candidates.sort((a,b)=>b.white_pixel_count-a.white_pixel_count)[0];
  return {at:performance.now(),wall_at:new Date().toISOString(),text:document.body.innerText,images,shape:main ? (main.white_pixel_occupancy>0.9?'square':'circle') : null,star:images.length>1};
}

if (typeof module !== 'undefined') module.exports={makeParticipant,renderedObservation};

const identity=await page.eval('() => ({url:location.href,title:document.title})');
console.log(JSON.stringify({type:'identity',...identity}));
if(identity.url!=='https://deploy.expfactory.org/preview/9/')throw new Error('Wrong task');
await page.press('Enter');
console.log(JSON.stringify({type:'navigation',key:'Enter'}));
const end=Date.now()+5000;
while(Date.now()<end){const o=await page.eval(renderedObservation.toString());if(o.shape){console.log(JSON.stringify({type:'perception_verification',observation:o}));break;}await page.wait(20);}

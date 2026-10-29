() => {
 const visible=e=>{const r=e.getBoundingClientRect();if(!e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})||r.width<=0||r.height<=0||r.right<=0||r.bottom<=0||r.left>=innerWidth||r.top>=innerHeight)return false;const x=Math.max(0,Math.min(innerWidth-1,r.x+r.width/2)),y=Math.max(0,Math.min(innerHeight-1,r.y+r.height/2));const top=document.elementFromPoint(x,y);return top===e||e.contains(top);};
 const buttons=Array.from(document.querySelectorAll('button,input,select')).filter(visible).map(e=>({tag:e.tagName,text:e.innerText,id:e.id,type:e.type}));
 const shapes=Array.from(document.querySelectorAll('div')).filter(e=>e.children.length===0&&visible(e)&&!e.innerText.trim()).filter(e=>{const r=e.getBoundingClientRect();return ['rgb(255, 255, 255)','rgb(0, 0, 0)'].includes(getComputedStyle(e).backgroundColor)&&r.width!==r.height;});
 const state=globalThis.__ebVisibleP28||(globalThis.__ebVisibleP28={elements:new WeakMap(),next:1});
 let stimulus=null;
 if(shapes.length && !buttons.length){
  for(const e of shapes){if(!state.elements.has(e))state.elements.set(e,state.next++);}
  stimulus={presentation:shapes.map(e=>state.elements.get(e)).join(':'),rectangles:shapes.map(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,color:getComputedStyle(e).backgroundColor};})};
 }
 return {at:new Date().toISOString(),browser_ms:performance.now(),url:location.href,text:document.body.innerText,buttons,stimulus};
}

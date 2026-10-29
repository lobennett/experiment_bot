const identity=await page.eval('() => ({url:location.href,title:document.title,text:document.body.innerText})');
console.log(JSON.stringify({type:'identity',...identity}));
if(identity.url!=='https://deploy.expfactory.org/preview/9/')throw new Error('Wrong task URL');
await page.click('button:not([disabled])');
console.log(await page.snapshot());

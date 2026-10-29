console.log(JSON.stringify(await page.eval('() => ({url:location.href,title:document.title,text:document.body.innerText})')));
await page.press('Enter');
await new Promise(r=>setTimeout(r,20));
console.log(JSON.stringify(await page.eval('() => ({url:location.href,title:document.title,text:document.body.innerText})')));

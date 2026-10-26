const {chromium}=require(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES ? process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES+'/playwright' : './frontend/node_modules/playwright');
const assert=require('node:assert/strict');
(async()=>{
 const launch={headless:true,args:['--no-sandbox']};
 if(process.env.CHROMIUM_EXECUTABLE){launch.executablePath=process.env.CHROMIUM_EXECUTABLE;launch.args.push('--single-process','--disable-gpu','--no-zygote');}
 const browser=await chromium.launch(launch);
 const page=await browser.newPage({viewport:{width:1440,height:1000}});let errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:5000');
 await page.locator('input[type=file]').setInputFiles('fixtures/timecards.jpg');
 await page.getByRole('button',{name:'Extract crops for manual entry'}).click();
 await page.getByRole('heading',{name:'5 cards to review'}).waitFor();
 assert.equal(await page.locator('tbody tr:not(.flags-row)').count(),35);
 assert.equal(await page.locator('.grand strong').first().textContent(),'Unresolved');
 const card=page.locator('section.card').first();
 await card.getByRole('textbox',{name:'Card 1 employee name'}).fill('Employee 06');
 const truth=require('./fixtures/ground_truth.json')[0];
 for(let i=0;i<7;i++){
   const row=card.locator('tbody tr:not(.flags-row)').nth(i),p=truth.punches[i];
   await row.locator('select').selectOption(Array.isArray(p)?'worked':p);
   if(Array.isArray(p)){await row.locator('td').nth(2).locator('input').fill(p[0]);await row.locator('td').nth(3).locator('input').fill(p[1]);}
   await row.getByLabel('Notes checked').check();
   await row.getByLabel('Reviewed',{exact:true}).check();
 }
 await page.waitForFunction(()=>document.querySelector('.grand strong')?.textContent==='51:53 · 51.88 h');
 await card.getByLabel('Employee 06 written total').fill('0:00');
 await page.getByText('Written total mismatch; review before paying').first().waitFor();
 assert.equal(await card.locator('.grand strong').textContent(),'51:53 · 51.88 h');
 await card.getByRole('button',{name:/Day 1 ↗/}).click();
 await page.getByRole('dialog').waitFor();
 assert.equal(await page.getByRole('dialog').locator('img').count(),2);
 await page.getByRole('button',{name:'Close ×'}).click();
 await page.getByRole('button',{name:'Save corrected crops'}).click();
 await page.getByRole('link',{name:'Download labeled crops'}).waitFor();
 await page.screenshot({path:'ui-review.png',fullPage:false});
 await page.setViewportSize({width:390,height:844});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false);
 await page.screenshot({path:'ui-mobile.png',fullPage:false});
 assert.deepEqual(errors,[]);console.log('PASS: actual Flask upload, 35 rows, corrections to 51:53, written-total independence, crop inspection, training save, mobile width, no JS errors');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});

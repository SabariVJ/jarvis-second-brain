/* Start server.py separately. Uses installed Edge; no camera/microphone access. */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base=process.env.HOLO_BASE_URL||'http://127.0.0.1:4890';
(async()=>{
  const browser=await chromium.launch({channel:process.env.HOLO_BROWSER||'msedge',headless:true,args:['--enable-unsafe-swiftshader']});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.addInitScript(()=>{
      // Test voice transcript transport without a microphone or an online STT service.
      window.SpeechRecognition=class {
        constructor(){window.testRecognition=this}
        start(){this.onstart?.()}
        stop(){this.onend?.()}
        deliver(text){this.onresult?.({results:[[{transcript:text}]]});this.onend?.()}
      };
    });
    await page.goto(base+'/?probe=1');
    await page.waitForFunction(()=>document.title.startsWith('PROBE'),null,{timeout:60000});
    console.log(await page.title());assert.match(await page.title(),/^PROBE 26\/26/);
    assert.equal(await page.evaluate(()=>window.__holo.cards().filter(c=>c.kind==='obj').length),2);
    await page.goto(base+'/?sim=1');await page.waitForFunction(()=>!!window.jarvisUI);
    assert.match(await page.locator('#status').innerText(),/SIM/);
    await page.waitForFunction(()=>window.__holo.gl());
    await page.waitForFunction(()=>window.__holo.hands.some(h=>h.present));
    await page.goto(base+'/');await page.waitForFunction(()=>!!window.jarvisUI);
    assert.equal(await page.evaluate(()=>document.querySelector('#cam').srcObject),null);
    await page.locator('#j-input').fill('Find my galaxy notes');await page.locator('#j-send').click();
    await page.waitForFunction(()=>document.querySelectorAll('.j-sources button').length>0);
    await page.waitForFunction(()=>!document.querySelector('#j-send').disabled);
    assert.equal(await page.locator('#galaxy').isVisible(),true);
    await page.locator('.j-sources button').first().click();
    await page.waitForFunction(()=>!document.querySelector('#source-reader').hidden);
    assert.match(await page.locator('#source-reader pre').innerText(),/Every note a star/);
    await page.locator('#source-summary').click();
    await page.waitForFunction(()=>document.querySelector('#j-log').textContent.includes('Local extract'));
    await page.waitForFunction(()=>!document.querySelector('#j-send').disabled);
    await page.locator('#j-input').fill('Open it');await page.locator('#j-send').click();
    await page.waitForFunction(()=>!document.querySelector('#source-reader').hidden);
    await page.locator('#source-close').click();
    await page.locator('#galaxy-list button').first().click();
    await page.locator('[data-act=collapse]').click();assert.equal(await page.locator('#galaxy-list button').count(),1);
    await page.locator('[data-act=expand]').click();assert.ok(await page.locator('#galaxy-list button').count()>1);
    await page.locator('[data-act=all]').click();
    // Typing HOLO shortcut letters must not toggle features or reset cards.
    const hands=await page.locator('#hands').innerText();await page.locator('#j-input').fill('hfjrvd');
    await page.locator('#j-input').press('h');assert.equal(await page.locator('#hands').innerText(),hands);
    await page.locator('#j-input').fill('');
    await page.locator('#j-mic').click();await page.waitForFunction(()=>document.querySelector('#j-status').textContent.includes('MIC ACTIVE'));
    await page.evaluate(()=>window.testRecognition.deliver('Find the arrow'));
    await page.waitForFunction(()=>document.querySelector('#j-log').textContent.includes('THE ARROW')&&!document.querySelector('#j-send').disabled);
    assert.ok(await page.locator('.j-entry').last().locator('.j-sources button').count()>0);
    assert.equal(await page.evaluate(()=>document.querySelector('#cam').srcObject),null);
    await page.locator('#j-index').click();await page.waitForFunction(()=>document.querySelector('#j-status').textContent==='IDLE');
    fs.mkdirSync('test-results',{recursive:true});await page.screenshot({path:'test-results/foundation-preview.png'});
    await page.setViewportSize({width:390,height:844});await page.screenshot({path:'test-results/mobile-preview.png'});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    assert.deepEqual(errors,[]);
    console.log('PASS: probe+props, simulation, no-camera, search, graph focus, source, summary, follow-ups, expand/collapse, shortcuts, mocked voice transcript, reindex, narrow layout; zero page errors.');
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});

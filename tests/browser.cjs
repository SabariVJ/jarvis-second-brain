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
        interim(text){const row=[{transcript:text}];row.isFinal=false;this.onresult?.({results:[row]})}
        deliver(text){const row=[{transcript:text}];row.isFinal=true;this.onresult?.({results:[row]});this.onend?.()}
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
    await page.evaluate(()=>window.testRecognition.interim('Find the'));
    assert.match(await page.locator('#j-transcript').innerText(),/Heard: Find the/);
    assert.equal(await page.locator('#j-send').isDisabled(),false);
    await page.evaluate(()=>window.testRecognition.deliver('Find the arrow'));
    await page.waitForFunction(()=>document.querySelector('#j-log').textContent.includes('THE ARROW')&&!document.querySelector('#j-send').disabled);
    assert.ok(await page.locator('.j-entry').last().locator('.j-sources button').count()>0);
    assert.equal(await page.evaluate(()=>document.querySelector('#cam').srcObject),null);
    await page.locator('#j-mic').click();await page.waitForFunction(()=>document.querySelector('#j-status').textContent.includes('MIC ACTIVE'));
    await page.locator('#j-mic').click();await page.waitForFunction(()=>document.querySelector('#j-status').textContent==='IDLE');
    await page.locator('#j-index').click();await page.waitForFunction(()=>document.querySelector('#j-status').textContent==='IDLE');
    await page.locator('#j-input').fill('Research current alternatives to X');await page.locator('#j-send').click();
    await page.waitForFunction(()=>document.querySelector('#j-log').textContent.includes('Live research needs an OpenAI API key'));
    assert.equal(await page.locator('.research-card').count(),0);
    let research={id:'fixture-card',query:'alternatives to X',status:'temporary',answer:'Alpha reports one result. Beta reports a different result.',
      researched_at:1790000000,model:'gpt-6-astra',warning:null,sources:[
        {title:'Alpha',url:'https://example.org/a',snippet:'Alpha reports one result.',snippet_origin:'cited_answer_excerpt'},
        {title:'Beta',url:'https://example.net/b',snippet:'Beta reports a different result.',snippet_origin:'cited_answer_excerpt'}]};
    await page.route('**/api/jarvis/chat',async route=>{
      const body=route.request().postDataJSON();
      if(!body.message.toLowerCase().startsWith('research '))return route.continue();
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({answer:research.answer,sources:[],node_ids:[],
        mode:'research',warning:null,action:'focus',state:'IDLE',events:[],research_card:research})});
    });
    await page.route('**/api/research/card',async route=>{
      const body=route.request().postDataJSON();
      if(body.action==='dismiss')research=null;
      else research={...research,status:body.action==='keep'?'pinned':'saved',...(body.action==='save'?{document_id:'doc_saved'}:{})};
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ok:true,action:body.action,card:research,document_id:research?.document_id})});
    });
    await page.route('**/api/research/cards?*',route=>route.fulfill({status:200,contentType:'application/json',
      body:JSON.stringify({cards:research?[research]:[]})}));
    await page.locator('#j-input').fill('Research alternatives to X');await page.locator('#j-send').click();
    await page.waitForFunction(()=>document.querySelector('.research-card'));
    assert.equal(await page.locator('.research-sources a').first().isVisible(),false);
    await page.locator('.research-card button').first().click();
    assert.equal(await page.locator('.research-sources a').count(),2);
    assert.equal(await page.locator('.research-sources a').first().getAttribute('rel'),'noopener noreferrer');
    await page.getByRole('button',{name:'Keep card'}).click();await page.waitForFunction(()=>document.querySelector('.research-card small').textContent.includes('PINNED'));
    await page.reload();await page.waitForFunction(()=>document.querySelector('.research-card small')?.textContent.includes('PINNED'));
    await page.getByRole('button',{name:'Dismiss'}).click();await page.waitForFunction(()=>!document.querySelector('.research-card'));
    fs.mkdirSync('test-results',{recursive:true});await page.screenshot({path:'test-results/foundation-preview.png'});
    await page.setViewportSize({width:390,height:844});await page.screenshot({path:'test-results/mobile-preview.png'});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    assert.deepEqual(errors,[]);
    console.log('PASS: probe+props, simulation, no-camera, search, graph focus, source, summary, follow-ups, expand/collapse, shortcuts, mocked voice transcript, reindex, narrow layout; zero page errors.');
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});

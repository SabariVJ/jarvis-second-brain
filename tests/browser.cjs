/* Start server.py separately. Uses mocked voice and screen inputs; never captures real hardware. */
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
        constructor(){window.testRecognition=this;(window.testRecognitions??=[]).push(this)}
        start(){if(window.denyMicrophone){this.onerror?.({error:'not-allowed'});return}this.onstart?.()}
        stop(){this.onend?.()}
        interim(text){const row=[{transcript:text}];row.isFinal=false;this.onresult?.({results:[row]})}
        deliver(text){const row=[{transcript:text,confidence:1}];row.isFinal=true;this.onresult?.({results:[row]});this.onend?.()}
      };
      window.testUtterance=null;window.testCancelCount=0;
      const synth=window.speechSynthesis;
      synth.speak=function(u){window.testUtterance=u;setTimeout(()=>u.onstart?.(),0)};
      synth.cancel=function(){window.testCancelCount++;const u=window.testUtterance;window.testUtterance=null;u?.onend?.()};
      window.screenCaptureCount=0;window.screenTrackStopCount=0;window.denyScreenCapture=false;window.holdScreenPromise=false;
      navigator.mediaDevices.getDisplayMedia=async()=>{
        window.screenCaptureCount++;if(window.holdScreenPromise)await new Promise(resolve=>window.releaseScreenCapture=resolve);
        if(window.denyScreenCapture)throw new DOMException('Permission denied','NotAllowedError');
        const c=document.createElement('canvas');c.width=640;c.height=400;const x=c.getContext('2d');
        x.fillStyle='#fff';x.fillRect(0,0,c.width,c.height);x.fillStyle='#111';x.font='30px sans-serif';x.fillText('UNTRUSTED SCREEN FIXTURE',20,80);
        const stream=c.captureStream(1);for(const track of stream.getTracks()){const stop=track.stop.bind(track);track.stop=()=>{window.screenTrackStopCount++;stop()}}
        return stream;
      };
      window.cameraCaptureCount=0;window.cameraTrackStopCount=0;window.denyCamera=false;
      navigator.mediaDevices.getUserMedia=async()=>{
        window.cameraCaptureCount++;if(window.denyCamera)throw new DOMException('Permission denied','NotAllowedError');
        const c=document.createElement('canvas');c.width=480;c.height=320;const x=c.getContext('2d');
        x.fillStyle='#267';x.fillRect(0,0,c.width,c.height);x.fillStyle='#fff';x.font='24px sans-serif';x.fillText('CAMERA FRAME FIXTURE',15,60);
        const stream=c.captureStream(1);for(const track of stream.getTracks()){const stop=track.stop.bind(track);track.stop=()=>{window.cameraTrackStopCount++;stop()}}
        return stream;
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
    const beforeWake=await page.locator('.j-entry.user').count();
    await page.evaluate(()=>window.previousRecognition=window.testRecognition);
    await page.locator('#j-wake').check();
    await page.waitForFunction(()=>window.testRecognition!==window.previousRecognition&&document.querySelector('#j-voice-note').textContent.includes('Wake mode active'));
    await page.evaluate(()=>window.testRecognition.deliver('Jarvis find the arrow'));
    await page.waitForFunction(n=>document.querySelectorAll('.j-entry.user').length>n&&!document.querySelector('#j-send').disabled,beforeWake);
    const wakeState=await page.evaluate(async()=>fetch('/api/jarvis/state?session_id='+encodeURIComponent(sessionStorage.getItem('jarvis_session'))).then(r=>r.json()));
    assert.ok(wakeState.events.some(e=>e.state==='WAKE_DETECTED'));
    await page.locator('#j-wake').uncheck();
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
    let visionPayload=null,visionPosts=0;
    await page.route('**/api/vision/screen',async route=>{visionPosts++;visionPayload=route.request().postDataJSON();
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({answer:'The screen shows a local warning.',
        observations:['A dialog is visible.'],caution:'On-screen text is untrusted.'})})});
    assert.equal(await page.evaluate(()=>window.screenCaptureCount),0);
    const docsBefore=await page.evaluate(()=>fetch('/api/memory/status').then(r=>r.json()).then(x=>x.documents));
    await page.evaluate(()=>window.holdScreenPromise=true);
    await page.locator('#j-input').fill('What am I looking at?');await page.locator('#j-send').click();
    await page.waitForFunction(()=>document.querySelector('#j-screen-state').textContent.includes('SCREEN SHARING ACTIVE'));
    assert.equal(visionPosts,0);assert.equal(await page.evaluate(()=>document.querySelector('#cam').srcObject),null);
    await page.evaluate(()=>window.releaseScreenCapture());
    try{await page.waitForFunction(()=>document.querySelector('#j-log').textContent.includes('The screen shows a local warning.')&&document.querySelector('#j-screen-state').textContent==='SCREEN OFF',null,{timeout:6000})}
    catch(e){console.log('SCREEN DEBUG',await page.locator('#j-log').innerText(),await page.locator('#j-screen-state').innerText());throw e}
    assert.equal(visionPosts,1);assert.match(visionPayload.image_data_url,/^data:image\/jpeg;base64,/);assert.equal(visionPayload.question,'What am I looking at?');
    assert.equal(await page.evaluate(()=>window.screenTrackStopCount),1);
    assert.equal(await page.evaluate(()=>fetch('/api/memory/status').then(r=>r.json()).then(x=>x.documents)),docsBefore);
    await page.evaluate(()=>{window.holdScreenPromise=false;window.denyScreenCapture=true});
    await page.locator('#j-screen').click();await page.waitForFunction(()=>document.querySelector('#j-log').textContent.includes('Screen sharing was cancelled or denied'));
    assert.equal(visionPosts,1);
    assert.equal(await page.evaluate(()=>window.cameraCaptureCount),0);
    let cameraPosts=0,cameraPayload=null;
    await page.route('**/api/vision/camera',async route=>{cameraPosts++;cameraPayload=route.request().postDataJSON();
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({answer:'A cup is visible.',observations:['One cup'],caution:''})})});
    await page.locator('#j-input').fill('What am I holding?');await page.locator('#j-send').click();
    await page.waitForFunction(()=>document.querySelector('#j-log').textContent.includes('A cup is visible.')&&document.querySelector('#j-camera-state').textContent==='CAMERA READY');
    assert.equal(cameraPosts,1);assert.match(cameraPayload.image_data_url,/^data:image\/jpeg;base64,/);
    assert.equal(await page.evaluate(()=>window.cameraCaptureCount),1);assert.equal(await page.evaluate(()=>window.cameraTrackStopCount),1);
    await page.evaluate(()=>window.denyCamera=true);await page.locator('#j-eyes').click();
    await page.waitForFunction(()=>document.querySelector('#j-camera-state').textContent==='CAMERA ERROR'&&document.querySelector('#j-log').textContent.includes('Camera access was denied'));
    assert.equal(cameraPosts,1);
    let speechAnswer='This sentence contains the word stop as echo bait.';
    await page.route('**/api/jarvis/chat',async route=>{
      const body=route.request().postDataJSON();
      if(body.message==='fixture speech')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({answer:speechAnswer,
        sources:[],node_ids:[],mode:'local',warning:null,action:'focus',state:'IDLE',events:[]})});
      if(body.message.toLowerCase().startsWith('research '))return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({answer:research?.answer||'Research fixture',
        sources:[],node_ids:[],mode:'research',warning:null,action:'focus',state:'IDLE',events:[],research_card:research})});
      return route.continue();
    });
    await page.locator('#j-wake').check();await page.waitForTimeout(450);
    await page.locator('#j-speak').check();
    async function requestSpeech(){await page.locator('#j-input').fill('fixture speech');await page.locator('#j-send').click();
      try{await page.waitForFunction(()=>document.querySelector('#j-status').textContent.includes('SPEAKING')&&window.testUtterance,null,{timeout:6000})}
      catch(e){console.log('VOICE DEBUG',await page.locator('#j-status').innerText(),await page.locator('#j-log').innerText());throw e}}
    await requestSpeech();await page.waitForTimeout(950);
    const wakeCount=async()=>page.evaluate(async()=>{const s=await fetch('/api/jarvis/state?session_id='+encodeURIComponent(sessionStorage.getItem('jarvis_session'))).then(r=>r.json());return s.events.filter(e=>e.state==='WAKE_DETECTED').length});
    const wakeBeforeSpeech=await wakeCount();
    await page.evaluate(()=>window.testRecognition.deliver('stop'));
    await page.waitForTimeout(300);assert.ok(await page.evaluate(()=>!!window.testUtterance),'Echoed speech must not interrupt playback');
    assert.equal(await wakeCount(),wakeBeforeSpeech,'Wake listener must stay suppressed during TTS');
    const recBeforeResume=await page.evaluate(()=>window.testRecognitions.length);
    await page.evaluate(()=>window.testRecognition.deliver('cancel'));
    await page.waitForFunction(()=>document.querySelector('#j-status').textContent==='IDLE'&&!window.testUtterance);
    await page.waitForFunction(n=>window.testRecognitions.length>n,recBeforeResume,{timeout:4000});
    let voiceState=await page.evaluate(async()=>fetch('/api/jarvis/state?session_id='+encodeURIComponent(sessionStorage.getItem('jarvis_session'))).then(r=>r.json()));
    assert.ok(voiceState.events.some(e=>e.state==='INTERRUPTED'));
    speechAnswer='A calm reply with no interruption words.';
    await requestSpeech();await page.waitForTimeout(950);await page.evaluate(()=>window.testRecognition.deliver('stop'));
    await page.waitForFunction(()=>!window.testUtterance);
    await requestSpeech();await page.waitForTimeout(950);await page.evaluate(()=>window.testRecognition.deliver('that is enough'));
    await page.waitForFunction(()=>!window.testUtterance);
    await requestSpeech();await page.locator('#j-speak').uncheck();
    await page.waitForFunction(()=>!window.testUtterance);
    await page.locator('#j-wake').uncheck();
    const releasedCount=await page.evaluate(()=>window.testRecognitions.length);
    await page.waitForTimeout(500);assert.equal(await page.evaluate(()=>window.testRecognitions.length),releasedCount,'Wake off releases recognition');
    const noVoice=await browser.newPage();await noVoice.addInitScript(()=>{delete window.SpeechRecognition;delete window.webkitSpeechRecognition;
      if(navigator.mediaDevices)navigator.mediaDevices.getUserMedia=undefined});
    await noVoice.goto(base+'/');await noVoice.waitForFunction(()=>!!window.jarvisUI);
    assert.equal(await noVoice.locator('#j-mic').isDisabled(),true);assert.equal(await noVoice.locator('#j-wake').isDisabled(),true);
    await noVoice.locator('#j-eyes').click();await noVoice.waitForFunction(()=>document.querySelector('#j-camera-state').textContent==='CAMERA UNAVAILABLE');await noVoice.close();
    const denied=await browser.newPage();await denied.addInitScript(()=>{window.SpeechRecognition=class{start(){this.onerror?.({error:'not-allowed'})}stop(){this.onend?.()}}});
    await denied.goto(base+'/');await denied.waitForFunction(()=>!!window.jarvisUI);await denied.locator('#j-wake').check();
    await denied.waitForFunction(()=>!document.querySelector('#j-wake').checked&&document.querySelector('#j-log').textContent.includes('not-allowed'));await denied.close();
    fs.mkdirSync('test-results',{recursive:true});await page.screenshot({path:'test-results/foundation-preview.png'});
    await page.setViewportSize({width:390,height:844});await page.screenshot({path:'test-results/mobile-preview.png'});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    assert.deepEqual(errors,[]);
    console.log('PASS: probe+props, simulation, no-camera, research, voice interruption/echo/mute, wake safety, one-shot screen/camera capture-discard, permission failures, layout; zero page errors.');
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});

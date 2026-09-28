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
    let gmailAuth={state:'NOT CONNECTED',connected:false},gmailCalls=[];
    let calendarAuth={state:'NOT CONNECTED',connected:false},calendarCalls=[],approvalItems=[],approvalSequence=0;
    const makeApproval=(tool,args)=>{const id='approval_'+String(++approvalSequence).padStart(24,'0'),item={id,tool,permission_class:'L3_EXTERNAL_WRITE',arguments_preview:args,
      created_at:Date.now()/1000,expires_at:Date.now()/1000+300,status:'PENDING',confirmation_phrase:'APPROVE '+id};approvalItems.push(item);return item};
    let briefingCalls=0;
    let personalMemories=[],memoryCalls=[];
    let documentCards=[],documentCalls=[],documentSequence=0,invoiceCreateBody=null;
    let focusState={state:'IDLE',monitor_supported:true,warning:null},focusCalls=[];
    const focusRoute=async route=>{
      const url=new URL(route.request().url()),action=url.pathname.split('/').pop();
      if(route.request().method()==='POST'){
        const body=route.request().postDataJSON();focusCalls.push({action,body});
        focusState=action==='start'?{state:'ACTIVE',goal:body.goal,remaining_seconds:5400,distraction_count:0,pause_count:0,monitor_supported:true,warning:null}:
          action==='pause'?{...focusState,state:'PAUSED'}:action==='resume'?{...focusState,state:'ACTIVE'}:{...focusState,state:'STOPPED',result:'stopped'};
      }
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(focusState)});
    };
    await page.route('**/api/focus',focusRoute);await page.route('**/api/focus/**',focusRoute);
    await page.route('**/api/personal-memory**',async route=>{
      const url=new URL(route.request().url()),method=route.request().method(),body=method==='POST'?route.request().postDataJSON():{};
      memoryCalls.push({method,path:url.pathname,body});
      if(method==='GET'){
        const id=url.searchParams.get('id'),category=url.searchParams.get('category'),q=(url.searchParams.get('q')||'').toLowerCase();
        const item=personalMemories.find(m=>m.id===id);
        const result=id?(item?{...item,source_type:item.source_type,source_reference:'Explicit user request'}:{}):
          {items:personalMemories.filter(m=>(!category||m.category===category)&&(!q||m.content.toLowerCase().includes(q)))};
        return route.fulfill({status:id&&!item?400:200,contentType:'application/json',body:JSON.stringify(result)});
      }
      if(url.pathname.endsWith('/remember')){const item={id:'mem_fixture',category:'PREFERENCE',content:body.content,importance:.8,source_type:body.source_type};personalMemories=[item];return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(item)})}
      if(url.pathname.endsWith('/update')){personalMemories[0]={...personalMemories[0],content:body.content,source_type:'user_update'};return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(personalMemories[0])})}
      if(url.pathname.endsWith('/forget')){personalMemories=[];return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({forgotten:true,id:body.id})})}
      return route.fulfill({status:404,contentType:'application/json',body:'{}'});
    });
    await page.route('**/api/integrations/telegram',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
      state:'DISABLED',enabled:false,configured:false,running:false,allowed_user_count:0,voice_notes:'NOT CONNECTED',sharing:'LOCAL APPROVAL REQUIRED'})}));
    await page.route('**/api/approvals**',async route=>{const url=new URL(route.request().url()),method=route.request().method();
      if(method==='GET')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({items:approvalItems})});
      const body=route.request().postDataJSON();if(url.pathname.endsWith('/confirm')){const at=approvalItems.findIndex(x=>x.id===body.approval_id);
        if(at<0)return route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({error:'Approval missing'})});
        const item=approvalItems.splice(at,1)[0];return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({approval:{...item,status:'EXECUTED'},tool_result:{ok:true,result:{confirmed:true}}})})}
      if(url.pathname.endsWith('/reject'))approvalItems=approvalItems.filter(x=>x.id!==body.approval_id);
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({items:approvalItems})});
    });
    await page.route('**/api/documents**',async route=>{
      const url=new URL(route.request().url()),method=route.request().method(),path=url.pathname,body=method==='POST'?route.request().postDataJSON():{};
      documentCalls.push({method,path,body});
      if(path.endsWith('/file'))return route.fulfill({status:200,contentType:'application/pdf',body:Buffer.from('%PDF-1.4\nmock\n%%EOF')});
      if(method==='GET')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({items:documentCards.filter(x=>x.status==='active')})});
      if(path.endsWith('/invoice/create')){invoiceCreateBody=body;documentSequence++;
        const id='doc_'+String(documentSequence).padStart(32,'0'),item={id,kind:'invoice',title:'Invoice INV-FIXTURE · '+body.customer.name,
          filename:'invoice_fixture.pdf',summary:'Invoice for '+body.customer.name+' · '+body.currency+' 25000.00',created_at:1790000000,
          source_ids:body.source_ids||[],invoice:body,share_approved:false,pinned:false,status:'active',preview_url:'/api/documents/file?id='+id};
        documentCards.unshift(item);return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({...item,created:true})})}
      if(path.endsWith('/create')){documentSequence++;const id='doc_'+String(documentSequence).padStart(32,'0'),item={id,kind:body.kind,title:body.title,
        filename:'report_fixture.pdf',summary:body.content,created_at:1790000000,source_ids:body.source_ids||[],share_approved:false,pinned:false,status:'active',preview_url:'/api/documents/file?id='+id};
        documentCards.unshift(item);return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(item)})}
      if(path.endsWith('/action')){const item=documentCards.find(x=>x.id===body.id);if(!item)return route.fulfill({status:404,contentType:'application/json',body:'{}'});
        if(body.action==='dismiss')item.status='dismissed';if(body.action==='pin')item.pinned=true;if(body.action==='unpin')item.pinned=false;
        if(body.action==='approve_share')item.share_approved=true;if(body.action==='revoke_share')item.share_approved=false;
        return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(item)})}
      return route.fulfill({status:404,contentType:'application/json',body:'{}'});
    });
    await page.route('**/api/integrations/gmail',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(gmailAuth)}));
    await page.route('**/api/integrations/calendar',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(calendarAuth)}));
    await page.route('**/api/briefing/morning',route=>{briefingCalls++;return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
      generated_at:'2026-09-27T08:00:00Z',spoken:'Good morning. You have one calendar item today. There are no active tasks.',
      calendar:{status:'READY',items:[{summary:'Planning',start:'09:00',end:'09:30'}]},
      email:{status:'READY',items:[{from:'Build Bot',subject:'<img src=x onerror=alert(1)>',snippet:'untrusted'}]},
      brain:{priorities:[{content:'Finish Jarvis',source:'notes.md'}],active_tasks:[],deadlines:[],reminders:[],recent_projects:[{name:'Jarvis',source:'notes.md'}]},
      focus:{state:'IDLE'},scheduling:{supported:false,auto_at_startup:false}})})});
    await page.addInitScript(()=>{
      // Test voice transcript transport without a microphone or an online STT service.
      window.SpeechRecognition=class {
        constructor(){window.testRecognition=this;(window.testRecognitions??=[]).push(this)}
        start(){if(window.denyMicrophone){this.onerror?.({error:'not-allowed'});return}this.onstart?.()}
        stop(){this.stopCount=(this.stopCount||0)+1;this.onend?.()}
        interim(text){const row=[{transcript:text}];row.isFinal=false;this.onresult?.({results:[row]})}
        deliver(text){const row=[{transcript:text,confidence:1}];row.isFinal=true;this.onresult?.({results:[row]});this.onend?.()}
      };
      window.testUtterance=null;window.testCancelCount=0;
      window.confirmAnswer=true;window.confirm=()=>window.confirmAnswer;
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
    await page.waitForFunction(()=>document.querySelectorAll('#settings-items .setting-item').length===14);
    await page.waitForFunction(()=>document.querySelector('#automation-state').textContent.includes('0 RULE'));
    assert.equal(await page.locator('#automation-source-gmail').isChecked(),false);
    assert.equal(await page.locator('#automation-source-calendar').isChecked(),false);
    await page.locator('#automation-source-gmail').check();
    await page.waitForFunction(()=>document.querySelector('#automation-source-gmail-status').textContent.includes('NOT CONNECTED'));
    await page.locator('#automation-source-gmail').uncheck();
    await page.waitForFunction(()=>document.querySelector('#automation-source-gmail-status').textContent.includes('DISABLED'));
    await page.locator('#automation-name').fill('Build notice');await page.locator('#automation-trigger').selectOption('EVENT');
    await page.locator('#automation-event').selectOption('BUILD_FINISHED');await page.locator('#automation-title').fill('Build finished');
    await page.locator('#automation-message').fill('Review the local build.');await page.locator('#automation-save').click();
    await page.waitForFunction(()=>document.querySelectorAll('#automation-items .automation-item').length===1);
    assert.match(await page.locator('#automation-items').innerText(),/DISABLED/,'new automations start disabled');
    await page.locator('#automation-items button').first().click();await page.waitForFunction(()=>document.querySelector('#automation-items').textContent.includes('ENABLED'));
    await page.locator('#automation-items button').nth(1).click();await page.locator('#automation-message').fill('Edited local notice.');
    await page.locator('#automation-save').click();await page.waitForFunction(()=>document.querySelector('#automation-items').textContent.includes('Build notice'));
    await page.locator('#automation-items button').first().click();await page.waitForFunction(()=>document.querySelector('#automation-items').textContent.includes('DISABLED'));
    await page.locator('#automation-items button').nth(2).click();await page.waitForFunction(()=>document.querySelectorAll('#automation-items .automation-item').length===0);
    assert.match(await page.locator('#settings-overall').innerText(),/ACTION REQUIRED|READY/);
    assert.equal(await page.locator('#saved-card-panel').isVisible(),true);
    await page.waitForFunction(()=>document.querySelector('#personal-memory-results').textContent.includes('No saved personal memories'));
    await page.locator('#personal-memory-content').fill('<img src=x onerror=alert(1)>');await page.locator('#personal-memory-form button').click();
    await page.waitForFunction(()=>document.querySelector('.personal-memory-item'));
    assert.equal(await page.locator('.personal-memory-item img').count(),0,'memory text must be rendered safely');
    assert.equal(memoryCalls.find(x=>x.path.endsWith('/remember')).body.source_type,'user_explicit');
    await page.locator('#personal-memory-query').fill('onerror');await page.locator('#personal-memory-search').click();
    await page.waitForFunction(()=>document.querySelectorAll('.personal-memory-item').length===1);
    await page.locator('.personal-memory-item button').first().click();
    await page.waitForFunction(()=>document.querySelector('.personal-memory-item p').textContent.includes('Provenance: user_explicit'));
    page.once('dialog',dialog=>dialog.accept('I prefer safe text rendering.'));
    await page.locator('.personal-memory-item button').nth(1).click();
    assert.ok(memoryCalls.some(x=>x.path.endsWith('/update')));
    await page.locator('#personal-memory-query').fill('');await page.locator('#personal-memory-search').click();
    await page.waitForFunction(()=>document.querySelector('.personal-memory-item p')?.textContent==='I prefer safe text rendering.');
    await page.locator('.personal-memory-item button').nth(2).click();
    await page.waitForFunction(()=>document.querySelector('#personal-memory-results').textContent.includes('No saved personal memories'));
    assert.equal(await page.evaluate(()=>document.querySelector('#cam').srcObject),null);
    assert.equal(await page.locator('#gmail-state').innerText(),'NOT CONNECTED');assert.equal(await page.locator('#gmail-inbox').isDisabled(),true);
    assert.equal(await page.locator('#calendar-state').innerText(),'NOT CONNECTED');assert.equal(await page.locator('#calendar-create').isDisabled(),true);
    assert.equal(await page.locator('#telegram-state').innerText(),'DISABLED');assert.equal(await page.locator('#telegram-start').isDisabled(),true);
    assert.equal(await page.locator('#telegram-detail').innerText().then(x=>x.includes('token')),false);
    await page.locator('#document-toggle').click();
    await page.waitForFunction(()=>document.querySelector('#invoice-form')&&!document.querySelector('#invoice-form').hidden);
    await page.locator('#invoice-customer-name').fill('Company X');await page.locator('#invoice-unit-price').fill('25000');
    await page.locator('#invoice-item-description').fill('App development');
    assert.equal(await page.locator('#invoice-customer-name').inputValue(),'Company X');
    assert.equal(await page.locator('#invoice-unit-price').inputValue(),'25000');
    assert.match(await page.locator('#invoice-item-description').inputValue(),/app development/i);
    await page.locator('#invoice-seller-name').fill('North Star Studio');await page.locator('#invoice-seller-address').fill('42 Sample Road, Pune');
    await page.locator('#invoice-customer-address').fill('11 Client Street, Mumbai');
    await page.locator('#invoice-form button[type=submit]').click();
    await page.waitForFunction(()=>document.querySelector('.document-card h4')?.textContent.includes('Company X'));
    let invoiceId=await page.locator('.document-card').first().getAttribute('data-id');
    assert.equal(invoiceCreateBody.customer.name,'Company X');assert.equal(invoiceCreateBody.items[0].unit_price,'25000');
    const pdfCheck=await page.evaluate(async id=>{const r=await fetch('/api/documents/file?id='+encodeURIComponent(id));return {status:r.status,type:r.headers.get('content-type'),head:Array.from(new Uint8Array(await r.arrayBuffer()).slice(0,4))}},invoiceId);
    assert.equal(pdfCheck.status,200);assert.equal(pdfCheck.type,'application/pdf');assert.deepEqual(pdfCheck.head,[37,80,68,70]);
    await page.locator('.document-card button').nth(1).click();
    await page.waitForFunction(()=>document.querySelector('.document-card iframe'));
    const invoiceControls=page.locator('.document-card').first().locator('.j-row button');
    await invoiceControls.nth(2).click();await page.waitForFunction(()=>document.querySelector('.document-card .j-row button:nth-child(3)')?.textContent==='Unpin');
    await invoiceControls.nth(4).click();await page.waitForFunction(async id=>fetch('/api/documents').then(r=>r.json()).then(x=>x.items.find(i=>i.id===id)?.share_approved),invoiceId);
    await page.locator('.document-card').first().locator('.j-row button').nth(4).click();
    await page.waitForFunction(async id=>fetch('/api/documents').then(r=>r.json()).then(x=>!x.items.find(i=>i.id===id)?.share_approved),invoiceId);
    await page.locator('.document-card').first().locator('.j-row button').nth(6).click();
    await page.waitForFunction(()=>document.querySelector('#saved-card-results').textContent.includes('INVOICE'));
    await page.locator('#generic-toggle').click();await page.locator('#document-title').fill('Build report');await page.locator('#document-content').fill('The report body wraps safely.\n\nNext steps are clear.');
    await page.locator('#generic-document-form button[type=submit]').click();await page.waitForFunction(()=>document.querySelectorAll('.document-card').length===2);
    await page.locator('.document-card').first().locator('.j-row button').nth(5).click();
    await page.waitForFunction(()=>document.querySelectorAll('.document-card').length===1);
    assert.equal(await page.locator('#briefing-status').innerText(),'NOT RUN');assert.equal(briefingCalls,0,'Briefing must not run automatically at startup');
    await page.locator('#briefing-run').click();await page.waitForFunction(()=>document.querySelector('#briefing-status').textContent.startsWith('READY'));
    assert.equal(briefingCalls,1);assert.match(await page.locator('#briefing-detail').innerText(),/Planning/);
    assert.equal(await page.locator('#briefing-detail img').count(),0,'Mail content must render as text');
    await page.locator('#j-input').fill('Jarvis, give me my morning briefing.');await page.locator('#j-send').click();
    await page.waitForFunction(()=>document.querySelector('#j-log').textContent.includes('There are no active tasks.'));
    assert.equal(briefingCalls,2,'Natural-language briefing must be manually invoked');
    await page.locator('#j-input').fill('Find my galaxy notes');await page.locator('#j-send').click();
    await page.waitForFunction(()=>document.querySelectorAll('.j-sources button').length>0);
    await page.waitForFunction(()=>!document.querySelector('#j-send').disabled);
    assert.equal(await page.locator('#galaxy').isVisible(),true);
    await page.locator('.j-sources button').first().click();
    await page.waitForFunction(()=>!document.querySelector('#source-reader').hidden);
    const noteContext=await page.evaluate(async()=>fetch('/api/jarvis/state?session_id='+encodeURIComponent(sessionStorage.getItem('jarvis_session'))).then(r=>r.json()));
    assert.equal(noteContext.current_context.event,'NOTE_OPENED');assert.equal(noteContext.current_context.object_type,'NOTE');
    assert.match(await page.locator('#source-reader pre').innerText(),/Every note a star/);
    await page.locator('#source-summary').click();
    await page.waitForFunction(()=>document.querySelector('#j-log').textContent.includes('Local extract'));
    await page.waitForFunction(()=>!document.querySelector('#j-send').disabled);
    await page.locator('#j-input').fill('Open it');await page.locator('#j-send').click();
    await page.waitForFunction(()=>!document.querySelector('#source-reader').hidden);
    await page.locator('#source-close').click();
    await page.locator('#galaxy-list button').first().click();
    await page.locator('[data-act=collapse]').click();assert.equal(await page.locator('#galaxy-list button').count(),1);
    const graphContext=await page.evaluate(async()=>fetch('/api/jarvis/state?session_id='+encodeURIComponent(sessionStorage.getItem('jarvis_session'))).then(r=>r.json()));
    assert.equal(graphContext.current_context.event,'NODE_COLLAPSED');
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
    await page.locator('#research-cards').getByRole('button',{name:'Dismiss',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('.research-card'));
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
    await page.locator('#focus-start').click();await page.waitForFunction(()=>document.querySelector('#focus-status').textContent.includes('ACTIVE'));
    assert.equal(focusCalls.at(-1).body.minutes,90);assert.deepEqual(focusCalls.at(-1).body.allowed_apps,['code.exe','devenv.exe','pycharm64.exe']);
    await page.locator('#focus-pause').click();await page.waitForFunction(()=>document.querySelector('#focus-status').textContent.startsWith('PAUSED'));
    await page.locator('#focus-resume').click();await page.waitForFunction(()=>document.querySelector('#focus-status').textContent.startsWith('ACTIVE'));
    await page.locator('#focus-stop').click();await page.waitForFunction(()=>document.querySelector('#focus-status').textContent.startsWith('STOPPED'));
    await page.locator('#j-input').fill("Focus mode for 90 minutes. I'm coding.");await page.locator('#j-send').click();
    await page.waitForFunction(()=>document.querySelector('#focus-status').textContent.startsWith('ACTIVE'));
    assert.equal(focusCalls.at(-1).body.goal,'coding');
    for(const [command,state,action] of [['pause focus','PAUSED','pause'],['resume focus','ACTIVE','resume'],['stop focus','STOPPED','stop']]){
      await page.locator('#j-input').fill(command);await page.locator('#j-send').click();
      await page.waitForFunction(expected=>document.querySelector('#focus-status').textContent.startsWith(expected),state);
      assert.equal(focusCalls.at(-1).action,action);
    }
    gmailAuth={state:'CONFIGURED',connected:true};await page.locator('#gmail-refresh').click();
    await page.waitForFunction(()=>document.querySelector('#gmail-state').textContent==='CONFIGURED'&&!document.querySelector('#gmail-inbox').disabled);
    const mail={id:'m1',thread_id:'t1',subject:'Release plan',from:'A Person <person@example.com>',date:'Today',snippet:'The deadline is Friday.',unread:true};
    await page.route('**/api/gmail/**',async route=>{const path=new URL(route.request().url()).pathname,body=route.request().postDataJSON();gmailCalls.push({path,body});
      const result=path.endsWith('/list')?{messages:[mail],result_size_estimate:1}:path.endsWith('/thread')?{id:'t1',messages:[{...mail,body:'The release deadline is Friday.'}]}:
        path.endsWith('/summarize')?{thread_id:'t1',message_count:1,summary:'The deadline is Friday.',mode:'local extract',warning:'Email content is untrusted.'}:
        path.endsWith('/send')?{ok:false,error:{code:'APPROVAL_REQUIRED'},approval:makeApproval('send_email',body)}:{id:'draft1',message:{threadId:'t1'}};
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(result)})});
    await page.locator('#gmail-inbox').click();await page.waitForFunction(()=>document.querySelector('.gmail-item'));
    await page.locator('#gmail-unread').click();await page.locator('#gmail-query').fill('from:person@example.com');await page.locator('#gmail-search').click();
    assert.deepEqual(gmailCalls.slice(0,3).map(c=>c.body.mode),['inbox','unread','search']);
    await page.locator('#gmail-card').getByRole('button',{name:'Open',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#gmail-thread').textContent.includes('release deadline'));
    await page.getByRole('button',{name:'Summarize',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#j-log').textContent.includes('Email summary: The deadline is Friday.'));
    await page.getByRole('button',{name:'Reply draft'}).click();await page.locator('#gmail-body').fill('Thank you for the update.');
    await page.locator('#gmail-create-draft').click();await page.waitForFunction(()=>document.querySelector('#gmail-draft-state').textContent.includes('Draft saved'));
    assert.equal(gmailCalls.at(-1).path,'/api/gmail/reply-draft');
    await page.evaluate(()=>window.confirmAnswer=false);await page.locator('#gmail-send').click();
    assert.equal(gmailCalls.some(c=>c.path==='/api/gmail/send'),false,'Canceling confirmation must not send');
    await page.evaluate(()=>window.confirmAnswer=true);await page.locator('#gmail-send').click();
    await page.waitForFunction(()=>document.querySelector('#gmail-draft-state').textContent.includes('Review it in ACTION APPROVALS'));
    page.once('dialog',dialog=>dialog.accept(dialog.defaultValue()));
    await page.locator('#approval-results button').first().click();
    await page.waitForFunction(()=>document.querySelector('#gmail-draft-state').textContent.includes('confirmed the message was sent'));
    assert.equal(gmailCalls.at(-1).body.confirmation,'SEND draft1');
    await page.locator('#gmail-new-draft').click();await page.locator('#gmail-to').fill('person@example.com');
    await page.locator('#gmail-subject').fill('Follow up');await page.locator('#gmail-body').fill('Here is the update.');
    await page.locator('#gmail-create-draft').click();await page.waitForFunction(()=>document.querySelector('#gmail-draft-state').textContent.includes('Draft saved'));
    assert.equal(gmailCalls.at(-1).path,'/api/gmail/draft');
    calendarAuth={state:'CONFIGURED',connected:true};await page.locator('#calendar-refresh').click();
    await page.waitForFunction(()=>document.querySelector('#calendar-state').textContent==='CONFIGURED'&&!document.querySelector('#calendar-create').disabled);
    const event={id:'event1',summary:'Planning',start:'2026-09-27T10:00:00+05:30',end:'2026-09-27T11:00:00+05:30',status:'confirmed'};
    await page.route('**/api/calendar/**',async route=>{const path=new URL(route.request().url()).pathname,body=route.request().method()==='POST'?route.request().postDataJSON():{};calendarCalls.push({path,body});
      const result=path.endsWith('/availability')?{busy:[{start:event.start,end:event.end}],errors:[]}:
        path.endsWith('/create')?{ok:false,error:{code:'APPROVAL_REQUIRED'},approval:makeApproval('create_calendar_event',body)}:
        path.endsWith('/reschedule')?{ok:false,error:{code:'APPROVAL_REQUIRED'},approval:makeApproval('reschedule_calendar_event',body)}:
        path.endsWith('/cancel')?{ok:false,error:{code:'APPROVAL_REQUIRED'},approval:makeApproval('cancel_calendar_event',body)}:{items:[event]};
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(result)})});
    await page.locator('#calendar-today').click();await page.locator('#calendar-tomorrow').click();
    await page.locator('#calendar-query').fill('Planning');await page.locator('#calendar-search').click();await page.waitForFunction(()=>document.querySelector('.calendar-item'));
    assert.ok(calendarCalls.some(c=>c.path==='/api/calendar/today'));assert.ok(calendarCalls.some(c=>c.path==='/api/calendar/tomorrow'));
    await page.locator('#calendar-availability').click();await page.waitForFunction(()=>document.querySelector('#calendar-action-state').textContent.includes('busy period'));
    await page.locator('#calendar-summary').fill('Review');await page.evaluate(()=>window.confirmAnswer=false);await page.locator('#calendar-create').click();
    assert.equal(calendarCalls.some(c=>c.path==='/api/calendar/create'),false,'Canceling event confirmation must not write');
    await page.evaluate(()=>window.confirmAnswer=true);await page.locator('#calendar-create').click();
    await page.waitForFunction(()=>document.querySelector('#calendar-action-state').textContent.includes('waiting in ACTION APPROVALS'));
    page.once('dialog',dialog=>dialog.accept(dialog.defaultValue()));
    await page.locator('#approval-results button').first().click();
    await page.waitForFunction(()=>document.querySelector('#calendar-action-state').textContent.includes('Calendar confirmed'));
    assert.equal(calendarCalls.find(c=>c.path==='/api/calendar/create').body.confirmation,'CREATE Review');
    await page.getByRole('button',{name:'Select',exact:true}).click();await page.locator('#calendar-reschedule').click();
    await page.waitForFunction(()=>document.querySelector('#calendar-action-state').textContent.includes('waiting in ACTION APPROVALS'));
    page.once('dialog',dialog=>dialog.accept(dialog.defaultValue()));
    await page.locator('#approval-results button').first().click();
    await page.waitForFunction(()=>document.querySelector('#calendar-action-state').textContent.includes('Calendar confirmed'));
    assert.equal(calendarCalls.find(c=>c.path==='/api/calendar/reschedule').body.confirmation,'RESCHEDULE event1');
    await page.getByRole('button',{name:'Select',exact:true}).click();await page.locator('#calendar-cancel').click();
    await page.waitForFunction(()=>document.querySelector('#calendar-action-state').textContent.includes('waiting in ACTION APPROVALS'));
    page.once('dialog',dialog=>dialog.accept(dialog.defaultValue()));
    await page.locator('#approval-results button').first().click();
    await page.waitForFunction(()=>document.querySelector('#calendar-action-state').textContent.includes('Calendar confirmed'));
    assert.equal(calendarCalls.find(c=>c.path==='/api/calendar/cancel').body.confirmation,'CANCEL event1');
    let speechAnswer='This sentence contains the word stop as echo bait.';
    await page.route('**/api/jarvis/chat',async route=>{
      const body=route.request().postDataJSON();
      if(body.message.toLowerCase().includes('open vs code'))return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({answer:'I staged this Windows action in Action Approvals. Review and approve it before it runs.',
        sources:[],node_ids:[],mode:'approval_required',warning:null,action:'focus',state:'IDLE',events:[],approval:makeApproval('open_application',{application:'VS Code'})})});
      if(body.message==='fixture speech')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({answer:speechAnswer,
        sources:[],node_ids:[],mode:'local',warning:null,action:'focus',state:'IDLE',events:[]})});
      if(body.message.toLowerCase().startsWith('research '))return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({answer:research?.answer||'Research fixture',
        sources:[],node_ids:[],mode:'research',warning:null,action:'focus',state:'IDLE',events:[],research_card:research})});
      return route.continue();
    });
    await page.locator('#j-input').fill('Jarvis, open VS Code.');await page.locator('#j-send').click();
    await page.waitForFunction(()=>document.querySelector('#j-log').textContent.includes('staged this Windows action'));
    await page.waitForFunction(()=>document.querySelector('#approval-results').textContent.includes('open application'));
    page.once('dialog',dialog=>dialog.accept(dialog.defaultValue()));await page.locator('#approval-results button').first().click();
    await page.waitForFunction(()=>document.querySelector('#approval-results').textContent==='');
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
    await page.locator('#j-mic').click();await page.waitForFunction(()=>document.querySelector('#j-status').textContent.includes('MIC ACTIVE'));
    const beforeMuteStop=await page.evaluate(()=>window.testRecognition.stopCount||0);await page.locator('#j-mute').click();
    await page.waitForFunction(()=>document.querySelector('#j-status').textContent==='GLOBAL MUTE · ON');
    assert.ok(await page.evaluate(()=>window.testRecognition.stopCount)>beforeMuteStop,'Global mute must stop active recognition');
    assert.equal(await page.locator('#j-mic').isDisabled(),true);assert.equal(await page.locator('#j-wake').isDisabled(),true);
    await page.locator('#j-mute').click();assert.equal(await page.locator('#j-mic').isDisabled(),false);
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
    console.log('PASS: probe+props, simulation, no-camera, saved cards/settings/automations, approval-gated Windows/Gmail/Calendar actions, voice interruption/wake/global mute, transient screen/camera frames, Focus Lock, responsive layout; zero page errors.');
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});

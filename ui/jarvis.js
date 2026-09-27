import {Galaxy} from './galaxy.js';

// Probe stays a test of the original engine, without chat or speech side effects.
if(!new URLSearchParams(location.search).has('probe')) boot().catch(e=>console.error('Jarvis UI unavailable',e));

async function boot(){
  document.body.insertAdjacentHTML('beforeend',`
    <button id="brain-toggle" aria-expanded="false">SECOND BRAIN</button>
    <section id="galaxy" aria-label="Second brain galaxy" hidden>
      <canvas id="galaxy-canvas"></canvas>
      <div id="galaxy-tools"><button data-act="all">All nodes</button><button data-act="expand">Expand</button><button data-act="collapse">Collapse</button></div>
      <nav id="galaxy-list" aria-label="Knowledge nodes"></nav><div id="galaxy-inspect"></div><div id="galaxy-caption"></div>
    </section>
    <aside id="jarvis-panel" aria-label="Jarvis assistant">
      <h2>JARVIS</h2><div class="sub">YOUR LOCAL SECOND BRAIN</div>
      <div id="j-status" role="status" aria-live="polite">CONNECTING</div>
      <div id="j-selection" class="sub">Select a note, or search your memory.</div>
      <div id="j-log" role="log" aria-live="polite"></div>
      <form id="j-form"><label class="sub" for="j-input">Ask Jarvis</label><input id="j-input" placeholder="Find my notes about…" maxlength="4000" autocomplete="off"><div class="j-row" style="margin-top:8px"><button id="j-send">Send</button><button type="button" id="j-summary">Summarize selected</button></div></form>
      <div class="j-row"><button id="j-mic">Use browser voice</button><button id="j-stop">Stop speech</button><label class="sub"><input type="checkbox" id="j-speak"> Read aloud</label><label class="sub"><input type="checkbox" id="j-wake"> Wake mode</label></div>
      <div class="sub" id="j-voice-note">Voice is opt-in and may use your browser’s online speech service.</div>
      <div class="sub" id="j-transcript" role="status" aria-live="polite"></div>
      <div class="j-row"><button id="j-screen">Explain current screen once</button><span id="j-screen-state" class="sub" role="status" aria-live="polite">SCREEN OFF</span></div>
      <div class="j-row"><button id="j-eyes">Look at this once</button><span id="j-camera-state" class="sub" role="status" aria-live="polite">CAMERA READY</span></div>
      <section id="focus-card" aria-label="H.O.L.O Focus Lock">
        <h3>H.O.L.O FOCUS LOCK</h3><div id="focus-status" class="sub" role="status" aria-live="polite">FOCUS IDLE</div><div id="focus-history" class="sub"></div>
        <div class="focus-fields"><label class="sub">Minutes<input id="focus-minutes" type="number" min="1" max="480" value="90"></label>
          <label class="sub">Goal<input id="focus-goal" maxlength="120" value="Deep work"></label></div>
        <label class="sub">Allowed app names, comma separated<input id="focus-allowed" value="code.exe, devenv.exe, pycharm64.exe"></label>
        <label class="sub">Distracting app or site titles<input id="focus-distracting" value="instagram, tiktok, youtube, reddit"></label>
        <div class="j-row"><button id="focus-start">Start</button><button id="focus-pause">Pause</button><button id="focus-resume">Resume</button><button id="focus-stop">Stop</button></div>
      </section>
      <div class="j-row"><button id="j-index">Reindex notes</button><button id="j-embed" hidden>Build semantic index</button><span class="sub" id="j-count"></span></div>
    </aside>
    <section id="research-cards" aria-label="Temporary research cards"></section>
    <section id="source-reader" role="dialog" aria-modal="true" aria-label="Source document" hidden>
      <div class="j-row"><button id="source-close">Close source</button><button id="source-summary">Summarize this</button></div><h2></h2><small></small><pre></pre>
    </section>`);
  const $=id=>document.getElementById(id);
  let sid,selected=null,busy=false,galaxy=null,speechToken=0,lastFocus=null,speaking=false;
  let resumeWake=()=>{}, speechRecognizer=null, speechEndTimer=null, interruptCooldownUntil=0, spokenText='';
  const status=value=>{$('j-status').textContent=value;$('jarvis-panel').dataset.state=value;};
  async function api(path,data){const r=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const result=await r.json();if(!r.ok)throw new Error(result.error||'Request failed');return result}
  sid=sessionStorage.getItem('jarvis_session');
  if(sid){try{await api('/api/jarvis/state?session_id='+encodeURIComponent(sid))}catch(_){sid=null}}
  if(!sid)sid=(await api('/api/jarvis/session',{})).session_id;
  sessionStorage.setItem('jarvis_session',sid);
  const health=await api('/api/health');
  status(health.mode==='local'?'IDLE · LOCAL MODE':'IDLE · ASTRA CONFIGURED');
  $('j-embed').hidden=!health.embeddings_enabled;
  function entry(text,type='assistant',sources=[],warning=null){const el=document.createElement('div');el.className='j-entry '+type;
    const body=document.createElement('div');body.textContent=text;el.append(body);
    if(warning){const w=document.createElement('div');w.className='j-warning';w.textContent=warning;el.append(w)}
    const links=document.createElement('div');links.className='j-sources';
    for(const s of sources){const b=document.createElement('button');b.textContent=s.relative_path||s.title;b.title=s.path;b.onclick=()=>openSource(s.document_id).catch(showError);links.append(b)}
    el.append(links);$('j-log').append(el);while($('j-log').children.length>30)$('j-log').firstChild.remove();$('j-log').scrollTop=$('j-log').scrollHeight;
  }
  function researchCard(card){
    let el=[...$('research-cards').children].find(x=>x.dataset.id===card.id);
    if(!el){el=document.createElement('article');el.className='research-card';el.dataset.id=card.id;$('research-cards').prepend(el)}
    el.replaceChildren();
    const heading=document.createElement('h3');heading.textContent='RESEARCH · '+card.query;
    const badge=document.createElement('small');badge.textContent=card.status.toUpperCase()+' · '+new Date(card.researched_at*1000).toLocaleString();
    const summary=document.createElement('p');summary.textContent=card.answer.slice(0,240)+(card.answer.length>240?'…':'');
    const detail=document.createElement('div');detail.className='research-detail';detail.hidden=true;
    const full=document.createElement('p');full.textContent=card.answer;detail.append(full);
    const sources=document.createElement('div');sources.className='research-sources';
    for(const s of card.sources){const link=document.createElement('a');link.href=s.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=s.title;link.title=s.url;
      sources.append(link);if(s.snippet){const note=document.createElement('small');note.textContent='Cited answer excerpt: '+s.snippet;sources.append(note)}}
    detail.append(sources);
    const controls=document.createElement('div');controls.className='j-row';
    const expand=document.createElement('button');expand.textContent='Expand';expand.onclick=()=>{detail.hidden=!detail.hidden;summary.hidden=!detail.hidden;expand.textContent=detail.hidden?'Expand':'Collapse'};
    const keep=document.createElement('button');keep.textContent='Keep card';keep.disabled=card.status!=='temporary';
    const save=document.createElement('button');save.textContent=card.status==='saved'?'Saved to brain':'Save to brain';save.disabled=card.status==='saved';
    const dismiss=document.createElement('button');dismiss.textContent='Dismiss';
    async function act(action){for(const b of [keep,save,dismiss])b.disabled=true;
      try{const response=await api('/api/research/card',{session_id:sid,card_id:card.id,action});
        if(action==='dismiss')el.remove();else{researchCard(response.card);if(action==='save'){await refresh();entry('Research saved to the second brain. Its cited web text remains marked untrusted.')}}
      }catch(e){showError(e);researchCard(card)}}
    keep.onclick=()=>act('keep');save.onclick=()=>act('save');dismiss.onclick=()=>act('dismiss');
    controls.append(expand,keep,save,dismiss);
    el.append(heading,badge,summary,detail,controls);
  }
  function showError(e){status('ERROR');entry(e.message||'Operation unavailable','assistant')}
  function isScreenRequest(message){return /\b(screen|what am i looking at|what button should i click|why is this error happening|explain this screen)\b/i.test(message)}
  function isCameraRequest(message){return /\b(look at this|what am i holding|what is in front of me)\b/i.test(message)}
  async function frameJpeg(stream){
    const track=stream.getVideoTracks()[0];if(!track)throw new Error('No visual source was selected');
    const video=document.createElement('video');video.muted=true;video.playsInline=true;video.srcObject=stream;
    try{await video.play();if(!video.videoWidth)await new Promise((resolve,reject)=>{
      const timeout=setTimeout(()=>reject(new Error('Video frame was unavailable')),4000);
      video.addEventListener('loadedmetadata',()=>{clearTimeout(timeout);resolve()},{once:true});
    });
      const scale=Math.min(1,1280/video.videoWidth,800/video.videoHeight),canvas=document.createElement('canvas');
      canvas.width=Math.max(1,Math.round(video.videoWidth*scale));canvas.height=Math.max(1,Math.round(video.videoHeight*scale));
      canvas.getContext('2d').drawImage(video,0,0,canvas.width,canvas.height);let imageDataUrl='';
      for(const quality of [.62,.5,.38]){imageDataUrl=canvas.toDataURL('image/jpeg',quality);if((imageDataUrl.length-23)*.75<500000)break}
      canvas.width=canvas.height=1;
      if((imageDataUrl.length-23)*.75>512000)throw new Error('Visual frame is too large to send safely');
      return imageDataUrl;
    }finally{video.srcObject=null}
  }
  async function captureScreen(question){
    if(busy)return;const chooser=navigator.mediaDevices?.getDisplayMedia;
    if(!chooser){entry('Screen sharing is unavailable in this browser or context.','assistant');return}
    let permission;
    try{permission=chooser.call(navigator.mediaDevices,{video:{frameRate:1},audio:false})}
    catch(e){entry('Screen capture was not started. Click Explain current screen once and allow a display in the browser chooser.','assistant');return}
    busy=true;$('j-send').disabled=true;$('j-screen').disabled=true;$('j-screen-state').textContent='SCREEN SHARING ACTIVE · CAPTURING ONE FRAME';
    status('SCREEN SHARING ACTIVE');await stopSpeech();entry(question,'user');
    let stream=null,imageDataUrl='';
    try{
      stream=await permission;imageDataUrl=await frameJpeg(stream);
      $('j-screen-state').textContent='SCREEN ANALYZING · IMAGE CAPTURED ONCE';
      for(const t of stream.getTracks())t.stop();stream=null;
      const result=await api('/api/vision/screen',{question,image_data_url:imageDataUrl});imageDataUrl='';
      entry(result.answer,'assistant');for(const item of result.observations||[])entry('• '+item,'assistant');
      if(result.caution)entry(result.caution,'assistant');status('IDLE');
    }catch(e){imageDataUrl='';entry(e.name==='NotAllowedError'?'Screen sharing was cancelled or denied. No screenshot was analyzed.':(e.message||'Screen analysis is unavailable.'),'assistant');status('IDLE')}
    finally{if(stream)for(const t of stream.getTracks())t.stop();
      $('j-screen-state').textContent='SCREEN OFF';$('j-send').disabled=false;$('j-screen').disabled=false;busy=false;resumeWake()}
  }
  async function captureCamera(question){
    if(busy)return;const getCamera=navigator.mediaDevices?.getUserMedia;
    if(!getCamera){$('j-camera-state').textContent='CAMERA UNAVAILABLE';entry('This browser cannot access a camera. H.O.L.O simulation remains available.','assistant');return}
    let request;try{request=getCamera.call(navigator.mediaDevices,{video:{facingMode:'environment'},audio:false})}
    catch(e){$('j-camera-state').textContent='CAMERA ERROR';entry('Camera could not be started. Allow camera access after pressing Look at this once.','assistant');return}
    busy=true;$('j-send').disabled=true;$('j-eyes').disabled=true;$('j-camera-state').textContent='CAMERA ACTIVE';
    status('CAMERA ACTIVE · CAPTURING ONE FRAME');await stopSpeech();entry(question,'user');
    let stream=null,imageDataUrl='';
    try{stream=await request;imageDataUrl=await frameJpeg(stream);
      for(const t of stream.getTracks())t.stop();stream=null;$('j-camera-state').textContent='CAMERA READY';
      const result=await api('/api/vision/camera',{question,image_data_url:imageDataUrl});imageDataUrl='';
      entry(result.answer,'assistant');for(const item of result.observations||[])entry('• '+item,'assistant');
      if(result.caution)entry(result.caution,'assistant');status('IDLE');
    }catch(e){imageDataUrl='';const denied=e.name==='NotAllowedError';
      $('j-camera-state').textContent=e.name==='NotFoundError'?'CAMERA UNAVAILABLE':'CAMERA ERROR';
      entry(denied?'Camera access was denied. No frame was analyzed.':(e.message||'Camera analysis is unavailable.'),'assistant');status('IDLE')}
    finally{if(stream)for(const t of stream.getTracks())t.stop();
      $('j-send').disabled=false;$('j-eyes').disabled=false;busy=false;resumeWake()}
  }
  async function select(id){await api('/api/jarvis/context',{session_id:sid,document_id:id});selected=id;
    const doc=await api('/api/memory/document?id='+encodeURIComponent(id));$('j-selection').textContent='Selected: '+doc.title;return doc}
  async function openSource(id){const doc=await select(id);const reader=$('source-reader');reader.querySelector('h2').textContent=doc.title;
    reader.querySelector('small').textContent=doc.path+' · indexed snapshot';reader.querySelector('pre').textContent=doc.body;lastFocus=document.activeElement;reader.hidden=false;$('source-close').focus();galaxy?.focus([id])}
  function closeSource(){$('source-reader').hidden=true;lastFocus?.focus()}
  $('source-close').onclick=closeSource;
  $('source-reader').addEventListener('keydown',e=>{if(e.key==='Escape')closeSource();if(e.key==='Tab'){const buttons=[$('source-close'),$('source-summary')];e.preventDefault();buttons[document.activeElement===buttons[0]?1:0].focus()}});
  $('source-summary').onclick=()=>{closeSource();ask('Summarize this').catch(showError)};
  addEventListener('holo-selection',e=>select(e.detail.document_id).catch(showError));
  try {galaxy=new Galaxy($('galaxy'),(id,open)=>(open?openSource(id):select(id)).catch(showError))}
  catch(_){$('galaxy-caption').textContent='WebGL unavailable. Source search and reader remain available.'}
  async function refresh(){const [graph,memory]=await Promise.all([api('/api/graph'),api('/api/memory/status')]);galaxy?.setData(graph);$('j-count').textContent=memory.active_sources+' sources';
    if(memory.errors.length)entry('Some files could not be indexed.','assistant',[],memory.errors.map(e=>e.relative_path+': '+e.error).join('\n'))}
  await refresh();
  try{for(const card of (await api('/api/research/cards?session_id='+encodeURIComponent(sid))).cards)researchCard(card)}catch(e){showError(e)}
  $('brain-toggle').onclick=()=>{$('galaxy').hidden=!$('galaxy').hidden;$('brain-toggle').setAttribute('aria-expanded',String(!$('galaxy').hidden))};
  async function stopSpeech(interrupted=false){speechToken++;clearTimeout(speechEndTimer);speechEndTimer=null;
    const interruptRecognizer=speechRecognizer;speechRecognizer=null;if(interruptRecognizer)try{interruptRecognizer.stop()}catch(_){}
    window.speechSynthesis?.cancel();const wasSpeaking=speaking;speaking=false;
    if(wasSpeaking||interrupted){await api('/api/jarvis/voice-state',{session_id:sid,state:'INTERRUPTED'}).catch(()=>{});
      await api('/api/jarvis/voice-state',{session_id:sid,state:'IDLE'}).catch(()=>{})}
    if(!busy)status('IDLE');resumeWake()}
  $('j-stop').onclick=()=>stopSpeech().catch(showError);
  function normalizeSpeech(text){return text.toLocaleLowerCase().replace(/[^\p{L}\p{N} ]/gu,' ').replace(/\s+/g,' ').trim()}
  function isInterruption(text){return /^(stop|wait|enough|that s enough|thats enough|that is enough|cancel|quiet|thank you|thanks|that s good|thats good|that is good)$/.test(normalizeSpeech(text))}
  function speak(text){if(!$('j-speak').checked||!window.speechSynthesis||typeof SpeechSynthesisUtterance==='undefined')return;
    const token=++speechToken;spokenText=text;interruptCooldownUntil=Date.now()+850;
    const utterance=new SpeechSynthesisUtterance(text);
    utterance.onstart=()=>{if(token!==speechToken)return;speaking=true;status('SPEAKING · INTERRUPT READY');resumeWake();
      api('/api/jarvis/voice-state',{session_id:sid,state:'SPEAKING'}).catch(()=>{});
      if(Recognition)listenForInterruption(token)};
    utterance.onend=utterance.onerror=()=>{if(token!==speechToken)return;clearTimeout(speechEndTimer);speechEndTimer=null;
      const current=speechRecognizer;speechRecognizer=null;if(current)try{current.stop()}catch(_){}
      speaking=false;status('IDLE');api('/api/jarvis/voice-state',{session_id:sid,state:'IDLE'}).then(()=>{interruptCooldownUntil=Date.now()+900;resumeWake()}).catch(()=>{})};
    window.speechSynthesis.speak(utterance)}
  function listenForInterruption(token){if(!speaking||token!==speechToken||speechRecognizer||!Recognition)return;
    const current=new Recognition();speechRecognizer=current;current.lang=navigator.language||'en-US';current.continuous=false;current.interimResults=true;
    current.onresult=e=>{if(speechRecognizer!==current||!speaking||token!==speechToken||Date.now()<interruptCooldownUntil)return;
      for(const result of Array.from(e.results||[])){if(!result.isFinal)continue;const heard=result[0]?.transcript||'',norm=normalizeSpeech(heard),spoken=normalizeSpeech(spokenText);
        if(!isInterruption(heard))continue;
        if(spoken.includes(norm))continue;
        interruptCooldownUntil=Date.now()+900;stopSpeech(true).catch(showError);return}}
    current.onerror=e=>{if(speechRecognizer!==current)return;speechRecognizer=null;
      try{current.stop()}catch(_){}
      if(e.error==='not-allowed'||e.error==='service-not-allowed'){$('j-voice-note').textContent='Microphone access was denied. Use Stop speech or enable browser microphone access.'}}
    current.onend=()=>{if(speechRecognizer!==current)return;speechRecognizer=null;
      if(speaking&&token===speechToken){speechEndTimer=setTimeout(()=>listenForInterruption(token),220)}};
    try{current.start()}catch(_){speechRecognizer=null}}
  $('j-speak').onchange=()=>{if(!$('j-speak').checked)speakMute()};
  function speakMute(){stopSpeech(false).catch(showError)}
  async function ask(message){if(busy||!message.trim())return;if(isCameraRequest(message)){captureCamera(message).catch(showError);return}
    if(isScreenRequest(message)){captureScreen(message).catch(showError);return}
    if(/\bpause focus\b/i.test(message)){await focusAction('/api/focus/pause',{});entry('Focus session paused.');return}
    if(/\bresume focus\b/i.test(message)){await focusAction('/api/focus/resume',{});entry('Focus session resumed.');return}
    if(/\bstop focus\b/i.test(message)){await focusAction('/api/focus/stop',{});entry('Focus session stopped.');return}
    if(/\b(start focus|focus mode|focus lock)\b/i.test(message)){
      const duration=message.match(/\b(\d{1,3})\s*minutes?\b/i),goal=message.match(/\b(?:i am|i'm|im)\s+(.+)$/i);
      await focusAction('/api/focus/start',{minutes:Number(duration?.[1]||$('focus-minutes').value||90),
        goal:goal?.[1]?.replace(/[.!?]+$/,'').slice(0,120)||$('focus-goal').value,allowed_apps:focusRules('focus-allowed'),distractions:focusRules('focus-distracting')});
      entry('Focus session started.');return;
    }
    busy=true;await stopSpeech();$('j-send').disabled=true;status('RETRIEVING');entry(message,'user');
    const poll=setInterval(()=>api('/api/jarvis/state?session_id='+encodeURIComponent(sid)).then(s=>{if(busy)status(s.state)}).catch(()=>{}),250);
    try{const result=await api('/api/jarvis/chat',{session_id:sid,message,selected_id:selected,spoken:$('j-speak').checked});
      entry(result.answer,'assistant',result.sources,result.warning);status('IDLE · '+result.mode.toUpperCase());
      if(result.research_card)researchCard(result.research_card);
      if(result.sources[0]){selected=result.sources[0].document_id;$('j-selection').textContent='Selected: '+result.sources[0].title}
      if(result.node_ids.length){$('galaxy').hidden=false;$('brain-toggle').setAttribute('aria-expanded','true');
        if(galaxy&&!galaxy.meshes.has(result.node_ids[0]))galaxy.setData(await api('/api/graph?focus='+encodeURIComponent(result.node_ids[0])));
        galaxy?.focus(result.node_ids)}
      if(result.action==='open'&&selected)await openSource(selected);
      speak(result.mode==='research'?result.answer.slice(0,550):result.answer);
    }finally{clearInterval(poll);busy=false;$('j-send').disabled=false}}
  $('j-form').onsubmit=e=>{e.preventDefault();const q=$('j-input').value;$('j-input').value='';ask(q).catch(showError)};
  $('j-screen').onclick=()=>captureScreen($('j-input').value.trim()||'What am I looking at?').catch(showError);
  $('j-eyes').onclick=()=>captureCamera($('j-input').value.trim()||'Look at this.').catch(showError);
  function focusRules(id){return $(id).value.split(',').map(x=>x.trim()).filter(Boolean)}
  function drawFocus(state){
    const minutes=Math.ceil((state.remaining_seconds||0)/60),parts=[state.state];
    if(['ACTIVE','PAUSED'].includes(state.state))parts.push(minutes+' min left',state.distraction_count+' distractions');
    if(state.result)parts.push(state.result);
    if(!state.monitor_supported)parts.push('app monitoring unavailable; timer only');
    $('focus-status').textContent=parts.join(' · ');
    const last=state.recent_sessions?.at(-1);
    $('focus-history').textContent=last?`Last: ${last.goal} · ${last.result} · ${Math.round((last.focused_seconds||0)/60)} focused min · ${last.distraction_count} distractions`:'';
    const active=state.state==='ACTIVE',paused=state.state==='PAUSED';
    $('focus-start').disabled=active||paused;$('focus-pause').disabled=!active;
    $('focus-resume').disabled=!paused;$('focus-stop').disabled=!active&&!paused;
    if(state.warning){entry(state.warning,'assistant');if(!$('j-speak').disabled&&$('j-speak').checked&&!busy&&!speaking)speak(state.warning)}
  }
  async function focusAction(action,payload={}){try{const state=action==='/api/focus'?await api('/api/focus'):await api(action,payload);drawFocus(state);return state}
    catch(e){entry(e.message||'Focus action failed.','assistant');throw e}}
  await focusAction('/api/focus');
  $('focus-start').onclick=()=>focusAction('/api/focus/start',{minutes:Number($('focus-minutes').value),goal:$('focus-goal').value,
    allowed_apps:focusRules('focus-allowed'),distractions:focusRules('focus-distracting')}).catch(()=>{});
  $('focus-pause').onclick=()=>focusAction('/api/focus/pause',{}).catch(()=>{});
  $('focus-resume').onclick=()=>focusAction('/api/focus/resume',{}).catch(()=>{});
  $('focus-stop').onclick=()=>focusAction('/api/focus/stop',{}).catch(()=>{});
  setInterval(()=>focusAction('/api/focus').catch(()=>{}),5000);
  $('j-summary').onclick=()=>ask('Summarize this').catch(showError);
  $('j-index').onclick=async()=>{try{status('INDEXING');await api('/api/memory/reindex',{});await refresh();status('IDLE')}catch(e){showError(e)}};
  $('j-embed').onclick=async()=>{try{status('EMBEDDING · SENDING NOTE CHUNKS TO OPENAI');await api('/api/memory/embed',{});await refresh();status('IDLE')}catch(e){showError(e)}};
  const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!Recognition){$('j-mic').disabled=true;$('j-wake').disabled=true;$('j-voice-note').textContent='Speech recognition unavailable in this browser. Text mode is ready.'}
  else {let recognition=null,voiceProcessing=false,voiceStarting=false,wakeRecognition=null,wakeTimer=null,wakeArmedUntil=0;
    function stopWake(){clearTimeout(wakeTimer);wakeTimer=null;if(wakeRecognition){const current=wakeRecognition;wakeRecognition=null;current.stop()}}
    function scheduleWake(){clearTimeout(wakeTimer);if(!$('j-wake').checked||speaking||busy||recognition||voiceProcessing)return;
      wakeTimer=setTimeout(()=>{wakeTimer=null;startWake()},Math.max(350,interruptCooldownUntil-Date.now()))}
    function startWake(){if(!$('j-wake').checked||speaking||busy||recognition||wakeRecognition)return;
      const current=new Recognition();wakeRecognition=current;current.lang=navigator.language||'en-US';current.continuous=false;current.interimResults=false;
      current.onresult=e=>{const final=Array.from(e.results||[]).find(r=>r.isFinal);if(!final||wakeRecognition!==current)return;
        const heard=(final[0]?.transcript||'').trim();const match=heard.match(/\bjarvis\b[\s,.:;!?]*(.*)$/i);
        if(!match&&Date.now()>wakeArmedUntil)return;
        const command=(match?match[1]:heard).trim();stopWake();
        (async()=>{try{if(match){await api('/api/jarvis/voice-state',{session_id:sid,state:'WAKE_DETECTED'});
            await api('/api/jarvis/voice-state',{session_id:sid,state:'LISTENING'});status('WAKE DETECTED · LISTENING')}
          if(!command){wakeArmedUntil=Date.now()+8000;scheduleWake();return}
          wakeArmedUntil=0;await api('/api/jarvis/voice-state',{session_id:sid,state:'TRANSCRIBING'});
          await api('/api/jarvis/voice-state',{session_id:sid,state:'IDLE'});await ask(command)}
          catch(err){showError(err)}finally{scheduleWake()}})();
      };
      current.onerror=e=>{if(wakeRecognition!==current)return;wakeRecognition=null;$('j-wake').checked=false;try{current.stop()}catch(_){}
        wakeArmedUntil=0;entry('Wake mode stopped: '+(e.error||'microphone unavailable'));status('IDLE')};
      current.onend=()=>{if(wakeRecognition!==current)return;wakeRecognition=null;
        if(wakeArmedUntil&&Date.now()>wakeArmedUntil){wakeArmedUntil=0;api('/api/jarvis/voice-state',{session_id:sid,state:'IDLE'}).catch(()=>{});status('IDLE')}
        scheduleWake()};
      try{current.start()}catch(e){wakeRecognition=null;$('j-wake').checked=false;entry('Wake mode unavailable: '+e.message)}
    }
    resumeWake=()=>{if(speaking||busy||recognition||voiceProcessing)stopWake();else scheduleWake()};
    $('j-wake').onchange=async()=>{if($('j-wake').checked){$('j-voice-note').textContent='Wake mode active. Browser microphone recognition may use an online speech service.';
        scheduleWake()}else{stopWake();wakeArmedUntil=0;$('j-voice-note').textContent='Voice is opt-in and may use your browser’s online speech service.';
        try{await api('/api/jarvis/voice-state',{session_id:sid,state:'IDLE'})}catch(_){}}};
    const resetMic=()=>{$('j-mic').textContent='Use browser voice';$('j-mic').disabled=false};
    $('j-mic').onclick=async()=>{if(busy||voiceProcessing||voiceStarting)return;
      if(recognition){const current=recognition;recognition=null;current.stop();resetMic();$('j-transcript').textContent='';
        await api('/api/jarvis/voice-state',{session_id:sid,state:'IDLE'});status('IDLE');return}
      stopWake();wakeArmedUntil=0;voiceStarting=true;$('j-mic').disabled=true;
      try{await stopSpeech();const current=new Recognition();recognition=current;
        current.lang=navigator.language||'en-US';current.continuous=false;current.interimResults=true;
        current.onstart=()=>{if(recognition!==current)return;voiceStarting=false;$('j-mic').disabled=false;status('LISTENING · MIC ACTIVE');$('j-mic').textContent='Stop listening'};
        current.onresult=e=>{if(recognition!==current||voiceProcessing)return;
          const results=Array.from(e.results||[]);const transcript=results.map(r=>r[0]?.transcript||'').join(' ').trim();
          $('j-transcript').textContent=transcript?'Heard: '+transcript:'';
          if(!results.some(r=>r.isFinal)||!transcript)return;
          voiceProcessing=true;recognition=null;current.stop();resetMic();
          (async()=>{try{await api('/api/jarvis/voice-state',{session_id:sid,state:'TRANSCRIBING'});status('TRANSCRIBING');
            await api('/api/jarvis/voice-state',{session_id:sid,state:'IDLE'});$('j-transcript').textContent='';await ask(transcript)}
            catch(err){showError(err)}finally{voiceProcessing=false}})();
        };
        current.onerror=e=>{if(recognition!==current)return;recognition=null;voiceStarting=false;resetMic();try{current.stop()}catch(_){}
          $('j-transcript').textContent='';entry('Microphone unavailable: '+(e.error||'unknown error'));
          if(e.error==='not-allowed'||e.error==='service-not-allowed')$('j-wake').checked=false;
          status('ERROR');api('/api/jarvis/voice-state',{session_id:sid,state:'ERROR'}).then(()=>api('/api/jarvis/voice-state',{session_id:sid,state:'IDLE'})).then(()=>scheduleWake()).catch(()=>{})};
        current.onend=()=>{if(recognition!==current)return;recognition=null;voiceStarting=false;resetMic();
          $('j-transcript').textContent='';if(!busy&&!voiceProcessing){api('/api/jarvis/voice-state',{session_id:sid,state:'IDLE'}).then(()=>scheduleWake()).catch(()=>{});status('IDLE')}};
        await api('/api/jarvis/voice-state',{session_id:sid,state:'LISTENING'});current.start();
      }catch(e){recognition=null;voiceStarting=false;resetMic();$('j-transcript').textContent='';
        api('/api/jarvis/voice-state',{session_id:sid,state:'ERROR'}).then(()=>api('/api/jarvis/voice-state',{session_id:sid,state:'IDLE'})).catch(()=>{});showError(e)}};
  }
  window.jarvisUI={summarize:async id=>{try{await select(id);await ask('Summarize this')}catch(e){showError(e)}},select,openSource,ask,
    focus:ids=>{galaxy?.focus(ids)},get selected(){return selected}};
  entry('Ready. Search your notes, select a source, then ask “summarize this” or “show related notes”.');
}

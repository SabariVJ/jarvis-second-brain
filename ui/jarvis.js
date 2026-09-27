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
      <div class="j-row"><button id="j-mic">Use browser voice</button><button id="j-stop">Stop speech</button><label class="sub"><input type="checkbox" id="j-speak"> Read aloud</label></div>
      <div class="sub" id="j-voice-note">Voice is opt-in and may use your browser’s online speech service.</div>
      <div class="sub" id="j-transcript" role="status" aria-live="polite"></div>
      <div class="j-row"><button id="j-index">Reindex notes</button><button id="j-embed" hidden>Build semantic index</button><span class="sub" id="j-count"></span></div>
    </aside>
    <section id="research-cards" aria-label="Temporary research cards"></section>
    <section id="source-reader" role="dialog" aria-modal="true" aria-label="Source document" hidden>
      <div class="j-row"><button id="source-close">Close source</button><button id="source-summary">Summarize this</button></div><h2></h2><small></small><pre></pre>
    </section>`);
  const $=id=>document.getElementById(id);
  let sid,selected=null,busy=false,galaxy=null,speechToken=0,lastFocus=null,speaking=false;
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
  async function stopSpeech(){speechToken++;window.speechSynthesis?.cancel();if(speaking){speaking=false;
    await api('/api/jarvis/voice-state',{session_id:sid,state:'INTERRUPTED'});await api('/api/jarvis/voice-state',{session_id:sid,state:'IDLE'})}if(!busy)status('IDLE')}
  $('j-stop').onclick=()=>stopSpeech().catch(showError);
  function speak(text){if(!$('j-speak').checked||!window.speechSynthesis)return;const token=++speechToken;
    const utterance=new SpeechSynthesisUtterance(text);utterance.onstart=()=>{speaking=true;status('SPEAKING');api('/api/jarvis/voice-state',{session_id:sid,state:'SPEAKING'}).catch(()=>{})};
    utterance.onend=utterance.onerror=()=>{if(token===speechToken){speaking=false;status('IDLE');api('/api/jarvis/voice-state',{session_id:sid,state:'IDLE'}).catch(()=>{})}};window.speechSynthesis.speak(utterance)}
  async function ask(message){if(busy||!message.trim())return;busy=true;await stopSpeech();$('j-send').disabled=true;status('RETRIEVING');entry(message,'user');
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
  $('j-summary').onclick=()=>ask('Summarize this').catch(showError);
  $('j-index').onclick=async()=>{try{status('INDEXING');await api('/api/memory/reindex',{});await refresh();status('IDLE')}catch(e){showError(e)}};
  $('j-embed').onclick=async()=>{try{status('EMBEDDING · SENDING NOTE CHUNKS TO OPENAI');await api('/api/memory/embed',{});await refresh();status('IDLE')}catch(e){showError(e)}};
  const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!Recognition){$('j-mic').disabled=true;$('j-voice-note').textContent='Speech recognition unavailable in this browser. Text mode is ready.'}
  else {let recognition=null,voiceProcessing=false,voiceStarting=false;
    const resetMic=()=>{$('j-mic').textContent='Use browser voice';$('j-mic').disabled=false};
    $('j-mic').onclick=async()=>{if(busy||voiceProcessing||voiceStarting)return;
      if(recognition){const current=recognition;recognition=null;current.stop();resetMic();$('j-transcript').textContent='';
        await api('/api/jarvis/voice-state',{session_id:sid,state:'IDLE'});status('IDLE');return}
      voiceStarting=true;$('j-mic').disabled=true;
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
        current.onerror=e=>{if(recognition!==current)return;recognition=null;voiceStarting=false;resetMic();
          $('j-transcript').textContent='';entry('Microphone unavailable: '+(e.error||'unknown error'));
          status('ERROR');api('/api/jarvis/voice-state',{session_id:sid,state:'ERROR'}).then(()=>api('/api/jarvis/voice-state',{session_id:sid,state:'IDLE'})).catch(()=>{})};
        current.onend=()=>{if(recognition!==current)return;recognition=null;voiceStarting=false;resetMic();
          $('j-transcript').textContent='';if(!busy&&!voiceProcessing){api('/api/jarvis/voice-state',{session_id:sid,state:'IDLE'}).catch(()=>{});status('IDLE')}};
        await api('/api/jarvis/voice-state',{session_id:sid,state:'LISTENING'});current.start();
      }catch(e){recognition=null;voiceStarting=false;resetMic();$('j-transcript').textContent='';
        api('/api/jarvis/voice-state',{session_id:sid,state:'ERROR'}).then(()=>api('/api/jarvis/voice-state',{session_id:sid,state:'IDLE'})).catch(()=>{});showError(e)}};
  }
  window.jarvisUI={summarize:async id=>{try{await select(id);await ask('Summarize this')}catch(e){showError(e)}},select,openSource,ask,
    focus:ids=>{galaxy?.focus(ids)},get selected(){return selected}};
  entry('Ready. Search your notes, select a source, then ask “summarize this” or “show related notes”.');
}

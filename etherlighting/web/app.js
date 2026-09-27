'use strict';
const $ = id => document.getElementById(id);
let state = null, editing = null, busy = false, editingPreset = null, presetSignature = '';
const csrf = document.querySelector('meta[name="csrf-token"]').content;
function node(tag, text, className) { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(className)n.className=className; return n; }
function toast(text){$('toast').textContent=text; $('toast').hidden=false; clearTimeout(toast.timer); toast.timer=setTimeout(()=>$('toast').hidden=true,6500);}
async function request(path, body){
  const response=await fetch('./api/'+path, body===undefined ? {cache:'no-store'} : {method:'POST',headers:{'Content-Type':'application/json','X-Etherlighting-CSRF':csrf},body:JSON.stringify(body)});
  const value=await response.json(); if(!response.ok)throw new Error(value.error||'Request failed'); return value;
}
async function action(path,body={}){if(busy)return;busy=true;try{state=await request(path,body);render();return true;}catch(e){toast(e.message);return false;}finally{busy=false;}}
function edit(address='',row=null){
  editing=state.rules.rules.find(r=>r.mac===address)||null;
  const r=editing||{mac:address,name:row?.name||'',color:'#38BDF8',brightness:30,enabled:true,group:'',allow_shared:false};
  $('name').value=r.name;$('mac').value=r.mac;$('mac').readOnly=!!editing;$('color').value=r.color;
  $('brightness').value=r.brightness;$('level').value=r.brightness+'%';$('enabled').checked=r.enabled;$('shared').checked=r.allow_shared;
  $('preset').value=state.presets.some(p=>p.name===r.group&&p.color.toUpperCase()===r.color.toUpperCase())?r.group:'';$('remove').hidden=!editing;$('editor').showModal();
}
function editPreset(preset=null){
  editingPreset=preset?.name??null;
  $('preset-title').textContent=preset?'Edit preset':'Add preset';
  $('preset-name').value=preset?.name||'';$('preset-color').value=preset?.color||'#38bdf8';
  $('delete-preset').hidden=!preset;$('preset-editor').showModal();
}
function renderPresets(){
  const signature=JSON.stringify(state.presets);
  if(signature===presetSignature)return;
  presetSignature=signature;
  const selected=$('preset').value;
  $('preset').replaceChildren(new Option('Custom',''));
  $('preset-list').replaceChildren();$('empty-presets').hidden=state.presets.length>0;
  for(const preset of state.presets){
    $('preset').append(new Option(preset.name,preset.name));
    const card=node('div',undefined,'rule'),top=node('div',undefined,'rule-top'),swatch=node('span',undefined,'swatch');
    swatch.style.background=preset.color;top.append(swatch,node('strong',preset.name));
    const button=node('button','Edit preset');button.setAttribute('aria-label','Edit preset '+preset.name);button.onclick=()=>editPreset(preset);
    card.append(top,node('p',preset.color),button);$('preset-list').append(card);
  }
  $('preset').value=state.presets.some(p=>p.name===selected&&p.color.toLowerCase()===$('color').value.toLowerCase())?selected:'';
}
function render(){
  if(!state)return;
  renderPresets();
  const stale=state.error || Date.now()/1000-state.updated>state.stale_after;
  const prefs=state.settings;
  $('settings-summary').textContent=(prefs.fallback_enabled?'Unidentified: '+prefs.fallback_color+' at '+prefs.fallback_brightness+'% · '+state.plan.fallback_ports.length+' ports':'Unidentified color off')+' · Poll every '+prefs.poll_seconds+'s · '+(prefs.push_seconds?'Reapply every '+prefs.push_seconds+'s':'Reapply on changes or manually');
  $('connection').textContent=stale?'Connection needs attention':state.active?'Colors running':'Live discovery';
  $('notice').classList.toggle('error',!!stale||state.restore_pending&&!state.active);
  $('notice').textContent=state.error || (state.restore_pending&&!state.active?'LED restoration is pending. Reconnect and use Stop & restore.':state.active?'Color rules are running. Ports refresh as devices move.':state.allow_control?'LED controls are available. Run a 10-second test before starting continuous color control.':'Read-only preview. Explore your real devices and save colors; the switch LEDs stay unchanged.');
  if(state.demo){$('connection').textContent='Demo · Sample devices';$('notice').textContent='Demo with fictional devices. No switch is connected. '+$('notice').textContent;}
  $('check').hidden=state.connection!=='direct';
  const device=state.device;
  $('switch-model').textContent=device?.model.replaceAll('-',' ')||'UniFi Etherlighting';
  $('switch-detail').textContent=state.switch_host+' · '+(device?device.copper_ports+' Ethernet + '+device.sfp_ports+' SFP+ ports':state.ports.length+' ports');
  $('compatibility').textContent=device?device.firmware+' · '+device.compatibility:'';
  $('ports').style.gridTemplateRows='repeat('+(device?.rows||2)+',34px)';
  $('ports').style.minWidth=((device?.port_count||state.ports.length)/(device?.rows||2)*34)+'px';
  $('device-count').textContent=new Set(state.rows.map(r=>r.mac)).size;
  $('link-count').textContent=state.ports.filter(p=>p.up).length;
  $('rule-count').textContent=state.rules.rules.length;$('ready-count').textContent=Object.keys(state.plan.desired).length;
  $('seen-at').textContent=state.updated?'Last read '+new Date(state.updated*1000).toLocaleTimeString()+' · Shared ports may include devices behind another switch or Wi-Fi access point.':'Waiting for the switch';
  $('ports').replaceChildren();
  for(const p of [...state.ports].sort((a,b)=>a.port-b.port)){
    const port=p.port, color=state.plan.desired[port];
    const el=node('button',String(port),'port'+(p.up?' link':'')+(color?' planned':'')+(p.uplink?' uplink':'')+(device&&port>device.copper_ports?' sfp':''));
    if(color)el.style.setProperty('--port-color',color.color);
    const names=state.rows.filter(r=>r.port===port).map(r=>r.name||r.mac);
    el.title='Port '+port+(p?.uplink?' · Uplink':'')+' · '+(names.join(', ')||'No devices learned');
    el.setAttribute('aria-label',el.title);el.onclick=()=>{$('search').value='port:'+port;renderDevices();$('search').scrollIntoView({block:'center',behavior:'smooth'});};$('ports').append(el);
  }
  $('rules').replaceChildren();$('empty-rules').hidden=state.rules.rules.length>0;
  for(const rule of state.rules.rules){
    const decision=state.plan.decisions.find(d=>d.mac===rule.mac), card=node('div',undefined,'rule'), top=node('div',undefined,'rule-top');
    const swatch=node('span',undefined,'swatch');swatch.style.background=rule.color;top.append(swatch,node('strong',rule.name||rule.mac));
    card.append(top,node('p',(decision?.port?'Port '+decision.port+' · ':'')+(decision?.reason||'Waiting for discovery')));
    const buttons=node('div',undefined,'actions'), editButton=node('button','Edit');editButton.onclick=()=>edit(rule.mac);buttons.append(editButton);
    if(state.allow_control){const test=node('button','Test 10 seconds');test.disabled=state.active||state.restore_pending||decision?.status!=='ready';test.onclick=async()=>{toast('Testing this port for 10 seconds…');if(await action('test',{mac:rule.mac}))toast('Test finished; stock lighting restoration requested. Check the physical port.');};buttons.append(test);}
    card.append(buttons);$('rules').append(card);
  }
  $('start').disabled=!state.allow_control||state.active||!!stale||!Object.keys(state.plan.desired).length;
  $('stop').disabled=!state.allow_control||!state.active&&!state.restore_pending;
  $('control-note').textContent=state.allow_control?'Colors follow eligible MAC addresses. Use the 10-second test to check a color. Stop restores the current UniFi lighting mode.':'This preview can save rules. Enable LED control in the app configuration when ready to test a physical port.';
  renderDevices();
}
function renderDevices(){
  const query=$('search').value.toLowerCase().trim(), portFilter=query.match(/^port:(\d+)$/), portCounts=new Map(), seen=new Set();
  for(const r of state.rows){if(r.age<=300&&!r.wireless.startsWith('leave/')){if(!portCounts.has(r.port))portCounts.set(r.port,new Set());portCounts.get(r.port).add(r.mac);}}
  $('devices').replaceChildren();let count=0;
  for(const row of [...state.rows].sort((a,b)=>a.port-b.port||a.mac.localeCompare(b.mac))){
    const key=row.mac+':'+row.port;if(seen.has(key))continue;seen.add(key);
    if(portFilter ? row.port!==Number(portFilter[1]) : query&&![row.name,row.mac,row.ip,String(row.port)].join(' ').toLowerCase().includes(query))continue;
    count++;const tr=node('tr'), name=node('td');name.append(node('strong',row.name||'Unnamed device'),node('small',row.mac+(row.ip?' · '+row.ip:'')));
    const port=state.ports.find(p=>p.port===row.port), status=port?.uplink?'Uplink':!port?.up?'Disconnected':row.age>300||row.wireless.startsWith('leave/')?'Last seen earlier':(portCounts.get(row.port)?.size||0)>1?'Shared port':'One MAC learned';
    const info=node('td');info.append(node('span',status,'tag'+(status==='Shared port'?' warn':'')));
    const chosen=state.rules.rules.find(r=>r.mac===row.mac), actionCell=node('td'), button=node('button',chosen?'Edit color':'Choose color');button.onclick=()=>edit(row.mac,row);actionCell.append(button);
    tr.append(name,node('td',String(row.port)),info,actionCell);$('devices').append(tr);
  }$('no-results').hidden=count>0;
}
$('search').addEventListener('input',()=>state&&renderDevices());
$('add').onclick=()=>edit();$('close').onclick=()=>$('editor').close();
$('brightness').oninput=()=>$('level').value=$('brightness').value+'%';
$('preset').onchange=()=>{const preset=state.presets.find(p=>p.name===$('preset').value);if(preset)$('color').value=preset.color;};
$('color').oninput=()=>{$('preset').value='';};
$('add-preset').onclick=()=>editPreset();$('close-preset').onclick=()=>$('preset-editor').close();
$('preset-form').onsubmit=async e=>{e.preventDefault();if(await action('presets',{operation:editingPreset===null?'add':'edit',original_name:editingPreset,name:$('preset-name').value,color:$('preset-color').value})){$('preset-editor').close();toast('Preset saved. Choose it when editing a device color.');}};
$('delete-preset').onclick=async()=>{if(editingPreset!==null&&await action('presets',{operation:'delete',original_name:editingPreset})){$('preset-editor').close();toast('Preset deleted. Saved device colors are unchanged.');}};
$('refresh').onclick=async()=>{toast('Refreshing switch…');if(await action('refresh'))toast(state.active?'Devices refreshed and colors reapplied.':'Devices refreshed. Color control is stopped.');};
$('edit-settings').onclick=()=>{const s=state.settings;$('fallback-enabled').checked=s.fallback_enabled;$('fallback-color').value=s.fallback_color;$('fallback-brightness').value=s.fallback_brightness;$('poll-seconds').value=s.poll_seconds;$('push-seconds').value=s.push_seconds;$('settings-editor').showModal();};
$('close-settings').onclick=()=>$('settings-editor').close();
$('settings-form').onsubmit=async e=>{e.preventDefault();const push=Number($('push-seconds').value);if(push>0&&push<15){toast('Color refresh must be 0 or at least 15 seconds.');return;}if(await action('settings',{fallback_enabled:$('fallback-enabled').checked,fallback_color:$('fallback-color').value,fallback_brightness:Number($('fallback-brightness').value),poll_seconds:Number($('poll-seconds').value),push_seconds:push})){$('settings-editor').close();toast(state.active?'Lighting settings saved and applied.':'Lighting settings saved.');}};
$('check').onclick=async()=>{if(await action('check'))toast('LED interface and shell checks passed. No light changes were made.');};
$('start').onclick=()=>action('start');$('stop').onclick=()=>action('stop');
$('rule-form').onsubmit=async e=>{e.preventDefault();const rule={mac:$('mac').value,name:$('name').value,color:$('color').value,brightness:Number($('brightness').value),enabled:$('enabled').checked,allow_shared:$('shared').checked,group:$('preset').value};
  const rules=state.rules.rules.filter(r=>r.mac!==editing?.mac&&r.mac!==rule.mac.toLowerCase());rules.push(rule);
  if(await action('rules',{version:1,rules})){$('editor').close();toast(state.active?'Rule saved and applied.':'Color saved to the preview.');}
};
$('remove').onclick=async()=>{if(editing&&await action('rules',{version:1,rules:state.rules.rules.filter(r=>r.mac!==editing.mac)})){$('editor').close();toast('Rule removed.');}};
$('export').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(state.rules,null,2)],{type:'application/json'}));const link=node('a');link.href=url;link.download='etherlighting-rules.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
$('import').onchange=async e=>{const file=e.target.files[0];if(!file)return;try{if(file.size>512000)throw new Error('Rules file is too large.');const imported=JSON.parse(await file.text());if(!Array.isArray(imported.rules)||imported.version!==1)throw new Error('Unrecognized rules file.');const merged=new Map(state.rules.rules.map(r=>[r.mac,r]));for(const rule of imported.rules)merged.set(rule.mac,rule);if(await action('rules',{version:1,rules:[...merged.values()]}))toast('Rules imported.');}catch(error){toast(error.message);}e.target.value='';};
async function poll(){if(!busy){try{state=await request('state');render();}catch(e){$('connection').textContent='Disconnected';$('notice').textContent='The app connection was lost. Reload after reconnecting.';}}}
poll();setInterval(poll,5000);

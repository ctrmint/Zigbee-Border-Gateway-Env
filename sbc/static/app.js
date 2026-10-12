'use strict';
let token='',timer=null,online=false,session=0,refreshing=false;
let locations=[],locationSignature='';
const requests=new Set();
const $=id=>document.getElementById(id);
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function btn(text,fn,disabled=false){const n=el('button',text);n.disabled=disabled;n.onclick=fn;return n;}
async function api(path,body,method=body?'POST':'GET'){
  const epoch=session,controller=new AbortController();requests.add(controller);
  try{
    const r=await fetch('/api/v1/'+path,{method,signal:controller.signal,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
    const d=await r.json();
    if(epoch!==session)throw new DOMException('Session changed','AbortError');
    if(!r.ok)throw Error(d.error||'Request failed');
    return d;
  }finally{requests.delete(controller);}
}
function reportError(e){if(e.name!=='AbortError')$('notice').textContent=e.message;}
async function command(c){try{const d=await api('commands',c);$('notice').textContent=d.accepted?'Command accepted. Waiting for device report.':'Command rejected.';await refresh();}catch(e){reportError(e);}}
async function configure(path,body,method,message){try{await api(path,body,method);$('notice').textContent=message;await refresh();return true;}catch(e){reportError(e);return false;}}
function renderLocations(){
  const signature=JSON.stringify(locations);
  if(signature===locationSignature)return;
  // Preserve drafts while telemetry refreshes.
  if(document.activeElement?.closest('#location-list'))return;
  locationSignature=signature;$('location-list').replaceChildren();
  for(const location of locations){
    const row=el('div',undefined,'location-row'),label=el('label',`Location · ${location.device_count} device${location.device_count===1?'':'s'}`);
    const input=el('input');input.value=location.name;input.maxLength=80;input.setAttribute('aria-label',`Rename ${location.name}`);label.append(input);
    row.append(label,btn('Save name',async()=>{if(await configure('locations/'+location.id,{name:input.value},'PUT','Location renamed.')){document.activeElement.blur();renderLocations();}}));
    const remove=btn('Delete',async()=>{if(await configure('locations/'+location.id,null,'DELETE','Location deleted.')){document.activeElement.blur();renderLocations();}},location.device_count>0);
    remove.className='quiet';remove.title=location.device_count?'Move or unassign devices before deleting.':'Delete empty location';row.append(remove);$('location-list').append(row);
  }
  if(!locations.length)$('location-list').append(el('p','Add a location, then assign sensors using the selector on each device.','small'));
}
function deviceCard(d){
  const card=el('article',undefined,'card'),model=Object.values(d.attributes).find(a=>a.cluster===0&&a.attribute===5);
  card.append(el('h3',model?.raw||'Zigbee device'),el('div',d.ieee,'small'),el('p',`Network address: 0x${Number(d.nwk).toString(16).padStart(4,'0')} · ${d.active?'Registered':'Left network'}`,'small'));
  const label=el('label','Location'),select=el('select');select.setAttribute('aria-label',`Location for ${d.ieee}`);
  const unassigned=el('option','Unassigned');unassigned.value='';select.append(unassigned);
  for(const location of locations){const option=el('option',location.name);option.value=location.id;select.append(option);}
  select.value=d.location_id||'';
  select.onchange=async()=>{select.disabled=true;const ok=await configure('devices/'+d.ieee+'/location',{location_id:select.value||null},'PUT','Device location saved.');if(!ok)select.value=d.location_id||'';select.disabled=false;select.blur();await refresh();};
  label.append(select);card.append(label);
  const metrics=el('div',undefined,'metrics');
  for(const a of Object.values(d.attributes)){if(a.unit){const m=el('div',undefined,'metric');m.append(el('strong',a.value===null?'Unknown':a.unit==='on/off'?(a.value?'On':'Off'):a.value.toFixed(2)),el('span',a.unit==='on/off'?'Reported state':a.unit),el('div',new Date(a.received*1000).toLocaleString(),'small'));metrics.append(m);}}
  card.append(metrics);const actions=el('div',undefined,'actions');actions.append(btn('Discover',()=>command({op:'discover',ieee:d.ieee}),!online||!d.active));
  for(const [ep,desc] of Object.entries(d.endpoints)){
    if(desc.input_clusters.includes(6)){for(const state of [true,false])actions.append(btn(`${state?'On':'Off'} · EP ${ep}`,()=>command({op:'on_off',ieee:d.ieee,endpoint:Number(ep),state}),!online||!d.active));}
    for(const cluster of desc.input_clusters.filter(c=>[6,0x0402,0x0405].includes(c)))actions.append(btn(`Read ${cluster.toString(16)} · EP ${ep}`,()=>command({op:'read',ieee:d.ieee,endpoint:Number(ep),cluster,attribute:0}),!online||!d.active));
  }
  card.append(actions);const details=el('details');details.append(el('summary','Endpoints and raw attributes'),el('pre',JSON.stringify({endpoints:d.endpoints,attributes:d.attributes},null,2)));card.append(details);return card;
}
function render(devices){
  if(document.activeElement?.closest('#devices select'))return;
  $('devices').replaceChildren();
  for(const location of [...locations,{id:null,name:'Unassigned'}]){
    const members=devices.filter(d=>(d.location_id||null)===location.id);if(!members.length)continue;
    const section=el('section');section.append(el('h2',`${location.name} · ${members.length}`));const cards=el('div',undefined,'cards');for(const d of members)cards.append(deviceCard(d));section.append(cards);$('devices').append(section);
  }
  if(!devices.length)$('devices').append(el('p','No devices yet. Open pairing and put a device into pairing mode.'));
}
async function refresh(){
  if(!token||refreshing)return;const epoch=session;refreshing=true;
  try{
    const [d,e]=await Promise.all([api('state'),api('events')]);if(epoch!==session)return;
    online=d.gateway.connected&&d.gateway.ready;locations=d.locations;
    $('status').textContent=`${d.gateway.mode==='simulator'?'SIMULATOR · ':''}${online?'Gateway connected':'Gateway offline / starting'}`;$('pairing').textContent=`Pairing: ${d.gateway.join_seconds||0}s remaining`;
    $('join').disabled=!online;$('close').disabled=!online;$('locations-panel').hidden=false;renderLocations();render(d.devices);
    if(d.gateway.gap)$('notice').textContent='History gap detected. Some gateway events were missed; rediscover devices if needed.';
    $('events').textContent=e.events.slice(0,20).map(x=>`${new Date(x.received*1000).toLocaleString()} · ${x.type} · ${x.ieee||''} · ${JSON.stringify(x)}`).join('\n');
  }catch(e){if(epoch!==session||e.name==='AbortError')return;online=false;$('status').textContent=e.message;$('join').disabled=true;$('close').disabled=true;for(const button of $('devices').querySelectorAll('.actions button'))button.disabled=true;}
  finally{if(epoch===session)refreshing=false;}
}
function endSession(){
  session++;for(const controller of requests)controller.abort();clearInterval(timer);refreshing=false;token='';online=false;locations=[];locationSignature='';
  $('devices').replaceChildren();$('location-list').replaceChildren();$('locations-panel').hidden=true;$('location-name').value='';$('notice').textContent='';$('events').textContent='Disconnected.';$('status').textContent='Disconnected';$('pairing').textContent='';$('join').disabled=true;$('close').disabled=true;
}
$('connect').onclick=()=>{const nextToken=$('token').value.trim();endSession();token=nextToken;refresh();timer=setInterval(refresh,3000);};
$('logout').onclick=()=>{endSession();$('token').value='';};
$('location-form').onsubmit=async event=>{event.preventDefault();const input=$('location-name'),submit=$('add-location');submit.disabled=true;const epoch=session;if(await configure('locations',{name:input.value},'POST','Location created.')&&epoch===session)input.value='';submit.disabled=false;};
$('join').onclick=()=>command({op:'permit_join',seconds:60});$('close').onclick=()=>command({op:'permit_join',seconds:0});$('join').disabled=true;$('close').disabled=true;

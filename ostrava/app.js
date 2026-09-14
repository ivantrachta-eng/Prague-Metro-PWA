let mode='tram';
let DATA={modes:{tram:{lines:{}},trolleybus:{lines:{}},bus:{lines:{}}}};
const els=Object.fromEntries(['lineSelect','directionSelect','stationSelect','announcementText','routeList','lineBadge','stationCount','status','autoNext'].map(id=>[id,document.getElementById(id)]));
const playBtn=document.getElementById('playBtn');

function lineSort(a,b){const na=Number(a),nb=Number(b);if(Number.isFinite(na)&&Number.isFinite(nb))return na-nb;return a.localeCompare(b,'cs',{numeric:true})}
function modeData(){return DATA.modes?.[mode]?.lines||{}}
function lineData(){return modeData()[els.lineSelect.value]||null}
function patterns(){return lineData()?.patterns||lineData()?.directions||[]}
function pattern(){return patterns()[Number(els.directionSelect.value)||0]||null}
function stops(){return pattern()?.stops||[]}
function modeLabel(){return mode==='tram'?'tramvaj':mode==='trolleybus'?'trolejbus':'autobus'}
function accent(){return mode==='tram'?'#0ea5e9':mode==='trolleybus'?'#7c3aed':'#f97316'}

function setupLines(){
  els.lineSelect.innerHTML='';
  const keys=Object.keys(modeData()).sort(lineSort);
  for(const k of keys){const o=document.createElement('option');o.value=k;o.textContent=k;els.lineSelect.appendChild(o)}
  if(!keys.length){const o=document.createElement('option');o.textContent='Data se načítají…';els.lineSelect.appendChild(o)}
}
function setupDirections(){
  els.directionSelect.innerHTML='';
  const d=lineData(); if(!d)return;
  patterns().forEach((p,i)=>{const o=document.createElement('option');o.value=i;const extra=d.hasVariants?` · varianta ${i+1}`:'';o.textContent=`${p.from} → ${p.to}${extra}`;els.directionSelect.appendChild(o)})
}
function setupStations(){
  els.stationSelect.innerHTML='';
  stops().forEach((s,i)=>{const o=document.createElement('option');o.value=i;o.textContent=s;els.stationSelect.appendChild(o)})
}
function announcementFor(i){
  const arr=stops(),cur=arr[i],next=arr[i+1];
  if(!cur)return'';
  if(next)return `${cur}. Příští zastávka: ${next}.`;
  return `${cur}. Konečná zastávka. Prosíme, vystupte.`;
}
function render(){
  const d=lineData(),p=pattern(),arr=stops(),i=Number(els.stationSelect.value)||0,cur=arr[i];
  document.documentElement.style.setProperty('--accent',accent());
  els.lineBadge.textContent=els.lineSelect.value||'–';
  if(!d||!p||!cur){els.announcementText.textContent='Data linek zatím nejsou načtena.';els.routeList.innerHTML='';els.stationCount.textContent='';return}
  els.stationCount.textContent=`${arr.length} zastávek`;
  els.announcementText.textContent=announcementFor(i);
  els.routeList.innerHTML='';
  arr.forEach((name,idx)=>{
    const b=document.createElement('button');b.className='route-item'+(idx===i?' active':'');b.type='button';
    const dot=document.createElement('span');dot.className='route-dot';
    const n=document.createElement('span');n.className='route-name';n.textContent=name;
    b.append(dot,n);
    if(d.hasVariants&&idx===0){const tag=document.createElement('span');tag.className='variant-note';tag.textContent='varianta';b.appendChild(tag)}
    b.addEventListener('click',()=>{els.stationSelect.value=idx;render()});
    els.routeList.appendChild(b);
  });
}
function refresh(){setupLines();setupDirections();setupStations();render()}
function sleep(ms){return new Promise(r=>setTimeout(r,ms))}
function unlockSpeech(){if(!('speechSynthesis'in window))return;try{speechSynthesis.cancel();speechSynthesis.resume();const u=new SpeechSynthesisUtterance(' ');u.lang='cs-CZ';u.volume=0;speechSynthesis.speak(u)}catch{}}
function speak(text,lang='cs-CZ'){return new Promise(resolve=>{if(!('speechSynthesis'in window)){resolve();return}speechSynthesis.resume();const u=new SpeechSynthesisUtterance(text);u.lang=lang;u.rate=.9;u.pitch=1;u.onend=resolve;u.onerror=resolve;speechSynthesis.speak(u)})}
async function playCurrent(){
  const arr=stops(),i=Number(els.stationSelect.value)||0,cur=arr[i],next=arr[i+1];if(!cur)return;
  els.status.textContent='Přehrávám…';
  await speak(`${cur}.`);
  await sleep(500);
  if(next){await speak(`Příští zastávka: ${next}.`)}else{await speak('Konečná zastávka. Prosíme, vystupte.')}
  if(els.autoNext.checked&&next){els.stationSelect.value=i+1;render()}
  els.status.textContent='Připraveno.';
}
async function loadData(){
  try{const r=await fetch('ostrava-transit-data.json',{cache:'no-store'});if(!r.ok)throw new Error(`HTTP ${r.status}`);DATA=await r.json();refresh()}catch(e){els.announcementText.textContent='Nepodařilo se načíst data DPO.';console.error(e)}
}

document.querySelectorAll('.mode-btn').forEach(b=>b.addEventListener('click',()=>{mode=b.dataset.mode;document.querySelectorAll('.mode-btn').forEach(x=>x.classList.toggle('active',x===b));refresh()}));
els.autoNext.checked=localStorage.getItem('ostravaAutoNext')==='1';
els.autoNext.addEventListener('change',()=>localStorage.setItem('ostravaAutoNext',els.autoNext.checked?'1':'0'));
els.lineSelect.addEventListener('change',()=>{setupDirections();setupStations();render()});
els.directionSelect.addEventListener('change',()=>{setupStations();render()});
els.stationSelect.addEventListener('change',render);
document.getElementById('prevBtn').addEventListener('click',()=>{els.stationSelect.value=Math.max(0,Number(els.stationSelect.value)-1);render()});
document.getElementById('nextBtn').addEventListener('click',()=>{els.stationSelect.value=Math.min(stops().length-1,Number(els.stationSelect.value)+1);render()});
playBtn.addEventListener('click',()=>{unlockSpeech();void playCurrent()});
if('serviceWorker'in navigator)window.addEventListener('load',()=>navigator.serviceWorker.register('service-worker.js').catch(()=>{}));
refresh();loadData();

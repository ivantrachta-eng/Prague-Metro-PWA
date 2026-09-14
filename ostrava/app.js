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

// DPO timetable PDFs use many compact abbreviations intended for printed tables.
// Keep the official compact stop label in the UI, but expand it for TTS and
// the announcement preview so Czech speech synthesis reads natural names.
const SPOKEN_STOP_EXACT={
  'Náměstí S.Čecha':'Náměstí Svatopluka Čecha',
  'Sad B.Němcové':'Sad Boženy Němcové',
  'Náměstí B.Němcové':'Náměstí Boženy Němcové',
  'Horn.poliklinika':'Hornická poliklinika',
  'Most M.Sýkory':'Most Miloše Sýkory',
  'Nám.J.Gagarina':'Náměstí Jurije Gagarina',
  'Nám.J.z Poděbrad':'Náměstí Jiřího z Poděbrad',
  'Náměstí Gen.Svobody':'Náměstí Generála Svobody',
  'Ředitel.Vítkovic':'Ředitelství Vítkovic',
  'Telekom.škola':'Telekomunikační škola',
  'ÚMOb Jih':'Úřad městského obvodu Jih',
  'VŠB-TUO':'Vysoká škola báňská, Technická univerzita Ostrava',
  'VŠ podnikání':'Vysoká škola podnikání',
  'Most Čs. armády':'Most Československé armády',
  'Dílny DP Ostrava':'Dílny Dopravního podniku Ostrava',
  'Revírní br. pokladna':'Revírní bratrská pokladna',
  'Stan.záchr.služby':'Stanice záchranné služby',
  'Stodolní žel.zastávka':'Stodolní železniční zastávka',
  'Čistička odp.vod':'Čistička odpadních vod',
  'Pomník RA':'Pomník Rudé armády',
  'Nábřeží SPB':'Nábřeží Svazu protifašistických bojovníků',
  '29.dubna':'Dvacátého devátého dubna',
  'U Hradu x':'U Hradu'
};

function spokenStopName(name){
  if(!name)return'';
  if(SPOKEN_STOP_EXACT[name])return SPOKEN_STOP_EXACT[name];
  let s=name;
  const replacements=[
    [/\bSl\.Ostrava\b/g,'Slezská Ostrava'],
    [/\bMor\.Ostrava\b/g,'Moravská Ostrava'],
    [/\bLudg\./g,'Ludgeřovice'],
    [/\bKpt\./g,'Kapitána '],
    [/\bGen\./g,'Generála '],
    [/\bČs\.\s*/g,'Československé '],
    [/\bNová huť hl\.brána\b/g,'Nová huť hlavní brána'],
    [/\bNová huť již\.brána\b/g,'Nová huť jižní brána'],
    [/\bHor\.Datyně\b/g,'Horní Datyně'],
    [/\bSpol\.dům\b/g,'Společenský dům'],
    [/\bChem\.závody\b/g,'Chemické závody'],
    [/\baut\.nádr\./g,'autobusové nádraží'],
    [/\bžel\.zast\.\b/g,'železniční zastávka'],
    [/\bžel\.zastávka\b/g,'železniční zastávka'],
    [/\bsídl\.\b/g,'sídliště '],
    [/\bkult\.dům\b/g,'kulturní dům'],
    [/\bkřiž\.\b/g,'křižovatka'],
    [/\brozc\.\b/g,'rozcestí'],
    [/\brest\.\b/g,'restaurace '],
    [/\bnám\.\b/g,'náměstí'],
    [/,OC\b/g,', obchodní centrum'],
    [/,PZ\b/g,', průmyslová zóna'],
    [/\bPZ\s+(sever|střed|jih|Dubí|Rudná)\b/g,'průmyslová zóna $1'],
    [/,ZD\b/g,', zemědělské družstvo'],
    [/,SOU\b/g,', střední odborné učiliště'],
    [/\bNáměstí SNP\b/g,'Náměstí Slovenského národního povstání'],
    [/\bDP Ostrava\b/g,'Dopravního podniku Ostrava']
  ];
  for(const [rx,to] of replacements)s=s.replace(rx,to);
  // Improve pauses for locality-qualified stop names without changing display labels.
  s=s.replace(/,/g,', ')
     .replace(/\s{2,}/g,' ')
     .replace(/\s+([.,])/g,'$1')
     .trim();
  return s;
}

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
  const curSpoken=spokenStopName(cur),nextSpoken=spokenStopName(next);
  if(next)return `${curSpoken}. Příští zastávka: ${nextSpoken}.`;
  return `${curSpoken}. Konečná zastávka. Prosíme, vystupte.`;
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
  await speak(`${spokenStopName(cur)}.`);
  await sleep(500);
  if(next){await speak(`Příští zastávka: ${spokenStopName(next)}.`)}else{await speak('Konečná zastávka. Prosíme, vystupte.')}
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

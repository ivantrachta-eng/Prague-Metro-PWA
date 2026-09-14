const CACHE='mhd-launcher-v11';
const ASSETS=[
  './',
  'index.html',
  'manifest.webmanifest',
  'praha/index.html',
  'styles.css',
  'app.js',
  'transit-data.json',
  'icons/icon-192.png',
  'icons/icon-512.png',
  'audio/gonga.wav',
  'audio/gongb.wav',
  'audio/gongc.wav'
];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{
  if(e.request.method!=='GET')return;
  const url=new URL(e.request.url);
  if(url.pathname.includes('/ostrava/'))return;
  e.respondWith(
    caches.match(e.request).then(cached=>cached||fetch(e.request).then(res=>{
      if(res&&res.ok){const copy=res.clone();caches.open(CACHE).then(c=>c.put(e.request,copy));}
      return res;
    }).catch(()=>{
      if(e.request.mode==='navigate')return caches.match('index.html');
      return Response.error();
    }))
  );
});

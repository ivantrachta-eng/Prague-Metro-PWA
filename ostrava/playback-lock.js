(()=>{
  const originalPlayCurrent=window.playCurrent;
  if(typeof originalPlayCurrent!=='function')return;

  let locked=false;
  const shell=document.querySelector('.app-shell');
  const blockedEvents=['click','pointerdown','pointerup','touchstart','touchend','keydown','keyup','change','input','submit'];

  function blockWhilePlaying(event){
    if(!locked)return;
    event.preventDefault();
    event.stopImmediatePropagation();
  }

  blockedEvents.forEach(type=>document.addEventListener(type,blockWhilePlaying,true));

  window.playCurrent=async function(...args){
    if(locked)return;
    locked=true;
    shell?.setAttribute('aria-busy','true');
    try{
      return await originalPlayCurrent.apply(this,args);
    }finally{
      locked=false;
      shell?.removeAttribute('aria-busy');
    }
  };
})();

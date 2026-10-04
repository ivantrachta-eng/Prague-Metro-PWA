/* Výslovnostní vrstva pro český systémový hlas.
   Nemění zobrazované názvy zastávek, pouze text poslaný do SpeechSynthesis. */
(() => {
  const exact = new Map([
    ['Strossmayerovo náměstí', 'Štrosmajerovo náměstí'],
    ['Koh-i-noor', 'Kohinor'],
    ['I. P. Pavlova', 'Í pé Pavlova'],
    ['Náměstí Olgy Scheinpflugové', 'Náměstí Olgy Šajnpflugové'],
    ['Slavia - Nádraží Eden', 'Slavia, Nádraží Eden'],
    ['Vozovna Střešovice (Muzeum MHD)', 'Vozovna Střešovice, Muzeum em há dé']
  ]);

  const replacements = [
    [/\bStrossmayerovo náměstí\b/g, 'Štrosmajerovo náměstí'],
    [/\bKoh-i-noor\b/gi, 'Kohinor'],
    [/\bI\.\s*P\.\s*Pavlova\b/g, 'Í pé Pavlova'],
    [/\bOlgy Scheinpflugové\b/g, 'Olgy Šajnpflugové'],
    [/\bMHD\b/g, 'em há dé'],
    [/\bOC\b/g, 'ó cé'],
    [/\bVŠE\b/g, 'vé šé é'],
    [/\bČVUT\b/g, 'čé vé ú té'],
    [/\bIKEM\b/g, 'ikem']
  ];

  /*
   * iOS český TTS dělá mezi samostatnou jednopísmennou předložkou a názvem
   * příliš velkou prosodickou hranici. Neviditelné Unicode spojovače ji na
   * některých hlasech neodstraní. Proto pro SYNTÉZU použijeme fonetický celek:
   *   U Libušského -> Ulibušského
   *   K Barrandovu -> Kbarrandovu
   *   V Olšinách   -> Volšinách
   * Zobrazený název se nemění. TTS tak nemá místo, na kterém by mohl vložit
   * pauzu; česká výslovnost souhlásek zůstává přirozeně spojitá.
   */
  const linkedPrepositions = /(^|[\s,(;:])([KkSsVvZzUuOo])\s+(?=[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ])/g;

  function linkCzechPrepositions(text) {
    return String(text).replace(linkedPrepositions, (_, before, prep) => before + prep);
  }

  function applyPronunciation(text) {
    let out = String(text);
    for (const [name, pronunciation] of exact) out = out.split(name).join(pronunciation);
    for (const [pattern, replacement] of replacements) out = out.replace(pattern, replacement);
    out = linkCzechPrepositions(out);
    return out;
  }

  function spokenStopName(name) {
    if (!name) return name;
    return applyPronunciation(name);
  }

  function spokenText(text) {
    if (!text) return text;
    return applyPronunciation(text);
  }

  window.spokenStopName = spokenStopName;
  window.spokenText = spokenText;

  const NativeUtterance = window.SpeechSynthesisUtterance;
  if (NativeUtterance) {
    window.SpeechSynthesisUtterance = new Proxy(NativeUtterance, {
      construct(Target, args) {
        if (args.length && typeof args[0] === 'string') args[0] = spokenText(args[0]);
        return Reflect.construct(Target, args);
      }
    });
  }
})();

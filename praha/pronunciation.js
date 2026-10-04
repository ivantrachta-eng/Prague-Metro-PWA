/* Výslovnostní vrstva pro český systémový hlas.
   Nemění zobrazované názvy zastávek, pouze text poslaný do SpeechSynthesis. */
(() => {
  const exact = new Map([
    ['Strossmayerovo náměstí', 'Štrosmajerovo náměstí'],
    ['Koh-i-noor', 'Kohinor'],
    ['I. P. Pavlova', 'Ip Pavlova'],
    ['I.P.Pavlova', 'Ip Pavlova'],
    ['IP Pavlova', 'Ip Pavlova'],
    ['Náměstí Olgy Scheinpflugové', 'Náměstí Olgy Šajnpflugové'],
    ['Slavia - Nádraží Eden', 'Slávia, Nádraží Eden'],
    ['Slavia', 'Slávia'],
    ['Slávia', 'Slávia'],
    ['Vozovna Střešovice (Muzeum MHD)', 'Vozovna Střešovice, Muzeum em há dé'],
    ['U Libušského potoka', 'Ulibušského potoka']
  ]);

  const replacements = [
    [/\bStrossmayerovo náměstí\b/g, 'Štrosmajerovo náměstí'],
    [/\bKoh-i-noor\b/gi, 'Kohinor'],
    [/\bI\.?\s*P\.?\s*Pavlova\b/gi, 'Ip Pavlova'],
    [/\bOlgy Scheinpflugové\b/g, 'Olgy Šajnpflugové'],
    [/\bSlavia\b/g, 'Slávia'],
    [/\bMHD\b/g, 'em há dé'],
    [/\bOC\b/g, 'ó cé'],
    [/\bVŠE\b/g, 'vé šé é'],
    [/\bČVUT\b/g, 'čé vé ú té'],
    [/\bIKEM\b/g, 'ikem']
  ];

  /*
   * Česká jednoslabičná i víceslabičná předložka tvoří s následujícím slovem
   * přízvukový celek. iOS TTS však někdy v názvech zastávek vloží po předložce
   * nepřirozenou pauzu. Proto ji pouze ve fonetickém textu připojíme k dalšímu
   * slovu. Důležité: předchozí verze vyžadovala velké písmeno po předložce;
   * proto fungovalo „U Průhonu“, ale ne „U Kaštanu“ v některých kontextech po
   * transformaci. Nová verze pracuje s českým písmenem bez ohledu na velikost.
   */
  const PREPOSITIONS = ['Před', 'Přes', 'Pod', 'Nad', 'Pro', 'Bez', 'Mezi', 'Za', 'Na', 'Do', 'Od', 'Po', 'U', 'K', 'S', 'V', 'Z', 'O'];
  const prepPattern = new RegExp('(^|[\\s,(;:])(' + PREPOSITIONS.join('|') + ')\\s+(?=[A-Za-zÁ-Žá-ž])', 'giu');

  function linkPrepositions(text) {
    return String(text).replace(prepPattern, (_, before, prep) => before + prep);
  }

  function applyPronunciation(text) {
    let out = String(text);
    const names = [...exact.entries()].sort((a, b) => b[0].length - a[0].length);
    for (const [name, pronunciation] of names) out = out.split(name).join(pronunciation);
    for (const [pattern, replacement] of replacements) out = out.replace(pattern, replacement);
    // Provést až po všech konkrétních fonetických náhradách.
    out = linkPrepositions(out);
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

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
    // Oficiální zápis zůstává Slavia, pro hlas ale potřebujeme dlouhé á.
    ['Slavia', 'Slávia'],
    ['Slávia', 'Slávia'],
    ['Slavia - Nádraží Eden', 'Slávia, Nádraží Eden'],
    ['Vozovna Střešovice (Muzeum MHD)', 'Vozovna Střešovice, Muzeum em há dé'],
    // Pro TTS je předložka připojena přímo k následujícímu slovu, ale zachováváme
    // celý správný pád názvu: foneticky má zaznít „U Libušského potoka“.
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

  function applyPronunciation(text) {
    let out = String(text);
    const names = [...exact.entries()].sort((a, b) => b[0].length - a[0].length);
    for (const [name, pronunciation] of names) out = out.split(name).join(pronunciation);
    for (const [pattern, replacement] of replacements) out = out.replace(pattern, replacement);
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

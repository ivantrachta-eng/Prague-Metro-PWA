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
   * Jednoslabičné české předložky jsou v běžné řeči přízvukovým celkem
   * s následujícím slovem. Některé iOS hlasy však při obyčejné mezeře
   * vytvoří slyšitelnou pauzu (např. „U | Libušského potoka“).
   * Word Joiner U+2060 zachová dvě slova pro TTS, ale zakáže zlom/pauzu
   * v tomto místě. Nezasahujeme do textu zobrazeného uživateli.
   */
  const WORD_JOINER = '\u2060';
  const linkedPrepositions = /(^|[\s,(;:])([KkSsVvZzUuOo])\s+(?=[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ])/g;

  function linkCzechPrepositions(text) {
    return String(text).replace(linkedPrepositions, (_, before, prep) => before + prep + WORD_JOINER);
  }

  function applyPronunciation(text) {
    let out = String(text);
    for (const [name, pronunciation] of exact) out = out.split(name).join(pronunciation);
    for (const [pattern, replacement] of replacements) out = out.replace(pattern, replacement);
    // Až nakonec: propojí předložku s prvním slovem názvu po všech náhradách.
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

  // app.js používá SpeechSynthesisUtterance přímo. Proxy zajistí, že se korekce
  // aplikuje centrálně na všechna česká hlášení, včetně metra a příští zastávky.
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

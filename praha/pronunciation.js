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
    ['Slavia', 'Slávia'],
    ['Slávia', 'Slávia'],
    ['Slavia - Nádraží Eden', 'Slávia, Nádraží Eden'],
    ['Vozovna Střešovice (Muzeum MHD)', 'Vozovna Střešovice, Muzeum em há dé'],
    ['U Libušského potoka', 'Ulibušského potoka'],
    ['U Průhonu', 'Uprůhonu'],
    ['U Pruhů', 'Upruhů']
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
   * Česká předložka se při přirozené výslovnosti váže k následujícímu slovu.
   * iOS TTS ale u názvů zastávek často vytvoří slyšitelnou pauzu. Proto pouze
   * v textu pro syntézu odstraníme mezeru mezi předložkou a prvním slovem.
   * Funguje i uvnitř názvu: Divadlo Na Fidlovačce -> Divadlo Nafidlovačce.
   * Zobrazené názvy zůstávají beze změny.
   */
  const prepositionPattern = /(^|[\s,(;:])((?:[UuKkSsVvZzOo]|[Nn]a|[Dd]o|[Oo]d|[Pp]o|[Zz]a|[Pp]od|[Nn]ad|[Pp]řed|[Pp]řes|[Pp]ro))\s+(?=[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ])/g;

  function joinPrepositions(text) {
    let previous;
    let out = String(text);
    // Opakování pokryje i případ, kdy by po jedné náhradě vznikl další shodný celek.
    do {
      previous = out;
      out = out.replace(prepositionPattern, (_, before, prep) => before + prep);
    } while (out !== previous);
    return out;
  }

  function applyPronunciation(text) {
    let out = String(text);
    const names = [...exact.entries()].sort((a, b) => b[0].length - a[0].length);
    for (const [name, pronunciation] of names) out = out.split(name).join(pronunciation);
    for (const [pattern, replacement] of replacements) out = out.replace(pattern, replacement);
    out = joinPrepositions(out);
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

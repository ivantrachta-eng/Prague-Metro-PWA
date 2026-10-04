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
    ['Slavia', 'Slavia'],
    ['Slávia', 'Slavia'],
    ['Slavia - Nádraží Eden', 'Slavia, Nádraží Eden'],
    ['Vozovna Střešovice (Muzeum MHD)', 'Vozovna Střešovice, Muzeum em há dé'],
    // U této zastávky používáme čistě fonetický tvar bez samostatné předložky.
    // „Ulibušského“ iOS stále může segmentovat; „Ulibušský potok“ drží celek
    // a přitom zní prakticky stejně jako požadované „U Libušského potoka“.
    ['U Libušského potoka', 'Ulibušský potok']
  ]);

  const replacements = [
    [/\bStrossmayerovo náměstí\b/g, 'Štrosmajerovo náměstí'],
    [/\bKoh-i-noor\b/gi, 'Kohinor'],
    [/\bI\.?\s*P\.?\s*Pavlova\b/gi, 'Ip Pavlova'],
    [/\bOlgy Scheinpflugové\b/g, 'Olgy Šajnpflugové'],
    [/\bSlávia\b/g, 'Slavia'],
    [/\bMHD\b/g, 'em há dé'],
    [/\bOC\b/g, 'ó cé'],
    [/\bVŠE\b/g, 'vé šé é'],
    [/\bČVUT\b/g, 'čé vé ú té'],
    [/\bIKEM\b/g, 'ikem']
  ];

  /*
   * iOS SpeechSynthesis si umí znovu rozdělit i text, ze kterého jsme odstranili
   * mezeru (např. Ulibušského). Proto už neděláme obecné slepování všech
   * předložek. Problematické názvy dostávají explicitní fonetickou podobu v
   * mapě výše. Je to stabilnější a nepoškozuje jiné názvy.
   */

  function applyPronunciation(text) {
    let out = String(text);
    // Nejdříve celé názvy; tím se explicitní fonetické varianty použijí i ve
    // větách typu „Příští zastávka U Libušského potoka“.
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

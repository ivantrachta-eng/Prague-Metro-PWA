# Pražské metro – PWA

## Co obsahuje
- linky A, B, C
- oba směry
- seznamy stanic a přestupy
- systémový český TTS jako fallback
- podpora vlastních WAV segmentů
- manifest + service worker pro instalaci na plochu a offline režim

## Spuštění
PWA potřebuje být servírovaná přes HTTPS nebo localhost. Nestačí otevřít `index.html` přímo jako soubor.

### Rychlý lokální test
V této složce spusť například:

    python3 -m http.server 8080

A otevři `http://localhost:8080`.

## iPhone
Nahraj obsah složky na libovolný HTTPS hosting. Na iPhonu otevři adresu v Safari, klepni na Sdílet a pak na Přidat na plochu.

## Vlastní audio
Do složky `audio/` lze přidat:
- `gong_station.wav`
- plná hlášení ve tvaru např. `a_mustek.wav`, `b_florenc.wav`, `c_muzeum.wav`

Pokud WAV chybí, aplikace použije systémový český hlas zařízení.

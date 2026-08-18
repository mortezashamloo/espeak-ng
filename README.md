# eSpeak NG Text-to-Speech (Persian + American English patch)

This is a fork of [espeak-ng/espeak-ng](https://github.com/espeak-ng/espeak-ng) with a targeted improvement for **Persian (fa)** users:

> When the current voice is Persian and an English word appears in the text, it is pronounced with a **General American (en-us)** accent instead of the default British English.

This is especially useful for screen readers such as **NVDA** on Windows (including Windows 7 + NVDA 2023.3).

## What the patch does

In `src/libespeak-ng/translate.c`:

- When language is Persian (`fa`) and an English word is detected, the secondary translator is set to `en` (so correct English dictionary, langopts and acronym handling are used).
- The phoneme table is then switched to `en-us`.
- General American dictionary rules (dictrules 3 and 6) are enabled.

`SetTranslator3` is intentionally left unchanged so emoji / capital-letter fallback behaviour of NVDA stays correct (silence when emoji reading is off).

## 32-bit DLL for NVDA on Windows 7

A pre-built **32-bit** `espeak.dll` (compatible with NVDA 2023.3 on Windows 7) has been tested and works better than the stock NVDA version for mixed Persian + English text.

### Installation

1. Get the 32-bit DLL (from Releases when published, or the file built and tested in this project).
2. Go to:
   ```
   C:\Program Files (x86)\NVDA\synthDrivers
   ```
3. Backup the existing `espeak.dll` (rename to `espeak.dll.bak`).
4. Copy the new file and name it exactly `espeak.dll`.
5. Restart NVDA completely.
6. Set the voice to **Persian (Farsi)** and test mixed Persian + English text.

No need to rename `en_dict` to `en-us_dict`.

## Building yourself

```bash
git clone https://github.com/mortezashamloo/espeak-ng.git
cd espeak-ng
# The patched translate.c is already in the tree
mkdir build && cd build
cmake .. -DBUILD_SHARED_LIBS=ON
cmake --build . --target espeak-ng
```

For a 32-bit Windows DLL (MinGW):

```bash
cmake .. -DCMAKE_SYSTEM_NAME=Windows \
  -DCMAKE_C_COMPILER=i686-w64-mingw32-gcc \
  -DCMAKE_CXX_COMPILER=i686-w64-mingw32-g++ \
  -DBUILD_SHARED_LIBS=ON -DCMAKE_BUILD_TYPE=MinSizeRel \
  -DUSE_SPEECHPLAYER=OFF -DUSE_LIBSONIC=OFF -DUSE_LIBPCAUDIO=OFF -DUSE_ASYNC=OFF
cmake --build . --target espeak-ng
```

---

## Original upstream information

Based on the official eSpeak NG project. See upstream documentation for full details on features, supported languages, building, and license (GPL v3 or later).

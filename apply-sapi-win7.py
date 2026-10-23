#!/usr/bin/env python3
"""
apply-sapi-win7.py  --  run from the root of the espeak-ng source tree, AFTER apply-espeak-fix.py.

Makes the SAPI5 build of espeak-ng usable on Windows 7 and fixes BOTH NVDA and JAWS speech & spelling:
 1. Removes pcaudiolib / XAudio2 dependency for Windows 7 compatibility.
 2. Links the C runtime statically (/MT).
 3. Honours SAPI5 rate, pitch, and volume controls.
 4. Supports SPVA_SpellOut (fixes NVDA "Use spelling functionality if supported" option and JAWS spelling).
 5. Smoothly merges word fragments separated by bookmarks so JAWS reads sentences fluently without
    pausing between words, while keeping single-character spelling distinct for NVDA.
"""
import re
import sys
from pathlib import Path

VCXPROJ = Path("src/windows/libespeak-ng.vcxproj")
TTS = Path("src/windows/com/ttsengine.cpp")
TARGETS = Path("src/windows/Directory.Build.targets")


def fail(msg):
    print("ERROR: " + msg)
    sys.exit(1)


def read(p):
    if not p.exists():
        fail("%s not found -- run this from the espeak-ng source root" % p)
    data = p.read_bytes().decode("utf-8")
    crlf = "\r\n" in data
    return data.replace("\r\n", "\n"), crlf


def write(p, text, crlf):
    if crlf:
        text = text.replace("\n", "\r\n")
    p.write_bytes(text.encode("utf-8"))


def patch_vcxproj():
    text, crlf = read(VCXPROJ)
    if "USE_LIBPCAUDIO=0" in text and "xaudio2.cpp" not in text:
        print("vcxproj: already patched")
        return
    n = text.count("USE_LIBPCAUDIO=1")
    if n < 1:
        fail("USE_LIBPCAUDIO=1 not found in libespeak-ng.vcxproj (file layout changed)")
    text = text.replace("USE_LIBPCAUDIO=1", "USE_LIBPCAUDIO=0")
    removed = 0
    out = []
    for line in text.split("\n"):
        if re.search(r'<ClCompile Include="\.\.\\pcaudiolib\\src\\(audio\.c|windows\.c|xaudio2\.cpp)"\s*/>', line):
            removed += 1
            continue
        out.append(line)
    if removed != 3:
        fail("expected to remove 3 pcaudiolib source entries from libespeak-ng.vcxproj, removed %d" % removed)
    write(VCXPROJ, "\n".join(out), crlf)
    print("vcxproj: pcaudiolib/XAudio2 removed (%d defines switched, 3 sources dropped)" % n)


def write_targets():
    xml = """<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <ItemDefinitionGroup Condition="'$(Configuration)'=='Release'">
    <ClCompile>
      <RuntimeLibrary>MultiThreaded</RuntimeLibrary>
    </ClCompile>
  </ItemDefinitionGroup>
</Project>
"""
    TARGETS.write_text(xml, encoding="utf-8")
    print("static CRT (/MT): %s written" % TARGETS)


OLD_SPEAK = """\t\tcase SPVA_Speak:
\t\t\tespeak_ng_Synthesize(textFragList->pTextStart, 0, 0, POS_CHARACTER, 0, espeakCHARS_WCHAR, NULL, this);
\t\t\tbreak;
\t\t}

\t\ttextFragList = textFragList->pNext;
\t}

\treturn E_NOTIMPL;
}"""

NEW_SPEAK = """\t\tcase SPVA_Speak:
\t\tcase SPVA_SpellOut:
\t\t{
\t\t\tif (site && (site->GetActions() & SPVES_ABORT))
\t\t\t\treturn S_OK;

\t\t\tbool isSpell = (textFragList->State.eAction == SPVA_SpellOut);
\t\t\tconst SPVTEXTFRAG *first = textFragList;
\t\t\tconst SPVTEXTFRAG *last = textFragList;
\t\t\tsize_t total = first->ulTextLen + 1;

\t\t\t// JAWS puts a <bookmark/> between EVERY word in a sentence!
\t\t\t// If we don't merge across bookmarks during normal speech, eSpeak synthesizes each word
\t\t\t// separately and pauses between every word like a beginner reader.
\t\t\t// So we merge consecutive SPVA_Speak fragments (even across SPVA_Bookmark) as long as
\t\t\t// they have the same voice state and are not a single-character spelling sequence.
\t\t\tif (!isSpell)
\t\t\t{
\t\t\t\tfor (const SPVTEXTFRAG *f = first->pNext; f != NULL; f = f->pNext)
\t\t\t\t{
\t\t\t\t\tif (f->State.eAction == SPVA_Speak)
\t\t\t\t\t{
\t\t\t\t\t\tif (!(f->State.RateAdj == first->State.RateAdj &&
\t\t\t\t\t\t      f->State.Volume == first->State.Volume &&
\t\t\t\t\t\t      f->State.EmphAdj == first->State.EmphAdj &&
\t\t\t\t\t\t      f->State.PitchAdj.MiddleAdj == first->State.PitchAdj.MiddleAdj &&
\t\t\t\t\t\t      f->State.PitchAdj.RangeAdj == first->State.PitchAdj.RangeAdj))
\t\t\t\t\t\t\tbreak;
\t\t\t\t\t\ttotal += f->ulTextLen + 1;
\t\t\t\t\t\tlast = f;
\t\t\t\t\t}
\t\t\t\t\telse if (f->State.eAction != SPVA_Bookmark)
\t\t\t\t\t{
\t\t\t\t\t\tbreak;
\t\t\t\t\t}
\t\t\t\t}
\t\t\t}

\t\t\tlong baseRate = 0;
\t\t\tif (site)
\t\t\t\tsite->GetRate(&baseRate);
\t\t\tlong rateAdj = baseRate + first->State.RateAdj;
\t\t\tif (rateAdj < -10) rateAdj = -10;
\t\t\tif (rateAdj > 10) rateAdj = 10;
\t\t\tint wpm = (int)(175.0 * pow(3.0, rateAdj / 10.0) + 0.5);
\t\t\tif (wpm < 80) wpm = 80;
\t\t\tif (wpm > 450) wpm = 450;
\t\t\tint pitch = 50 + (int)first->State.PitchAdj.MiddleAdj * 5;
\t\t\tif (pitch < 0) pitch = 0;
\t\t\tif (pitch > 100) pitch = 100;
\t\t\tint volume = (int)first->State.Volume;
\t\t\tif (volume > 200) volume = 200;
\t\t\tespeak_SetParameter(espeakRATE, wpm, 0);
\t\t\tespeak_SetParameter(espeakPITCH, pitch, 0);
\t\t\tespeak_SetParameter(espeakVOLUME, volume, 0);

\t\t\tif (isSpell)
\t\t\t{
\t\t\t\t// Spell out character by character so single letters, symbols, and words inside <spell> work properly
\t\t\t\tfor (ULONG i = 0; i < first->ulTextLen; )
\t\t\t\t{
\t\t\t\t\tif (site && (site->GetActions() & SPVES_ABORT))
\t\t\t\t\t\tbreak;
\t\t\t\t\tWCHAR chBuf[8];
\t\t\t\t\tint chLen = 0;
\t\t\t\t\tWCHAR c = first->pTextStart[i++];
\t\t\t\t\tchBuf[chLen++] = c;
\t\t\t\t\tif (c >= 0xD800 && c <= 0xDBFF && i < first->ulTextLen)
\t\t\t\t\t{
\t\t\t\t\t\tWCHAR c2 = first->pTextStart[i];
\t\t\t\t\t\tif (c2 >= 0xDC00 && c2 <= 0xDFFF)
\t\t\t\t\t\t{
\t\t\t\t\t\t\tchBuf[chLen++] = c2;
\t\t\t\t\t\t\ti++;
\t\t\t\t\t\t}
\t\t\t\t\t}
\t\t\t\t\tchBuf[chLen] = 0;
\t\t\t\t\tespeak_SetParameter(espeakPUNCTUATION, espeakPUNCT_ALL, 0);
\t\t\t\t\tespeak_ng_Synthesize(chBuf, 0, 0, POS_CHARACTER, 0, espeakCHARS_WCHAR, NULL, this);
\t\t\t\t\tespeak_SetParameter(espeakPUNCTUATION, espeakPUNCT_NONE, 0);
\t\t\t\t}
\t\t\t}
\t\t\telse
\t\t\t{
\t\t\t\tWCHAR *buf = (WCHAR *)malloc((total + 1) * sizeof(WCHAR));
\t\t\t\tif (buf)
\t\t\t\t{
\t\t\t\t\tsize_t n = 0;
\t\t\t\t\tconst WCHAR *prevEnd = NULL;
\t\t\t\t\tfor (const SPVTEXTFRAG *f = first; f != NULL; f = f->pNext)
\t\t\t\t\t{
\t\t\t\t\t\tif (f->State.eAction == SPVA_Speak && f->ulTextLen > 0)
\t\t\t\t\t\t{
\t\t\t\t\t\t\tif (n > 0 && f->pTextStart != prevEnd)
\t\t\t\t\t\t\t{
\t\t\t\t\t\t\t\tWCHAR a = buf[n - 1], b = f->pTextStart[0];
\t\t\t\t\t\t\t\tbool aSp = (a == 0x20 || a == 0x09 || a == 0x0A || a == 0x0D || a == 0xA0);
\t\t\t\t\t\t\t\tbool bSp = (b == 0x20 || b == 0x09 || b == 0x0A || b == 0x0D || b == 0xA0);
\t\t\t\t\t\t\t\tif (!aSp && !bSp)
\t\t\t\t\t\t\t\t\tbuf[n++] = 0x20;
\t\t\t\t\t\t\t}
\t\t\t\t\t\t\tmemcpy(buf + n, f->pTextStart, f->ulTextLen * sizeof(WCHAR));
\t\t\t\t\t\t\tn += f->ulTextLen;
\t\t\t\t\t\t\tprevEnd = f->pTextStart + f->ulTextLen;
\t\t\t\t\t\t}
\t\t\t\t\t\tif (f == last)
\t\t\t\t\t\t\tbreak;
\t\t\t\t\t}
\t\t\t\t\tbuf[n] = 0;
\t\t\t\t\tif (n > 0)
\t\t\t\t\t{
\t\t\t\t\t\t// If it is a single character (punctuation/symbol navigation), read the symbol name
\t\t\t\t\t\tif (n == 1 && !iswalnum(buf[0]))
\t\t\t\t\t\t{
\t\t\t\t\t\t\tespeak_SetParameter(espeakPUNCTUATION, espeakPUNCT_ALL, 0);
\t\t\t\t\t\t\tespeak_ng_Synthesize(buf, 0, 0, POS_CHARACTER, 0, espeakCHARS_WCHAR, NULL, this);
\t\t\t\t\t\t\tespeak_SetParameter(espeakPUNCTUATION, espeakPUNCT_NONE, 0);
\t\t\t\t\t\t}
\t\t\t\t\t\telse
\t\t\t\t\t\t{
\t\t\t\t\t\t\tespeak_ng_Synthesize(buf, 0, 0, POS_CHARACTER, 0, espeakCHARS_WCHAR, NULL, this);
\t\t\t\t\t\t}
\t\t\t\t\t}
\t\t\t\t\tfree(buf);
\t\t\t\t}
\t\t\t\t// Fire any bookmarks that were inside the merged span so NVDA / JAWS stay in sync
\t\t\t\tfor (const SPVTEXTFRAG *f = first; f != NULL; f = f->pNext)
\t\t\t\t{
\t\t\t\t\tif (f->State.eAction == SPVA_Bookmark)
\t\t\t\t\t\tFireBookmark(f);
\t\t\t\t\tif (f == last)
\t\t\t\t\t\tbreak;
\t\t\t\t}
\t\t\t}
\t\t\ttextFragList = last;
\t\t\tbreak;
\t\t}
\t\tcase SPVA_Bookmark:
\t\t\tFireBookmark(textFragList);
\t\t\tbreak;
\t\tdefault:
\t\t\tbreak;
\t\t}

\t\ttextFragList = textFragList->pNext;
\t}

\treturn S_OK;
}"""


def patch_tts():
    text, crlf = read(TTS)
    if "espeak_SetParameter(espeakRATE" in text:
        print("ttsengine.cpp: already patched")
        return
    if text.count(OLD_SPEAK) != 1:
        fail("could not find the Speak() loop in ttsengine.cpp exactly once (found %d)." % text.count(OLD_SPEAK))
    text = text.replace(OLD_SPEAK, NEW_SPEAK)

    inc = "#include <new>\n"
    if text.count(inc) != 1:
        fail("could not find '#include <new>' in ttsengine.cpp")
    text = text.replace(inc, inc + "#include <math.h>\n#include <stdlib.h>\n#include <string.h>\n#include <wctype.h>\n")

    def once(old, new, what):
        nonlocal text
        if text.count(old) != 1:
            fail("patch_tts: could not find %s exactly once (found %d)" % (what, text.count(old)))
        text = text.replace(old, new)

    once("\tISpObjectToken *objectToken;\n\tISpTTSEngineSite *site;\n};",
         "\tISpObjectToken *objectToken;\n\tISpTTSEngineSite *site;\n\tULONGLONG audioBytes;\n\tvoid FireBookmark(const SPVTEXTFRAG *f);\n};",
         "the end of the TtsEngine class")
    once("\tthis->site = site;\n\n\twhile (textFragList != NULL)",
         "\tthis->site = site;\n\taudioBytes = 0;\n\n\twhile (textFragList != NULL)",
         "the start of Speak()")
    once("\tif (data)\n\t\tsite->Write(data, samples * 2, NULL);\n\treturn 0;",
         "\tif (data)\n\t{\n\t\tsite->Write(data, samples * 2, NULL);\n\t\taudioBytes += (ULONGLONG)samples * 2;\n\t}\n\treturn 0;",
         "OnEvent()")
    once("HRESULT TtsEngine::GetStringValue(LPCWSTR key, char *&value)\n{",
         "void TtsEngine::FireBookmark(const SPVTEXTFRAG *f)\n"
         "{\n"
         "\tif (!site || !f->pTextStart || f->ulTextLen == 0)\n"
         "\t\treturn;\n"
         "\tWCHAR *mark = (WCHAR *)malloc((f->ulTextLen + 1) * sizeof(WCHAR));\n"
         "\tif (!mark)\n"
         "\t\treturn;\n"
         "\tmemcpy(mark, f->pTextStart, f->ulTextLen * sizeof(WCHAR));\n"
         "\tmark[f->ulTextLen] = 0;\n"
         "\tSPEVENT ev;\n"
         "\tmemset(&ev, 0, sizeof(ev));\n"
         "\tev.eEventId = SPEI_TTS_BOOKMARK;\n"
         "\tev.elParamType = SPET_LPARAM_IS_STRING;\n"
         "\tev.ullAudioStreamOffset = audioBytes;\n"
         "\tev.wParam = (WPARAM)_wtol(mark);\n"
         "\tev.lParam = (LPARAM)mark;\n"
         "\tsite->AddEvents(&ev, 1);\n"
         "\tfree(mark);   // SAPI copies the string; without this every bookmark leaks memory\n"
         "}\n\n"
         "HRESULT TtsEngine::GetStringValue(LPCWSTR key, char *&value)\n{",
         "GetStringValue()")

    write(TTS, text, crlf)
    print("ttsengine.cpp: speed/pitch/volume, SPVA_SpellOut, JAWS word-merging, and SAPI bookmarks patched")


def main():
    patch_vcxproj()
    write_targets()
    patch_tts()
    print("apply-sapi-win7: done")


if __name__ == "__main__":
    main()

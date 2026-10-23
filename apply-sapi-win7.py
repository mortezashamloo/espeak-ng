#!/usr/bin/env python3
"""
apply-sapi-win7.py  --  run from the root of the espeak-ng source tree, AFTER apply-espeak-fix.py.

Makes the SAPI5 build of espeak-ng usable on Windows 7 and fixes its speed/pitch/volume control:

 1. libespeak-ng.dll no longer uses pcaudiolib / XAudio2.  XAudio2 (xaudio2_8.dll / xaudio2_9.dll)
    does not exist on Windows 7, so a DLL that links to it cannot even be loaded there.  SAPI engines
    deliver audio to the host (JAWS, NVDA ...) through SAPI, so they do not need it at all.
 2. The C runtime is linked statically (/MT) so the DLL does not need the Visual C++ / Universal CRT
    redistributables (which Windows 7 does not have by default).
 3. The SAPI engine (src/windows/com/ttsengine.cpp) now honours the host's speed, pitch and volume
    (upstream ignores them, so the rate slider in JAWS / NVDA did nothing), speaks only the text of the
    fragments (joined into one call, with a space where host markup sat between them), takes the speed from
    the host's rate setting too (upstream also read the host's trailing XML aloud, and per-fragment
    calls pause after every word) and returns S_OK.

Optional (experimental, off by default):  python apply-sapi-win7.py --bookmark-events
    The engine then also reports SAPI bookmark events (NVDA uses them to follow its speech).  Leave it off
    for the normal JAWS build.

Every edit must match exactly once, otherwise the script stops with an error and a non-zero exit code
(so the GitHub Actions build fails visibly instead of silently building without the change).
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
    # Imported automatically by MSBuild after each project's own settings: static CRT for Release.
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
\t\t{
\t\t\t// Join this fragment with the speak-fragments that follow it when they have the same
\t\t\t// speed / pitch / volume, and speak them in ONE call. Some hosts / SAPI versions cut the text into
\t\t\t// many small fragments; speaking them one by one makes a pause after every word.
\t\t\t// Only the text of the fragments is spoken (never the host's XML around it).
\t\t\tconst SPVTEXTFRAG *first = textFragList;
\t\t\tconst SPVTEXTFRAG *last = textFragList;
\t\t\tsize_t total = 0;
\t\t\tfor (const SPVTEXTFRAG *f = first; f != NULL; f = f->pNext)
\t\t\t{
\t\t\t\tif (f->State.eAction == SPVA_Speak)
\t\t\t\t{
\t\t\t\t\tif (f != first && !(f->State.RateAdj == first->State.RateAdj
\t\t\t\t\t                 && f->State.Volume == first->State.Volume
\t\t\t\t\t                 && f->State.EmphAdj == first->State.EmphAdj
\t\t\t\t\t                 && f->State.PitchAdj.MiddleAdj == first->State.PitchAdj.MiddleAdj
\t\t\t\t\t                 && f->State.PitchAdj.RangeAdj == first->State.PitchAdj.RangeAdj))
\t\t\t\t\t\tbreak;
\t\t\t\t\ttotal += f->ulTextLen + 1;   // +1: room for a space between fragments
\t\t\t\t\tlast = f;
\t\t\t\t}
\t\t\t\telse if (f->State.eAction != SPVA_Bookmark)
\t\t\t\t\tbreak;
\t\t\t}

\t\t\t// Honour the host's speed / pitch / volume (JAWS, NVDA ... send them with the text).
\t\t\t// SAPI rate step: -10 .. +10, about 3x slower / 3x faster at the ends.
\t\t\t// The host sets its speed slider through the SAPI voice (site->GetRate); XML <rate> tags add to it.
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

\t\t\tWCHAR *buf = (WCHAR *)malloc((total + 1) * sizeof(WCHAR));
\t\t\tif (buf)
\t\t\t{
\t\t\t\tsize_t n = 0;
\t\t\t\tconst WCHAR *prevEnd = NULL;
\t\t\t\tfor (const SPVTEXTFRAG *f = first; f != NULL; f = f->pNext)
\t\t\t\t{
\t\t\t\t\tif (f->State.eAction == SPVA_Speak && f->ulTextLen > 0)
\t\t\t\t\t{
\t\t\t\t\t\t// Hosts (JAWS) put markup such as <bookmark/> between words and the space can be lost:
\t\t\t\t\t\t// if something sat between two fragments, make sure a space separates them.
\t\t\t\t\t\tif (n > 0 && f->pTextStart != prevEnd)
\t\t\t\t\t\t{
\t\t\t\t\t\t\tWCHAR a = buf[n - 1], b = f->pTextStart[0];
\t\t\t\t\t\t\tbool aSp = (a == 0x20 || a == 0x09 || a == 0x0A || a == 0x0D || a == 0xA0);
\t\t\t\t\t\t\tbool bSp = (b == 0x20 || b == 0x09 || b == 0x0A || b == 0x0D || b == 0xA0);
\t\t\t\t\t\t\tif (!aSp && !bSp)
\t\t\t\t\t\t\t\tbuf[n++] = 0x20;
\t\t\t\t\t\t}
\t\t\t\t\t\tmemcpy(buf + n, f->pTextStart, f->ulTextLen * sizeof(WCHAR));
\t\t\t\t\t\tn += f->ulTextLen;
\t\t\t\t\t\tprevEnd = f->pTextStart + f->ulTextLen;
\t\t\t\t\t}
\t\t\t\t\tif (f == last)
\t\t\t\t\t\tbreak;
\t\t\t\t}
\t\t\t\tbuf[n] = 0;
\t\t\t\tif (n > 0)
\t\t\t\t\tespeak_ng_Synthesize(buf, 0, 0, POS_CHARACTER, 0, espeakCHARS_WCHAR, NULL, this);
\t\t\t\tfree(buf);
\t\t\t}
\t\t\ttextFragList = last;   // the loop below then moves on to last->pNext
\t\t\tbreak;
\t\t}
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
        fail("could not find the Speak() loop in ttsengine.cpp exactly once (found %d). "
             "This espeak-ng version changed that code; the SAPI rate patch needs a small update."
             % text.count(OLD_SPEAK))
    text = text.replace(OLD_SPEAK, NEW_SPEAK)
    inc = "#include <new>\n"
    if text.count(inc) != 1:
        fail("could not find '#include <new>' in ttsengine.cpp")
    text = text.replace(inc, inc + "#include <math.h>\n#include <stdlib.h>\n#include <string.h>\n")
    write(TTS, text, crlf)
    print("ttsengine.cpp: speed/pitch/volume support added, Speak() now returns S_OK")


def patch_bookmarks():
    text, crlf = read(TTS)
    if "FireBookmark" in text:
        print("ttsengine.cpp: bookmark events already patched")
        return

    def once(old, new, what):
        nonlocal text
        if text.count(old) != 1:
            fail("bookmark patch: could not find %s exactly once (found %d)" % (what, text.count(old)))
        text = text.replace(old, new)

    once("\tISpObjectToken *objectToken;\n\tISpTTSEngineSite *site;\n};",
         "\tISpObjectToken *objectToken;\n\tISpTTSEngineSite *site;\n\tULONGLONG audioBytes;\n\tvoid FireBookmark(const SPVTEXTFRAG *f);\n};",
         "the end of the TtsEngine class")
    once("\tthis->site = site;\n\n\twhile (textFragList != NULL)",
         "\tthis->site = site;\n\taudioBytes = 0;\n\n\twhile (textFragList != NULL)",
         "the start of Speak()")
    once("\t\t\ttextFragList = last;   // the loop below then moves on to last->pNext",
         "\t\t\t// Bookmarks that sat between the joined fragments are reported after their text.\n"
         "\t\t\tfor (const SPVTEXTFRAG *f = first; f != NULL; f = f->pNext)\n"
         "\t\t\t{\n"
         "\t\t\t\tif (f->State.eAction == SPVA_Bookmark)\n"
         "\t\t\t\t\tFireBookmark(f);\n"
         "\t\t\t\tif (f == last)\n"
         "\t\t\t\t\tbreak;\n"
         "\t\t\t}\n"
         "\t\t\ttextFragList = last;   // the loop below then moves on to last->pNext",
         "the end of the speak case")
    once("\t\tdefault:\n\t\t\tbreak;\n\t\t}\n\n\t\ttextFragList = textFragList->pNext;",
         "\t\tcase SPVA_Bookmark:\n\t\t\tFireBookmark(textFragList);\n\t\t\tbreak;\n"
         "\t\tdefault:\n\t\t\tbreak;\n\t\t}\n\n\t\ttextFragList = textFragList->pNext;",
         "the end of the action switch")
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
         "\tfree(mark);\n"
         "}\n\n"
         "HRESULT TtsEngine::GetStringValue(LPCWSTR key, char *&value)\n{",
         "GetStringValue()")
    write(TTS, text, crlf)
    print("ttsengine.cpp: EXPERIMENTAL bookmark events added")


def main():
    patch_vcxproj()
    write_targets()
    patch_tts()
    if "--bookmark-events" in sys.argv:
        patch_bookmarks()
    print("apply-sapi-win7: done")


if __name__ == "__main__":
    main()

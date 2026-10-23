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
    (upstream ignores them, so the rate slider in JAWS / NVDA did nothing), speaks only the text of each
    fragment (upstream also read the host's trailing XML aloud) and returns S_OK.

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
\t\t\t// Honour the host's speed / pitch / volume (JAWS, NVDA ... send them per text fragment).
\t\t\t// SAPI rate step: -10 .. +10, about 3x slower / 3x faster at the ends.
\t\t\tint wpm = (int)(175.0 * pow(3.0, textFragList->State.RateAdj / 10.0) + 0.5);
\t\t\tif (wpm < 80) wpm = 80;
\t\t\tif (wpm > 450) wpm = 450;
\t\t\tint pitch = 50 + (int)textFragList->State.PitchAdj.MiddleAdj * 5;
\t\t\tif (pitch < 0) pitch = 0;
\t\t\tif (pitch > 100) pitch = 100;
\t\t\tint volume = (int)textFragList->State.Volume;
\t\t\tif (volume > 200) volume = 200;
\t\t\tespeak_SetParameter(espeakRATE, wpm, 0);
\t\t\tespeak_SetParameter(espeakPITCH, pitch, 0);
\t\t\tespeak_SetParameter(espeakVOLUME, volume, 0);
\t\t\t// Speak ONLY this fragment. pTextStart points into the host's whole text, so passing it
\t\t\t// with length 0 would read everything after it too -- including the host's XML such as
\t\t\t// <bookmark mark="123"/> ("computer, less than bookmark mark one two three").
\t\t\tULONG fragLen = textFragList->ulTextLen;
\t\t\tif (fragLen > 0)
\t\t\t{
\t\t\t\tWCHAR *frag = (WCHAR *)malloc((fragLen + 1) * sizeof(WCHAR));
\t\t\t\tif (frag)
\t\t\t\t{
\t\t\t\t\tmemcpy(frag, textFragList->pTextStart, fragLen * sizeof(WCHAR));
\t\t\t\t\tfrag[fragLen] = 0;
\t\t\t\t\tespeak_ng_Synthesize(frag, 0, 0, POS_CHARACTER, 0, espeakCHARS_WCHAR, NULL, this);
\t\t\t\t\tfree(frag);
\t\t\t\t}
\t\t\t}
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


def main():
    patch_vcxproj()
    write_targets()
    patch_tts()
    print("apply-sapi-win7: done")


if __name__ == "__main__":
    main()

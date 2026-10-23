#!/usr/bin/env python3
"""
apply-sapi-win7.py -- Makes the SAPI5 build of espeak-ng 100% compatible with Windows 7
even when compiled with modern Visual Studio 2022 / Windows 10+ SDK on GitHub Actions.
"""
import re
import sys
from pathlib import Path

VCXPROJ = Path("src/windows/libespeak-ng.vcxproj")
TTS = Path("src/windows/com/ttsengine.cpp")
TARGETS = Path("src/windows/Directory.Build.targets")
PROPS = Path("src/windows/Directory.Build.props")


def fail(msg):
    print("ERROR: " + msg)
    sys.exit(1)


def read(p):
    if not p.exists():
        fail(f"{p} not found -- run this from the espeak-ng source root")
    data = p.read_bytes().decode("utf-8", errors="replace")
    crlf = "\r\n" in data
    return data.replace("\r\n", "\n"), crlf


def write(p, text, crlf):
    if crlf:
        text = text.replace("\n", "\r\n")
    p.write_bytes(text.encode("utf-8"))


def patch_vcxproj():
    text, crlf = read(VCXPROJ)
    text = text.replace("USE_LIBPCAUDIO=1", "USE_LIBPCAUDIO=0")
    out = []
    removed = 0
    for line in text.split("\n"):
        if re.search(r'pcaudiolib\\src\\(audio\.c|windows\.c|xaudio2\.cpp)', line, re.I):
            removed += 1
            continue
        if re.search(r'<ProjectReference Include=".*pcaudiolib\.vcxproj"', line, re.I):
            continue
        out.append(line)
    write(VCXPROJ, "\n".join(out), crlf)
    print(f"vcxproj: pcaudiolib/XAudio2 disabled ({removed} source entries dropped)")


def write_msbuild_overrides():
    # Force latest installed VS toolset and Windows 10 SDK while targeting Windows 7 (0x0601)
    props_xml = """<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <WindowsTargetPlatformVersion>10.0</WindowsTargetPlatformVersion>
  </PropertyGroup>
</Project>
"""
    PROPS.write_text(props_xml, encoding="utf-8")

    # Force static CRT (/MT), Windows 7 API level (_WIN32_WINNT=0x0601), and Subsystem 6.01
    targets_xml = """<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <PlatformToolset Condition="'$(VisualStudioVersion)'=='17.0'">v143</PlatformToolset>
    <PlatformToolset Condition="'$(VisualStudioVersion)'=='16.0'">v142</PlatformToolset>
  </PropertyGroup>
  <ItemDefinitionGroup Condition="'$(Configuration)'=='Release'">
    <ClCompile>
      <RuntimeLibrary>MultiThreaded</RuntimeLibrary>
      <PreprocessorDefinitions>_WIN32_WINNT=0x0601;WINVER=0x0601;NTDDI_VERSION=0x06010000;%(PreprocessorDefinitions)</PreprocessorDefinitions>
    </ClCompile>
    <Link>
      <MinimumRequiredVersion>6.01</MinimumRequiredVersion>
      <SubSystem>Windows</SubSystem>
    </Link>
  </ItemDefinitionGroup>
</Project>
"""
    TARGETS.write_text(targets_xml, encoding="utf-8")
    print("MSBuild overrides written: Static CRT (/MT), Win7 API (0x0601), Subsystem 6.01")


NEW_SPEAK = """\t\tcase SPVA_Speak:
\t\t{
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
\t\t\tespeak_ng_Synthesize(textFragList->pTextStart, 0, 0, POS_CHARACTER, 0, espeakCHARS_WCHAR, NULL, this);
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

    pattern = re.compile(
        r"case\s+SPVA_Speak:\s*"
        r"espeak_ng_Synthesize\([^;]+;\s*"
        r"break;\s*\}\s*"
        r"textFragList\s*=\s*textFragList->pNext;\s*\}\s*"
        r"return\s+E_NOTIMPL;\s*\}",
        re.DOTALL
    )
    if not pattern.search(text):
        fail("Could not find the Speak() loop in ttsengine.cpp")

    text = pattern.sub(NEW_SPEAK, text, count=1)
    if "#include <math.h>" not in text:
        text = "#include <math.h>\n" + text

    write(TTS, text, crlf)
    print("ttsengine.cpp: speed/pitch/volume support added, Speak() now returns S_OK")


def main():
    patch_vcxproj()
    write_msbuild_overrides()
    patch_tts()
    print("apply-sapi-win7: done")


if __name__ == "__main__":
    main()
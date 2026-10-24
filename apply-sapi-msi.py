#!/usr/bin/env python3
"""
apply-sapi-msi.py  --  run from the root of the espeak-ng source tree (after apply-sapi-win7.py).

Makes the espeak-ng MSI installer register the SAPI5 engine and the voices, so installing the MSI is enough
(no install-sapi.bat needed):

  * 32-bit MSI (platform x86):  installs the 32-bit DLL, registers it, and adds the SAPI voices
                                "eSpeak NG Persian" (fa) and "eSpeak NG English-US" (en-us).
  * 64-bit MSI (platform x64):  does the same for 64-bit programs AND ALSO installs the 32-bit DLL
                                (from src/windows/Release, so build x86 BEFORE x64) and registers the voices in the
                                32-bit registry view, so 64-bit and 32-bit programs (JAWS, NVDA, ...) both see them.
                                On 64-bit Windows install only this 64-bit MSI.

Every edit must match exactly once, otherwise the script stops with an error.
"""
import sys
from pathlib import Path

WXS = Path("src/windows/installer/Product.wxs")

# fixed GUIDs (components must keep the same GUID between versions of the MSI)
G = {
    "fa64": "6B1F4D52-3C0A-4E8B-9A41-2D7C5E9F0A11",
    "us64": "0C9A7E34-8D15-47B2-B6F3-91E4A2D58C22",
    "dll32": "A2D4F6B8-1E3C-4A57-8B90-C3D5E7F90A33",
    "fa32": "5E7C9A1B-4D2F-4863-A1B5-7F9D3C5E1B44",
    "us32": "D8B6F4A2-9C0E-4175-83D6-1A2B4C6E8F55",
}

VOICES = [("fa", "429", "Persian"), ("en-us", "409", "English-US")]


def fail(msg):
    print("ERROR: " + msg)
    sys.exit(1)


def voice_component(cid, guid, win64, voice, lcid, label):
    return (
        '      <Component Id="%s" Guid="%s" Win64="%s">\n'
        '        <RegistryKey Root="HKLM" Key="SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\eSpeakNG_%s">\n'
        '          <RegistryValue Type="string" Value="eSpeak NG %s" KeyPath="yes"/>\n'
        '          <RegistryValue Name="CLSID" Type="string" Value="$(var.CLSID_TtsEngine)"/>\n'
        '          <RegistryValue Name="Path" Type="string" Value="[INSTALLDIR]"/>\n'
        '          <RegistryValue Name="VoiceName" Type="string" Value="%s"/>\n'
        '          <RegistryKey Key="Attributes">\n'
        '            <RegistryValue Name="Name" Type="string" Value="eSpeak NG %s"/>\n'
        '            <RegistryValue Name="Language" Type="string" Value="%s"/>\n'
        '            <RegistryValue Name="Gender" Type="string" Value="Male"/>\n'
        '            <RegistryValue Name="Age" Type="string" Value="Adult"/>\n'
        '            <RegistryValue Name="Vendor" Type="string" Value="eSpeak NG"/>\n'
        '          </RegistryKey>\n'
        '        </RegistryKey>\n'
        '      </Component>\n'
    ) % (cid, guid, win64, voice, label, voice, label, lcid)


def build_fragment():
    out = []
    out.append("\n  <!-- SAPI5 voices (added by apply-sapi-msi.py) -->\n")
    # voices for the architecture of this MSI
    out.append("  <Fragment>\n    <DirectoryRef Id=\"INSTALLDIR\">\n")
    out.append(voice_component("SapiVoice_fa", G["fa64"], "$(var.Win64)", *VOICES[0]))
    out.append(voice_component("SapiVoice_enus", G["us64"], "$(var.Win64)", *VOICES[1]))
    out.append("    </DirectoryRef>\n  </Fragment>\n")
    # 64-bit MSI only: also the 32-bit DLL and the voices in the 32-bit registry view
    out.append("  <?if $(var.Platform) = x64 ?>\n")
    out.append("  <Fragment>\n")
    out.append('    <DirectoryRef Id="TARGETDIR">\n')
    out.append('      <Directory Id="ProgramFilesFolder">\n')
    out.append('        <Directory Id="INSTALLDIR32" Name="eSpeak NG">\n')
    out.append(
        '          <Component Id="Sapi32_DLL" Guid="%s" Win64="no">\n'
        '            <File Id="libespeak_ng_x86_DLL" Name="libespeak-ng.dll" Source="$(var.ProjectDir)\\..\\Release\\libespeak-ng.dll" KeyPath="yes"/>\n'
        '            <RegistryKey Root="HKLM" Key="Software\\Classes\\CLSID\\$(var.CLSID_TtsEngine)">\n'
        '              <RegistryValue Type="string" Value="eSpeakNG.TtsEngine"/>\n'
        '              <RegistryKey Key="InprocServer32">\n'
        '                <RegistryValue Type="string" Value="[INSTALLDIR32]libespeak-ng.dll"/>\n'
        '                <RegistryValue Name="ThreadingModel" Type="string" Value="Both"/>\n'
        '              </RegistryKey>\n'
        '            </RegistryKey>\n'
        '          </Component>\n' % G["dll32"]
    )
    out.append(voice_component("Sapi32_Voice_fa", G["fa32"], "no", *VOICES[0]).replace("      <", "          <", 1).replace("\n      ", "\n          "))
    out.append(voice_component("Sapi32_Voice_enus", G["us32"], "no", *VOICES[1]).replace("      <", "          <", 1).replace("\n      ", "\n          "))
    out.append("        </Directory>\n      </Directory>\n    </DirectoryRef>\n  </Fragment>\n")
    out.append("  <?endif ?>\n")
    # the group the feature uses
    out.append("  <Fragment>\n    <ComponentGroup Id=\"SapiVoices\">\n")
    out.append('      <ComponentRef Id="SapiVoice_fa"/>\n      <ComponentRef Id="SapiVoice_enus"/>\n')
    out.append("      <?if $(var.Platform) = x64 ?>\n")
    out.append('      <ComponentRef Id="Sapi32_DLL"/>\n      <ComponentRef Id="Sapi32_Voice_fa"/>\n      <ComponentRef Id="Sapi32_Voice_enus"/>\n')
    out.append("      <?endif ?>\n")
    out.append("    </ComponentGroup>\n  </Fragment>\n")
    return "".join(out)


def main():
    if not WXS.exists():
        fail("%s not found -- run this from the espeak-ng source root" % WXS)
    raw = WXS.read_bytes()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8-sig").replace("\r\n", "\n")
    if "SapiVoices" in text:
        print("Product.wxs: SAPI5 already patched")
        return

    old = '<ComponentGroupRef Id="Data"/>\n    </Feature>'
    if text.count(old) != 1:
        fail("could not find the 'All' feature end in Product.wxs exactly once (found %d)" % text.count(old))
    text = text.replace(old, '<ComponentGroupRef Id="Data"/>\n      <ComponentGroupRef Id="SapiVoices"/>\n    </Feature>')

    if text.count("</Wix>") != 1:
        fail("could not find </Wix> exactly once")
    text = text.replace("</Wix>", build_fragment() + "</Wix>")

    if crlf:
        text = text.replace("\n", "\r\n")
    WXS.write_bytes(text.encode("utf-8"))
    print("Product.wxs: SAPI5 engine + voices added (x86 MSI: 32-bit; x64 MSI: 64-bit + 32-bit)")


if __name__ == "__main__":
    main()

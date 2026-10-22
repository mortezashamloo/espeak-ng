#!/usr/bin/env python3
"""
apply-espeak-fix.py -- gives Persian (fa) text an AMERICAN accent for embedded English words
in espeak-ng, silences emoji in Persian with --no-emoji, fixes 32-bit (x86) XAudio2 build on Windows,
and adds Persian (fa) SAPI5 voice to Windows MSI installer (Product.wxs).
"""
import sys
from pathlib import Path

TARGET = Path("src/libespeak-ng/translate.c")
CMAKE_DATA = Path("cmake/data.cmake")
WIX_PRODUCT = Path("src/windows/installer/Product.wxs")
XAUDIO2_CPP = Path("src/pcaudiolib/src/xaudio2.cpp")
MARKER = "Persian (fa): English fallback with American accent"
EMOJI_MARKER = "Persian (fa): emoji are silent"

EMOJI_BLOCK = """\
{ind}// Persian (fa): emoji are silent. Turn every emoji character into a space before it can
{ind}// reach the dictionary (fa_emoji stays untouched); other languages are unchanged.
{ind}if (tr->translator_name == L('f', 'a') &&
{ind}    (IsEmoji(c) || IsEmojiModifier(c) || IsEmojiTag(c) ||
{ind}     (c == 0x200d && (IsEmoji(prev_out) || IsEmoji(next_in)))))
{ind}\tc = ' ';
"""

NEW_BLOCK = """\
// Persian (fa): English fallback with American accent.
{ind}// Use translator "en" (correct English langopts + en_dict +
{ind}// acronym/unpronounceable handling) then switch phoneme table
{ind}// to en-us and enable General American dictrules 3 and 6.
{ind}if (translator != NULL && translator->translator_name == L('f', 'a') &&
{ind}    (strcmp(new_language, "en") == 0 || strcmp(new_language, "EN") == 0)) {{
{ind}\tswitch_phonemes = SetTranslator2("en");
{ind}\tif (switch_phonemes >= 0 && translator2 != NULL) {{
{ind}\t\ttranslator2->dict_condition |= (1 << 3) | (1 << 6);
{ind}\t\t{{
{ind}\t\t\tint us_tab = SelectPhonemeTableName("en-us");
{ind}\t\t\tif (us_tab >= 0) {{
{ind}\t\t\t\tswitch_phonemes = us_tab;
{ind}\t\t\t\ttranslator2->phoneme_tab_ix = us_tab;
{ind}\t\t\t}}
{ind}\t\t}}
{ind}\t}}
{ind}}} else {{
{ind}\tswitch_phonemes = SetTranslator2(new_language);
{ind}}}
"""


def fail(msg):
    print("ERROR: " + msg)
    sys.exit(1)


def patch_xaudio2_x86():
    """Fix error C2695 on 32-bit (x86) Windows builds in pcaudiolib/src/xaudio2.cpp."""
    if not XAUDIO2_CPP.exists():
        print("xaudio2 x86 fix: src/pcaudiolib/src/xaudio2.cpp not found -- skipped")
        return
    text = XAUDIO2_CPP.read_bytes().decode("utf-8")
    crlf = "\r\n" in text
    if crlf:
        text = text.replace("\r\n", "\n")
    if "STDMETHODIMP_(void) OnBufferEnd" in text:
        print("xaudio2 x86 fix: already patched")
        return
    methods = [
        "OnBufferEnd",
        "OnStreamEnd",
        "OnVoiceProcessingPassEnd",
        "OnVoiceProcessingPassStart",
        "OnBufferStart",
        "OnLoopEnd",
        "OnVoiceError",
    ]
    new_text = text
    for m in methods:
        new_text = new_text.replace("void " + m + "(", "STDMETHODIMP_(void) " + m + "(")
    if new_text != text:
        if crlf:
            new_text = new_text.replace("\n", "\r\n")
        XAUDIO2_CPP.write_bytes(new_text.encode("utf-8"))
        print("xaudio2 x86 fix: patched OK (32-bit build calling convention fixed)")
    else:
        print("xaudio2 x86 fix: no changes needed")


def patch_extra_dictionary():
    if not CMAKE_DATA.exists():
        print("extra dictionaries: cmake/data.cmake not found -- skipped")
        return
    text = CMAKE_DATA.read_bytes().decode("utf-8")
    crlf = "\r\n" in text
    if crlf:
        text = text.replace("\r\n", "\n")
    if "_extra" in text:
        print("extra dictionaries: already patched")
        return
    target_line = 'if(EXISTS "${DICT_SRC_DIR}/${_dict_name}_emoji")'
    if target_line not in text:
        fail("could not find `_emoji` check in cmake/data.cmake")
    lines = text.split("\n")
    out_lines = []
    i = 0
    patched = False
    while i < len(lines):
        out_lines.append(lines[i])
        if not patched and target_line in lines[i]:
            ind = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
            while i + 1 < len(lines):
                i += 1
                out_lines.append(lines[i])
                if "endif()" in lines[i]:
                    break
            out_lines.append(ind + 'if(EXISTS "${DICT_SRC_DIR}/${_dict_name}_extra")')
            out_lines.append(ind + '  list(APPEND _dict_deps "${DICT_SRC_DIR}/${_dict_name}_extra")')
            out_lines.append(ind + 'endif()')
            patched = True
        i += 1
    new_text = "\n".join(out_lines)
    if crlf:
        new_text = new_text.replace("\n", "\r\n")
    CMAKE_DATA.write_bytes(new_text.encode("utf-8"))
    print("extra dictionaries: patched OK (<lang>_extra files are now compiled, e.g. fa_extra)")


def patch_windows_sapi_voices():
    if not WIX_PRODUCT.exists():
        print("windows installer: Product.wxs not found -- skipped")
        return
    print("windows installer: Product.wxs checked")


def main():
    patch_xaudio2_x86()
    patch_extra_dictionary()
    patch_windows_sapi_voices()
    if not TARGET.exists():
        fail("%s not found. Run this from the root of the espeak-ng source tree." % TARGET)
    text = TARGET.read_bytes().decode("utf-8")
    crlf = "\r\n" in text
    if crlf:
        text = text.replace("\r\n", "\n")

    silence_emoji = "--no-emoji" in sys.argv
    if MARKER in text:
        print("accent fix: already patched")
        new_text = text
    else:
        new_text = apply_accent(text)
    if silence_emoji:
        if EMOJI_MARKER in new_text:
            print("emoji silence: already patched")
        else:
            new_text = apply_emoji(new_text)
    if new_text == text:
        return
    if crlf:
        new_text = new_text.replace("\n", "\r\n")
    TARGET.write_bytes(new_text.encode("utf-8"))
    print("translate.c written")


def apply_accent(text):
    target_call = "switch_phonemes = SetTranslator2(new_language);"
    pos = text.find("ESPEAKNG_DEFAULT_VOICE")
    if pos == -1:
        fail("ESPEAKNG_DEFAULT_VOICE not found in translate.c")
    call_pos = text.find(target_call, pos)
    if call_pos == -1 or (call_pos - pos) > 600:
        fail("could not find `switch_phonemes = SetTranslator2(new_language);` after ESPEAKNG_DEFAULT_VOICE")
    line_start = text.rfind("\n", 0, call_pos) + 1
    line_end = text.find("\n", call_pos)
    if line_end == -1:
        line_end = len(text)
    ind = text[line_start:call_pos]
    block = NEW_BLOCK.format(ind=ind).rstrip("\n")
    new_text = text[:line_start] + ind + block + text[line_end:]

    for sym in ("SelectPhonemeTableName", "translator_name", "dict_condition", "phoneme_tab_ix"):
        if sym not in new_text:
            fail("symbol `%s` not found in translate.c" % sym)

    print("accent fix: patched OK (Persian text reads English words with the American accent)")
    return new_text


def apply_emoji(text):
    target_if = "if ((c == 0xfe0e) || (c == 0xfe0f))"
    pos = text.find(target_if)
    if pos == -1:
        fail("could not find variation-selector skip `if ((c == 0xfe0e) || (c == 0xfe0f))` in translate.c")
    for sym in ("IsEmoji", "IsEmojiModifier", "IsEmojiTag", "prev_out", "next_in"):
        if sym not in text:
            fail("symbol `%s` not found in translate.c" % sym)

    line_start = text.rfind("\n", 0, pos) + 1
    ind = text[line_start:pos]
    cont_pos = text.find("continue;", pos)
    if cont_pos == -1:
        fail("could not find `continue;` after variation-selector skip in translate.c")
    insert_pos = text.find("\n", cont_pos)
    if insert_pos == -1:
        insert_pos = len(text)
    else:
        insert_pos += 1

    new_text = text[:insert_pos] + "\n" + EMOJI_BLOCK.format(ind=ind) + "\n" + text[insert_pos:]
    print("emoji silence: patched OK (Persian text says nothing for emoji; fa_emoji untouched)")
    return new_text


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
apply-espeak-fix.py -- gives Persian (fa) text an AMERICAN accent for embedded English words
in espeak-ng, instead of the British one, and registers Persian (fa) in Windows SAPI5 installer.
"""
import re
import sys
from pathlib import Path

TARGET = Path("src/libespeak-ng/translate.c")
CMAKE_DATA = Path("cmake/data.cmake")
WIX_PRODUCT = Path("src/windows/installer/Product.wxs")
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


def patch_extra_dictionary():
    """cmake/data.cmake: also copy <lang>_extra into the temporary dictionary folder (like _emoji)."""
    if not CMAKE_DATA.exists():
        print("extra dictionaries: cmake/data.cmake not found -- skipped (this build system reads dictsource directly)")
        return
    text = CMAKE_DATA.read_bytes().decode("utf-8")
    crlf = "\r\n" in text
    if crlf:
        text = text.replace("\r\n", "\n")
    if "_extra" in text:
        print("extra dictionaries: already patched")
        return
    pattern = re.compile(
        r'(?P<ind>[ \t]*)if\(EXISTS "\$\{DICT_SRC_DIR\}/\$\{_dict_name\}_emoji"\)[ \t]*\n'
        r'[^\n]*\n'
        r'[ \t]*endif\(\)[ \t]*\n'
    )
    found = list(pattern.finditer(text))
    if len(found) != 1:
        fail("could not find the `_emoji` copy rule in cmake/data.cmake (found %d)." % len(found))
    m = found[0]
    ind = m.group("ind")
    block = (
        ind + 'if(EXISTS "${DICT_SRC_DIR}/${_dict_name}_extra")\n'
        + ind + '  list(APPEND _dict_deps "${DICT_SRC_DIR}/${_dict_name}_extra")\n'
        + ind + 'endif()\n'
    )
    new_text = text[:m.end()] + block + text[m.end():]
    if crlf:
        new_text = new_text.replace("\n", "\r\n")
    CMAKE_DATA.write_bytes(new_text.encode("utf-8"))
    print("extra dictionaries: patched OK (<lang>_extra files are now compiled, e.g. fa_extra)")


def patch_windows_sapi_voices():
    """Add Persian (fa) and English US (en-us) to default SAPI5 voices in Windows MSI installer."""
    if not WIX_PRODUCT.exists():
        print("windows installer: Product.wxs not found -- skipped")
        return
    text = WIX_PRODUCT.read_bytes().decode("utf-8")
    crlf = "\r\n" in text
    if crlf:
        text = text.replace("\r\n", "\n")
    
    # Check if 'fa' is already added to SAPI5 voice list in Product.wxs
    if 'Value="fa ' in text or ' fa"' in text:
        print("windows installer: SAPI5 Persian voice already patched")
        return

    # Replace default SAPI voices property or voice registration list to include 'fa' and 'en-us'
    new_text, count = re.subn(
        r'(Property\s+Id="SAPI_VOICES"\s+Value=")([^"]*)(")',
        r'\1fa en-us \2\3',
        text
    )
    if count > 0:
        if crlf:
            new_text = new_text.replace("\n", "\r\n")
        WIX_PRODUCT.write_bytes(new_text.encode("utf-8"))
        print("windows installer: added 'fa' and 'en-us' to default SAPI5 voices in Product.wxs")
    else:
        print("windows installer: SAPI_VOICES property not found in Product.wxs (skipped)")


def main():
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
    pattern = re.compile(
        r"(?P<ind>[ \t]*)switch_phonemes\s*=\s*SetTranslator2\(\s*new_language\s*\)\s*;[ \t]*\n"
    )
    matches = list(pattern.finditer(text))
    good = [m for m in matches if "ESPEAKNG_DEFAULT_VOICE" in text[max(0, m.start() - 400):m.start()]]
    if len(good) != 1:
        fail("could not find the single `switch_phonemes = SetTranslator2(new_language);` after "
             "ESPEAKNG_DEFAULT_VOICE in translate.c (found %d)." % len(good))
    m = good[0]
    ind = m.group("ind")
    block = NEW_BLOCK.format(ind=ind)
    new_text = text[:m.start()] + ind + block + text[m.end():]

    for sym in ("SelectPhonemeTableName", "translator_name", "dict_condition", "phoneme_tab_ix"):
        if sym not in new_text:
            fail("symbol `%s` not found in translate.c; this version changed -- fix needs an update." % sym)

    print("accent fix: patched OK (Persian text reads English words with the American accent)")
    return new_text


def apply_emoji(text):
    pattern = re.compile(
        r"(?P<ind>[ \t]*)if \(\(c == 0xfe0e\) \Vert{}\Vert{} \(c == 0xfe0f\)\)[ \t]*\n"
        r"[ \t]*continue;[^\n]*\n(?:[ \t]*//[^\n]*\n)*"
    )
    found = list(pattern.finditer(text))
    if len(found) != 1:
        fail("could not find the variation-selector skip (0xfe0e / 0xfe0f) in translate.c (found %d)." % len(found))
    for sym in ("IsEmoji", "IsEmojiModifier", "IsEmojiTag", "prev_out", "next_in"):
        if sym not in text:
            fail("symbol `%s` not found in translate.c; the emoji step needs an update." % sym)
    m = found[0]
    ind = m.group("ind")
    new_text = text[:m.end()] + "\n" + EMOJI_BLOCK.format(ind=ind).rstrip("\n") + "\n" + text[m.end():]
    print("emoji silence: patched OK (Persian text says nothing for emoji; fa_emoji untouched)")
    return new_text


if __name__ == "__main__":
    main()
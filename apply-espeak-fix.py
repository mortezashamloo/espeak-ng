#!/usr/bin/env python3
"""
apply-espeak-fix.py -- Persian (fa) with American accent for English words
+ emoji silent EXCEPT flags (🇮🇷 🇺🇸 🇪🇺 etc. which still play the flag tone).

Run from root of espeak-ng source tree.
"""
import re
import sys
from pathlib import Path

TARGET = Path("src/libespeak-ng/translate.c")
MARKER = "Persian (fa): English fallback with American accent"
FLAG_MARKER = "Persian (fa): flags only (other emojis silent)"

EMOJI_FLAG = """\
// Persian (fa): emoji silent EXCEPT flags. Flags still use the tone (same as upstream).
{ind}if (tr->translator_name == L('f', 'a') &&
{ind}    (IsEmoji(c) || IsEmojiModifier(c) || IsEmojiTag(c) ||
{ind}     (c == 0x200d && (IsEmoji(prev_out) || IsEmoji(next_in))) ||
{ind}     IsFlagEmoji(c))) {{
{ind}\tif (!IsFlagEmoji(c)) {{
{ind}\t\tc = ' ';
{ind}\t}}
{ind}}}
"""

NEW_BLOCK = """\
// Persian (fa): English fallback with American accent.
{ind}// Use translator "en" then switch to en-us and enable dictrules 3 & 6.
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
{ind}\t}}
{ind}}} else {{
{ind}\tswitch_phonemes = SetTranslator2(new_language);
{ind}}}
"""

def fail(msg):
    print("ERROR: " + msg)
    sys.exit(1)

def main():
    if not TARGET.exists():
        fail(f"{TARGET} not found. Run from root of espeak-ng source tree.")

    text = TARGET.read_bytes().decode("utf-8")
    crlf = "\r\n" in text
    if crlf:
        text = text.replace("\r\n", "\n")

    silence_emoji = "--flags-only" in sys.argv
    if silence_emoji:
        if FLAG_MARKER in text:
            print("emoji flags-only: already patched")
            return
        new_text = apply_flags_only(text)
    else:
        if MARKER in text:
            print("accent fix: already patched")
            new_text = text
        else:
            new_text = apply_accent(text)

    if new_text == text:
        return
    if crlf:
        new_text = new_text.replace("\n", "\r\n")
    TARGET.write_bytes(new_text.encode("utf-8"))
    print("✅ translate.c patched successfully!")

def apply_accent(text):
    # The one call in TranslateClause that hands the fallback language to SetTranslator2,
    # right after the default-voice fallback.  Whitespace-tolerant.
    pattern = re.compile(
        r"(?P<ind>[ \t]*)switch_phonemes\s*=\s*SetTranslator2\(\s*new_language\s*\)\s*;[ \t]*\n"
    )
    matches = list(pattern.finditer(text))
    # keep only the match(es) that sit right after ESPEAKNG_DEFAULT_VOICE (the clause fallback)
    good = [m for m in matches if "ESPEAKNG_DEFAULT_VOICE" in text[max(0, m.start() - 400):m.start()]]
    if len(good) != 1:
        fail("could not find the single `switch_phonemes = SetTranslator2(new_language);` after "
             "ESPEAKNG_DEFAULT_VOICE in translate.c (found %d). This espeak-ng version changed that "
             "code; the fix needs a small update." % len(good))
    m = good[0]
    ind = m.group("ind")
    block = NEW_BLOCK.format(ind=ind)
    # first line of NEW_BLOCK has no indent because the match already starts with the indent
    new_text = text[:m.start()] + ind + block + text[m.end():]

    # sanity: the symbols the block uses must exist in this version
    for sym in ("SelectPhonemeTableName", "translator_name", "dict_condition", "phoneme_tab_ix"):
        if sym not in new_text:
            fail("symbol `%s` not found in translate.c; this version changed -- fix needs an update." % sym)

    print("accent fix: patched OK (Persian text reads English words with the American accent)")
    return new_text

def apply_flags_only(text):
    # اضافه کردن block جدید برای silent عادی ولی flag فعال
    pattern = re.compile(r"(?P<ind>[ \t]*)if \(\(c == 0xfe0e\) \|\| \(c == 0xfe0f\)\)[ \t]*\n")
    found = list(pattern.finditer(text))
    if len(found) != 1:
        fail("could not find variation-selector skip (0xfe0e / 0xfe0f) in translate.c (found %d). "
             "This espeak-ng version changed that code; the emoji step needs a small update. "
             "(Run without --flags-only to apply only the accent fix.)" % len(found))
    for sym in ("IsEmoji", "IsEmojiModifier", "IsEmojiTag", "prev_out", "next_in", "IsFlagEmoji"):
        if sym not in text:
            fail("symbol `%s` not found in translate.c; the flags-only step needs an update." % sym)
    m = found[0]
    ind = m.group("ind")
    new_text = text[:m.end()] + "\n" + EMOJI_FLAG.format(ind=ind) + "\n" + text[m.end():]
    print("emoji flags-only: patched OK (flags still play tone, others silent)")
    return new_text

if __name__ == "__main__":
    main()
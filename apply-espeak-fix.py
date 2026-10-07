#!/usr/bin/env python3
"""
apply-espeak-fix.py -- gives Persian (fa) text an AMERICAN accent for embedded English words
in espeak-ng, instead of the British one.

Run it from the root of an espeak-ng source tree (the folder that contains `src/`), before building:

    python3 apply-espeak-fix.py

It edits only src/libespeak-ng/translate.c, inside the word-translation code (the place where a word
asks for the fallback language's translator).  When the current voice is Persian ("fa") and the
fallback language is English, it:
  * asks for the real "en" translator (so the English dictionary, abbreviations, acronym
    handling and langopts stay exactly as upstream),
  * switches that translator's phoneme table to "en-us",
  * turns on dictionary rule conditions 3 and 6 (the same ones voices/en-us uses: `dictrules 3 6`).
Every other language keeps upstream behaviour.

With the option `--no-emoji` it ALSO makes Persian text SILENT for emoji.  Without that option emoji
are read exactly as upstream does (so: remove `--no-emoji` from the workflow to get emoji read again).
The `fa_emoji` dictionary file is NOT touched or emptied: in the clause tokenizer, when the voice is Persian, every
emoji character (faces, hearts, flags, skin tones, joiners, tag characters) is turned into a space
before it can reach the dictionary, so nothing is said for it and the words around it stay separate.

It is safe to run again (it says "already patched").  If a new espeak-ng version moved the code so
that the spot can no longer be found, it stops with a clear message and a non-zero exit code, so a
GitHub Actions build fails visibly instead of silently building without the fix.
"""
import re
import sys
from pathlib import Path

TARGET = Path("src/libespeak-ng/translate.c")
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


def main():
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


def apply_emoji(text):
    # In the clause tokenizer, right after the variation-selector skip (U+FE0E / U+FE0F).
    pattern = re.compile(
        r"(?P<ind>[ \t]*)if \(\(c == 0xfe0e\) \|\| \(c == 0xfe0f\)\)[ \t]*\n"
        r"[ \t]*continue;[^\n]*\n(?:[ \t]*//[^\n]*\n)*"
    )
    found = list(pattern.finditer(text))
    if len(found) != 1:
        fail("could not find the variation-selector skip (0xfe0e / 0xfe0f) in translate.c (found %d). "
             "This espeak-ng version changed that code; the emoji step needs a small update. "
             "(Run without --no-emoji to apply only the accent fix.)" % len(found))
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

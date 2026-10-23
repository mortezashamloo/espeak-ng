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

It ALSO makes the build read your own `dictsource/<lang>_extra` files (always on, e.g. `fa_extra`).
The stock CMake data build (used by the Android build) copies only `_rules`, `_list`, `_listx` and
`_emoji` into its temporary dictionary folder, so a `fa_extra` file was silently ignored.  This adds
the missing copy (cmake/data.cmake).  Nothing changes when no `*_extra` file exists.

With the option `--no-emoji` it ALSO adds a Persian emoji switch with three modes:
    all    -- emoji are read exactly as upstream does
    flags  -- only flags are read (country flags, the black/white/chequered/triangular/crossed flags
              and the England/Scotland/Wales flags); every other emoji is silent
    off    -- every emoji is silent (this is the default, same as before)
The mode is read from the environment variable ESPEAK_FA_EMOJI ("all", "flags" or "off") each time an
emoji is met.  On Android the eSpeak app gets a new setting ("Emoji in Persian text", a radio list) that
sets it before every speech; on Windows/Linux you can set the variable yourself.  Without `--no-emoji`
nothing about emoji is touched (so: remove `--no-emoji` from the workflow to get upstream behaviour).
The `fa_emoji` dictionary file is NOT touched or emptied: a silent emoji is turned into a space in the clause
tokenizer before it can reach the dictionary, so nothing is said for it and the neighbouring words stay separate.

It is safe to run again (it says "already patched").  If a new espeak-ng version moved the code so
that the spot can no longer be found, it stops with a clear message and a non-zero exit code, so a
GitHub Actions build fails visibly instead of silently building without the fix.
"""
import re
import sys
from pathlib import Path

TARGET = Path("src/libespeak-ng/translate.c")
CMAKE_DATA = Path("cmake/data.cmake")
MARKER = "Persian (fa): English fallback with American accent"
EMOJI_MARKER = "Persian (fa): emoji mode (ESPEAK_FA_EMOJI"
OLD_EMOJI_MARKER = "Persian (fa): emoji are silent"
EMOJI_HELPER_MARKER = "FaEmojiMode(void)"

EMOJI_HELPERS = """\
// Persian (fa): emoji mode helpers.  Mode: 0 = read all emoji (upstream), 1 = flags only, 2 = silent.
// Chosen at run time by the environment variable ESPEAK_FA_EMOJI ("all" / "flags" / "off"); the Android
// app sets it from its settings.  Unset or unknown: silent.
#ifdef _MSC_VER
#pragma warning(push)
#pragma warning(disable: 4996)
#endif
static int FaEmojiMode(void)
{
\tconst char *v = getenv("ESPEAK_FA_EMOJI");
\tif (v != NULL) {
\t\tif (strcmp(v, "all") == 0)
\t\t\treturn 0;
\t\tif (strcmp(v, "flags") == 0)
\t\t\treturn 1;
\t}
\treturn 2;
}
#ifdef _MSC_VER
#pragma warning(pop)
#endif

// true for the characters that make up a flag: the two letters of a country flag, the plain flag
// symbols, and the tag letters of a subdivision flag (England, Scotland, Wales)
static int FaEmojiIsFlagPart(unsigned int c, int prev_out)
{
\tif (IsRegionalIndicator(c))
\t\treturn 1;
\tif (c == 0x1f3f4 || c == 0x1f3f3 || c == 0x1f3c1 || c == 0x1f6a9 || c == 0x1f38c)
\t\treturn 1;
\tif (IsEmojiTag(c) && (prev_out == 0x1f3f4 || IsEmojiTag(prev_out)))
\t\treturn 1;
\treturn 0;
}

"""

EMOJI_BLOCK = """\
{ind}// Persian (fa): emoji mode (ESPEAK_FA_EMOJI = all / flags / off, default off).  An emoji that must
{ind}// stay silent becomes a space before it can reach the dictionary (fa_emoji stays untouched).
{ind}if (tr->translator_name == L('f', 'a') &&
{ind}    (IsEmoji(c) || IsEmojiModifier(c) || IsEmojiTag(c) ||
{ind}     (c == 0x200d && (IsEmoji(prev_out) || IsEmoji(next_in))))) {{
{ind}\tint fa_emoji_mode = FaEmojiMode();
{ind}\tif (fa_emoji_mode == 2 || (fa_emoji_mode == 1 && !FaEmojiIsFlagPart(c, prev_out)))
{ind}\t\tc = ' ';
{ind}}}

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
        fail("could not find the `_emoji` copy rule in cmake/data.cmake (found %d). This espeak-ng version "
             "changed that file; the *_extra step needs a small update." % len(found))
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


def main():
    patch_extra_dictionary()
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
            print("emoji mode: already patched")
        else:
            new_text = apply_emoji(new_text)
    if new_text != text:
        if crlf:
            new_text = new_text.replace("\n", "\r\n")
        TARGET.write_bytes(new_text.encode("utf-8"))
        print("translate.c written")
    if silence_emoji:
        patch_android_emoji_setting()


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
    # 1) an older version of this script put a plain "emoji are silent" block in; take it out first
    if OLD_EMOJI_MARKER in text:
        old = re.compile(
            r"[ \t]*// " + re.escape(OLD_EMOJI_MARKER) + r"[^\n]*\n(?:[ \t]*//[^\n]*\n)*"
            r"[ \t]*if \(tr->translator_name == L\('f', 'a'\) &&\n"
            r"(?:[^\n]*\n){1,3}?[ \t]*c = ' ';\n\n?"
        )
        text, n = old.subn("", text, count=1)
        if n != 1:
            fail("found an older emoji block in translate.c but could not remove it. Start from a clean "
                 "translate.c (Sync fork) and run again.")
        print("emoji mode: removed the older always-silent block")

    # 2) in the clause tokenizer, right after the variation-selector skip (U+FE0E / U+FE0F)
    pattern = re.compile(
        r"(?P<ind>[ \t]*)if \(\(c == 0xfe0e\) \|\| \(c == 0xfe0f\)\)[ \t]*\n"
        r"[ \t]*continue;[^\n]*\n(?:[ \t]*//[^\n]*\n)*"
    )
    found = list(pattern.finditer(text))
    if len(found) != 1:
        fail("could not find the variation-selector skip (0xfe0e / 0xfe0f) in translate.c (found %d). "
             "This espeak-ng version changed that code; the emoji step needs a small update. "
             "(Run without --no-emoji to apply only the accent fix.)" % len(found))
    for sym in ("IsEmoji", "IsEmojiModifier", "IsEmojiTag", "IsRegionalIndicator", "prev_out", "next_in"):
        if sym not in text:
            fail("symbol `%s` not found in translate.c; the emoji step needs an update." % sym)
    m = found[0]
    ind = m.group("ind")
    new_text = text[:m.end()] + "\n" + EMOJI_BLOCK.format(ind=ind).rstrip("\n") + "\n" + text[m.end():]

    # 3) the two helper functions, right before the function that holds the tokenizer
    if EMOJI_HELPER_MARKER not in new_text:
        anchor = re.compile(r"^void TranslateClauseWithTerminator\(", re.M)
        am = list(anchor.finditer(new_text))
        if len(am) != 1:
            fail("could not find `void TranslateClauseWithTerminator(` in translate.c (found %d). This "
                 "espeak-ng version changed that code; the emoji step needs a small update." % len(am))
        new_text = new_text[:am[0].start()] + EMOJI_HELPERS + new_text[am[0].start():]
    print("emoji mode: patched OK (Persian emoji: all / flags / off through ESPEAK_FA_EMOJI, default off)")
    return new_text


# ---------------------------------------------------------------- Android app setting

ANDROID = Path("android")
EMOJI_PREF_KEY = "espeak_emoji_mode"

STR_EN = """\
  <string name="setting_emoji_mode">Emoji in Persian text</string>
  <string name="emoji_mode_all">Read all emoji</string>
  <string name="emoji_mode_flags">Read only flags</string>
  <string name="emoji_mode_off">Do not read emoji</string>
"""
STR_FA = """\
  <string name="setting_emoji_mode">ایموجی در متن فارسی</string>
  <string name="emoji_mode_all">خواندن همه‌ی ایموجی‌ها</string>
  <string name="emoji_mode_flags">فقط خواندن پرچم‌ها</string>
  <string name="emoji_mode_off">خواندن هیچ ایموجی</string>
"""

PREF_METHOD = """\
    /** Persian emoji mode: all / flags / off (read by libespeak-ng through ESPEAK_FA_EMOJI). */
    private static Preference createEmojiModePreference(Context context) {
        final ListPreference pref = new ListPreference(context);
        pref.setTitle(R.string.setting_emoji_mode);
        pref.setDialogTitle(R.string.setting_emoji_mode);
        pref.setKey(VoiceSettings.PREF_EMOJI_MODE);
        final CharSequence[] entries = new CharSequence[] {
                context.getString(R.string.emoji_mode_all),
                context.getString(R.string.emoji_mode_flags),
                context.getString(R.string.emoji_mode_off)
        };
        final CharSequence[] values = new CharSequence[] { "all", "flags", "off" };
        pref.setEntries(entries);
        pref.setEntryValues(values);
        pref.setDefaultValue("off");
        pref.setPersistent(true);
        pref.setOnPreferenceChangeListener(mOnPreferenceChanged);

        final SharedPreferences prefs = PreferenceManager.getDefaultSharedPreferences(storageContext);
        final String current = prefs.getString(VoiceSettings.PREF_EMOJI_MODE, "off");
        for (int i = 0; i < values.length; i++) {
            if (values[i].equals(current)) {
                pref.setSummary(entries[i]);
            }
        }
        return pref;
    }

"""


def _read(path):
    data = path.read_bytes().decode("utf-8")
    crlf = "\r\n" in data
    return data.replace("\r\n", "\n"), crlf


def _write(path, text, crlf):
    if crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))


def _replace_once(text, old, new, what):
    if text.count(old) != 1:
        fail("Android emoji setting: could not find %s (found %d). This espeak-ng version changed that "
             "file; the Android step needs a small update." % (what, text.count(old)))
    return text.replace(old, new)


def patch_android_emoji_setting():
    """New radio setting in the Android eSpeak app; TtsService hands it to the native code."""
    res_en = ANDROID / "res/values/strings.xml"
    settings_java = ANDROID / "src/com/reecedunn/espeak/TtsSettingsActivity.java"
    voice_java = ANDROID / "src/com/reecedunn/espeak/VoiceSettings.java"
    service_java = ANDROID / "src/com/reecedunn/espeak/TtsService.java"
    for f in (res_en, settings_java, voice_java, service_java):
        if not f.exists():
            print("Android emoji setting: %s not found -- skipped (no Android app in this tree)" % f)
            return

    changed = False

    # strings (English default + Persian)
    for path, block in ((res_en, STR_EN), (ANDROID / "res/values-fa/strings.xml", STR_FA)):
        if not path.exists():
            if path is res_en:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("<?xml version='1.0' encoding='UTF-8'?>\n<resources>\n" + block + "</resources>\n").encode("utf-8"))
            changed = True
            continue
        t, crlf = _read(path)
        if 'name="setting_emoji_mode"' in t:
            continue
        t = _replace_once(t, "</resources>", block + "</resources>", "</resources> in " + str(path))
        _write(path, t, crlf)
        changed = True

    # VoiceSettings: key + getter
    t, crlf = _read(voice_java)
    if "PREF_EMOJI_MODE" not in t:
        anchor = 'public static final String PREF_UNICODE_NORMALIZATION = "espeak_unicode_normalization";\n'
        t = _replace_once(t, anchor, anchor + '    public static final String PREF_EMOJI_MODE = "%s";\n' % EMOJI_PREF_KEY,
                          "PREF_UNICODE_NORMALIZATION in VoiceSettings.java")
        end = t.rstrip().rfind("}")
        if end < 0:
            fail("Android emoji setting: VoiceSettings.java has no closing brace")
        getter = (
            "\n    /** Persian emoji mode: \"all\", \"flags\" or \"off\" (default). */\n"
            "    public String getEmojiMode() {\n"
            "        final String mode = mPreferences.getString(PREF_EMOJI_MODE, \"off\");\n"
            "        return (\"all\".equals(mode) || \"flags\".equals(mode)) ? mode : \"off\";\n"
            "    }\n"
        )
        t = t[:end].rstrip() + "\n" + getter + "}\n"
        _write(voice_java, t, crlf)
        changed = True

    # settings screen: the radio list, right after Unicode normalization
    t, crlf = _read(settings_java)
    if "createEmojiModePreference" not in t:
        m_anchor = "    private static Preference createUnicodeNormalizationPreference(Context context) {\n"
        t = _replace_once(t, m_anchor, PREF_METHOD + m_anchor, "createUnicodeNormalizationPreference")
        add = "        group.addPreference(createUnicodeNormalizationPreference(context));\n"
        t = _replace_once(t, add, add + "        group.addPreference(createEmojiModePreference(context));\n",
                          "the Unicode normalization addPreference line")
        _write(settings_java, t, crlf)
        changed = True

    # speech service: pass the choice to the native code before every speech
    t, crlf = _read(service_java)
    if "ESPEAK_FA_EMOJI" not in t:
        anchor = "        final VoiceSettings settings = new VoiceSettings(PreferenceManager.getDefaultSharedPreferences(storageContext), mEngine);\n"
        hook = (
            "\n        // Persian emoji mode reaches libespeak-ng through the environment (see translate.c)\n"
            "        try {\n"
            "            android.system.Os.setenv(\"ESPEAK_FA_EMOJI\", settings.getEmojiMode(), true);\n"
            "        } catch (Throwable ignored) {\n"
            "        }\n"
        )
        t = _replace_once(t, anchor, anchor + hook, "the VoiceSettings line in TtsService.java")
        _write(service_java, t, crlf)
        changed = True
    if not changed:
        print("Android emoji setting: already patched")
        return
    print("Android emoji setting: patched OK (radio list \"Emoji in Persian text\": all / flags only / off)")


if __name__ == "__main__":
    main()

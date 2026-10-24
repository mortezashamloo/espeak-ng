espeak-ng Persian fixes / اصلاحات espeak-ng برای فارسی
=====================================================

Files / فایل‌ها
- apply-espeak-fix.py                    -> repo root (next to the "src" folder) / ریشهٔ فورک، کنار پوشهٔ src
- .github/workflows/android.yml          -> replaces the same file in the fork / جایگزین فایل هم‌نام
- .github/workflows/windows-msbuild.yml  -> replaces the same file in the fork / جایگزین فایل هم‌نام
- .github/workflows/create-keystore.yml  -> new file, run ONCE by hand / فایل جدید، فقط یک بار دستی اجرا شود

What the script does / اسکریپت چه می‌کند
- English words inside Persian text get the American accent / کلمات انگلیسی در متن فارسی لهجهٔ آمریکایی
- with --no-emoji: emoji are silent in the Persian voice (fa_emoji untouched);
  remove --no-emoji from the workflow to read emoji again / با --no-emoji ایموجی بی‌صدا؛ برای خواندن ایموجی آن را بردار
- dictsource/fa_extra is now compiled by the CMake (Android) build / فایل fa_extra حالا در ساخت اندروید خوانده می‌شود

Signing key (Android) / کلید امضا
1. Create repository secret ESPEAK_KEYSTORE_PASSWORD (20+ characters). Keep a copy outside GitHub.
2. Actions tab -> "Create signing keystore (run once)" -> Run workflow.
3. Download the artifact keystore-base64, copy its text into a new secret ESPEAK_KEYSTORE_BASE64.
   KEEP THE TEXT FILE SAFE before deleting the artifact: GitHub never shows a secret again.
4. Delete the artifact (the fork is public). Do not run the workflow twice.
5. Run the Android workflow; APKs are signed. First install with the new key needs uninstalling the old app once.

Notes / نکات
- Sync fork merges upstream changes; never click "Discard commits".
- Never put the password or the keystore text in a public place.

#!/usr/bin/env python3
"""
remove-espeak-registry.py  --  find (and optionally remove) every eSpeak / eSpeak NG leftover in the Windows registry.

  python remove-espeak-registry.py              -> only LISTS what it found (nothing is changed)
  python remove-espeak-registry.py --delete     -> backs up each key to a .reg file, then deletes it
  python remove-espeak-registry.py --delete --delete-uninstall   -> also removes the "Programs and Features" entries
  python remove-espeak-registry.py --delete --delete-files       -> also removes the eSpeak folders in Program Files

Run it from an Administrator Command Prompt (Python 3.8 on Windows 7 is fine).

What it touches (both the 32-bit and the 64-bit registry views, HKLM and HKCU):
  * SAPI voice tokens   ...\\Microsoft\\Speech\\Voices\\Tokens\\*   whose name / values / engine DLL mention "espeak"
  * COM classes         ...\\Classes\\CLSID\\*                       whose DLL path or name mentions "espeak"
  * top-level keys      SOFTWARE\\eSpeak, SOFTWARE\\eSpeak NG ...
It never touches any other voice (Microsoft Anna, RHVoice, Sapi4 ...), because only keys that mention
"espeak" are selected.  Every deleted key is exported to a .reg backup first (double-click a .reg to restore it).
"""
import argparse
import ctypes
import datetime
import os
import shutil
import subprocess
import sys
import winreg

KNOWN_CLSIDS = {"{61D23633-CE59-4101-8158-569FC6B51B49}"}   # eSpeak NG SAPI5 engine (upstream / install-sapi.bat)
TOKENS = r"SOFTWARE\Microsoft\Speech\Voices\Tokens"
CLSIDS = r"SOFTWARE\Classes\CLSID"
UNINSTALL = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"

IS64 = "ProgramFiles(x86)" in os.environ
if IS64:
    VIEWS = [("64-bit", winreg.KEY_WOW64_64KEY, "/reg:64"), ("32-bit", winreg.KEY_WOW64_32KEY, "/reg:32")]
else:
    VIEWS = [("native", 0, "")]
ROOTS = [("HKLM", winreg.HKEY_LOCAL_MACHINE), ("HKCU", winreg.HKEY_CURRENT_USER)]


def mentions(text):
    return "espeak" in str(text).lower()


def sub_keys(root, path, flag):
    try:
        k = winreg.OpenKey(root, path, 0, winreg.KEY_READ | flag)
    except OSError:
        return []
    names = []
    i = 0
    while True:
        try:
            names.append(winreg.EnumKey(k, i))
            i += 1
        except OSError:
            break
    winreg.CloseKey(k)
    return names


def values(root, path, flag):
    try:
        k = winreg.OpenKey(root, path, 0, winreg.KEY_READ | flag)
    except OSError:
        return {}
    out = {}
    i = 0
    while True:
        try:
            name, val, _ = winreg.EnumValue(k, i)
            out[name] = val
            i += 1
        except OSError:
            break
    winreg.CloseKey(k)
    return out


def default_of(root, path, flag):
    return values(root, path, flag).get("", "")


def find_candidates():
    found = {}   # (rootname, path, viewname) -> (root, flag, exportflag, reason)

    def add(rn, root, path, vn, flag, ef, reason):
        found.setdefault((rn, path.lower(), vn), (rn, root, path, vn, flag, ef, reason))

    for rn, root in ROOTS:
        for vn, flag, ef in VIEWS:
            # 1) SAPI voice tokens
            for name in sub_keys(root, TOKENS, flag):
                p = TOKENS + "\\" + name
                vals = values(root, p, flag)
                attrs = values(root, p + "\\Attributes", flag)
                texts = [name] + [str(v) for v in vals.values()] + [str(v) for v in attrs.values()]
                reason = None
                if any(mentions(t) for t in texts):
                    reason = "voice token mentions eSpeak"
                else:
                    clsid = str(vals.get("CLSID", ""))
                    if clsid:
                        for r2 in (root, winreg.HKEY_LOCAL_MACHINE):
                            dll = default_of(r2, CLSIDS + "\\" + clsid + "\\InprocServer32", flag)
                            if mentions(dll) or clsid.upper() in KNOWN_CLSIDS:
                                reason = "voice uses eSpeak engine (%s)" % (dll or clsid)
                                break
                if reason:
                    add(rn, root, p, vn, flag, ef, reason)
            # 2) COM classes
            for name in sub_keys(root, CLSIDS, flag):
                p = CLSIDS + "\\" + name
                reason = None
                if name.upper() in KNOWN_CLSIDS:
                    reason = "eSpeak NG SAPI5 engine class"
                else:
                    for sub in ("InprocServer32", "LocalServer32"):
                        d = default_of(root, p + "\\" + sub, flag)
                        if mentions(d):
                            reason = "class points to " + str(d)
                            break
                    if not reason and mentions(default_of(root, p, flag)):
                        reason = "class named " + str(default_of(root, p, flag))
                if reason:
                    add(rn, root, p, vn, flag, ef, reason)
            # 3) top-level SOFTWARE\eSpeak ...
            for name in sub_keys(root, "SOFTWARE", flag):
                if mentions(name):
                    add(rn, root, "SOFTWARE\\" + name, vn, flag, ef, "eSpeak settings key")
    return list(found.values())


def find_uninstall():
    out = {}
    for rn, root in ROOTS:
        for vn, flag, ef in VIEWS:
            for name in sub_keys(root, UNINSTALL, flag):
                p = UNINSTALL + "\\" + name
                v = values(root, p, flag)
                if mentions(v.get("DisplayName", "")) or mentions(name):
                    out[(rn, p.lower(), vn)] = (rn, root, p, vn, flag, ef,
                                                "installed program: %s | %s" % (v.get("DisplayName", name), v.get("UninstallString", "")))
    return list(out.values())


def delete_tree(root, path, flag):
    try:
        k = winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS | flag)
    except FileNotFoundError:
        return
    children = []
    i = 0
    while True:
        try:
            children.append(winreg.EnumKey(k, i))
            i += 1
        except OSError:
            break
    winreg.CloseKey(k)
    for c in children:
        delete_tree(root, path + "\\" + c, flag)
    winreg.DeleteKeyEx(root, path, flag, 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delete", action="store_true", help="really delete (default: only list)")
    ap.add_argument("--delete-uninstall", action="store_true", help="also delete 'Programs and Features' entries")
    ap.add_argument("--delete-files", action="store_true", help="also delete eSpeak folders in Program Files")
    args = ap.parse_args()

    try:
        is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        is_admin = False
    if args.delete and not is_admin:
        print("Run this from an ADMINISTRATOR command prompt (right-click cmd.exe -> Run as administrator).")
        return 1

    cands = find_candidates()
    unin = find_uninstall()
    if args.delete_uninstall:
        cands += unin

    print("=== eSpeak keys found: %d ===" % len(cands))
    for rn, root, path, vn, flag, ef, reason in cands:
        print("[%s %s] %s\n      -> %s" % (rn, vn, path, reason))
    if unin and not args.delete_uninstall:
        print("\n=== installed programs that mention eSpeak (NOT deleted; uninstall them in Programs and Features) ===")
        for rn, root, path, vn, flag, ef, reason in unin:
            print("[%s %s] %s" % (rn, vn, reason))

    dirs = []
    for env in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        base = os.environ.get(env)
        if base and os.path.isdir(base):
            for n in os.listdir(base):
                full = os.path.join(base, n)
                if mentions(n) and os.path.isdir(full) and full not in dirs:
                    dirs.append(full)
    if dirs:
        print("\n=== folders ===")
        for d in dirs:
            print(d)

    if not args.delete:
        print("\nNothing was changed. To delete the keys above run again with  --delete")
        return 0

    if not cands and not (args.delete_files and dirs):
        print("Nothing to delete.")
        return 0
    if input("\nType YES to back up and delete everything listed above: ").strip() != "YES":
        print("Cancelled.")
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "espeak-registry-backup-" + stamp)
    os.makedirs(bdir)
    ok = bad = 0
    for n, (rn, root, path, vn, flag, ef, reason) in enumerate(cands, 1):
        full = rn + "\\" + path
        cmd = ["reg", "export", full, os.path.join(bdir, "%03d.reg" % n), "/y"] + ([ef] if ef else [])
        subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            delete_tree(root, path, flag)
            ok += 1
        except OSError as e:
            bad += 1
            print("COULD NOT DELETE [%s %s] %s : %s" % (rn, vn, path, e))
    if args.delete_files:
        for d in dirs:
            shutil.rmtree(d, ignore_errors=True)
            print("folder removed (if not in use):", d)
    print("\nDeleted %d keys, %d failed. Backups: %s" % (ok, bad, bdir))
    if bad:
        print("Keys that fail with 'Access is denied' have damaged permissions: in regedit right-click the key ->"
              " Permissions -> Advanced -> Owner -> change to Administrators, tick 'Replace owner on subcontainers',"
              " give Administrators Full Control, then run this script again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

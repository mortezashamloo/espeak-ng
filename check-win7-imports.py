#!/usr/bin/env python3
"""
check-win7-imports.py <x86|x64> <dest-folder>

Finds the freshly built libespeak-ng.dll of the given architecture under src/windows, makes sure it
can load on Windows 7 (no XAudio2, no UCRT / VC++ runtime DLLs, no api-ms-win-* forwarders, no known
Windows 8+ functions, exports the COM entry points) and copies it to <dest-folder>.
Exits with an error (so the GitHub Actions run turns red) if anything is wrong.
"""
import re
import shutil
import sys
from pathlib import Path

import pefile

arch, dest = sys.argv[1], Path(sys.argv[2])
machine = {"x86": 0x14C, "x64": 0x8664}[arch]

BAD_DLL = re.compile(r"^(xaudio2|vcruntime|msvcp|concrt|ucrtbase|vcomp|api-ms-win-|ext-ms-win-)", re.I)
WIN8_FUNCS = {
    "GetSystemTimePreciseAsFileTime", "SetThreadDescription", "GetThreadDescription",
    "WaitOnAddress", "WakeByAddressSingle", "WakeByAddressAll", "PrefetchVirtualMemory",
    "GetCurrentPackageId", "GetCurrentPackageFamilyName", "SetProcessMitigationPolicy",
    "VirtualAlloc2", "MapViewOfFile3", "GetSystemTimeAsFileTime_PreciseDoesNotExist",
}


def fail(msg):
    print("ERROR: " + msg)
    sys.exit(1)


cands = []
for p in Path("src/windows").rglob("libespeak-ng.dll"):
    try:
        pe = pefile.PE(str(p), fast_load=True)
    except Exception:
        continue
    if pe.FILE_HEADER.Machine == machine:
        cands.append(p)
if not cands:
    fail("no %s libespeak-ng.dll found under src/windows" % arch)
dll = max(cands, key=lambda p: p.stat().st_mtime)
print("checking", dll)

pe = pefile.PE(str(dll))
pe.parse_data_directories()

problems = []
dlls = []
for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
    name = entry.dll.decode("ascii", "replace")
    dlls.append(name)
    if BAD_DLL.search(name):
        problems.append("imports %s (not available on a clean Windows 7)" % name)
    for imp in entry.imports:
        if imp.name and imp.name.decode("ascii", "replace") in WIN8_FUNCS:
            problems.append("uses Windows 8+ function %s from %s" % (imp.name.decode(), name))
print("imports:", ", ".join(sorted(set(d.lower() for d in dlls))))

exports = {s.name.decode() for s in pe.DIRECTORY_ENTRY_EXPORT.symbols if s.name}
for need in ("DllGetClassObject", "DllCanUnloadNow", "espeak_ng_Initialize"):
    if need not in exports:
        problems.append("missing export %s" % need)

osv = (pe.OPTIONAL_HEADER.MajorSubsystemVersion, pe.OPTIONAL_HEADER.MinorSubsystemVersion)
print("subsystem version: %d.%d" % osv)
if osv > (6, 1):
    problems.append("subsystem version %d.%d is newer than Windows 7 (6.1)" % osv)

if problems:
    for p in problems:
        print("  - " + p)
    fail("this DLL would not work on Windows 7")

dest.mkdir(parents=True, exist_ok=True)
shutil.copy2(dll, dest / "libespeak-ng.dll")
print("OK: Windows 7 compatible, copied to", dest / "libespeak-ng.dll")

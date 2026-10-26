@echo off
rem Fix DB ACLs and attributes for repository DB (cthulu.db / Cthulu.db)
set OUT=_fix_db_acl.out
echo Fixing ACLs and attributes > %OUT%

echo Taking ownership of ct*hulu.db >> %OUT% 2>&1
if exist ct.hulu db (echo skipping) else (echo)

REM takeown and icacls (try both lower and upper case names if present)
if exist ct.hulu.db (
  takeown /f "cthulu.db" /a >> %OUT% 2>&1
  icacls "cthulu.db" /grant "%USERNAME%:(M)" /C >> %OUT% 2>&1
  icacls "cthulu.db" /grant "Administrators:(F)" /C >> %OUT% 2>&1
  icacls "cthulu.db" /grant "SYSTEM:(F)" /C >> %OUT% 2>&1
  attrib -R "cthulu.db" >> %OUT% 2>&1
) else (echo ct hulu db not found >> %OUT% 2>&1)

if exist Cthulu.db (
  takeown /f "Cthulu.db" /a >> %OUT% 2>&1
  icacls "Cthulu.db" /grant "%USERNAME%:(M)" /C >> %OUT% 2>&1
  icacls "Cthulu.db" /grant "Administrators:(F)" /C >> %OUT% 2>&1
  icacls "Cthulu.db" /grant "SYSTEM:(F)" /C >> %OUT% 2>&1
  attrib -R "Cthulu.db" >> %OUT% 2>&1
) else (echo Cthulu.db not found >> %OUT% 2>&1)

REM Fix directory ACLs recursively (safe: grant current user modify)
icacls "." /grant "%USERNAME%:(OI)(CI)(M)" /C >> %OUT% 2>&1

REM Show final ACL for db files
if exist ct hulu.db (icacls "cthulu.db" >> %OUT% 2>&1)
if exist Cthulu.db (icacls "Cthulu.db" >> %OUT% 2>&1)

echo Done >> %OUT%
exit /b 0

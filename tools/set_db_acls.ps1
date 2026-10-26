<#
SetDBACLs.ps1
Grant the current user Modify permissions to the Cthulu DB and project folder.
Usage: .\tools\set_db_acls.ps1 -DbPath .\cthulu.db -User "DOMAIN\\User"
#>
param(
    [string]$DbPath = '.\cthulu.db',
    [string]$User = "$env:USERNAME",
    [switch]$Verbose
)

function Exec($cmd) {
    if ($Verbose) { Write-Host "> $cmd" -ForegroundColor Cyan }
    $r = cmd /c $cmd
    return $r
}

$fullDb = Resolve-Path $DbPath
Write-Host "Ensuring ownership and ACLs for: $fullDb" -ForegroundColor Green

# Take ownership as Administrators
Exec "takeown /f `"$($fullDb)`" /a"
# Grant Modify to the specified user
Exec "icacls `"$($fullDb)`" /grant `"$User:(M)`" /C"
# Grant Modify to project folder recursively
Exec "icacls `"$PWD\`" /grant `"$User:(OI)(CI)(M)`" /C"
# Remove readonly attribute
Exec "attrib -R `"$($fullDb)`""

Write-Host "ACL adjustments complete. Verify with: icacls $fullDb" -ForegroundColor Green

<#
.SYNOPSIS
  Bulk-export SolidWorks parts/assemblies to STEP for gitcad import.

.DESCRIPTION
  SolidWorks files (.sldprt/.sldasm) are a proprietary binary format wrapping
  Parasolid geometry — no open-source library can read them. But SolidWorks
  itself translates perfectly. This script drives your installed SolidWorks
  via COM to convert an entire folder tree to STEP, which gitcad imports at
  full geometric fidelity (model_import / import_step_file).

  Parametric feature history is not preserved — that is true of every
  SolidWorks translation path, commercial ones included.

.REQUIREMENTS
  A licensed SolidWorks installation on this machine (any recent version).

.USAGE
  powershell -File scripts/sw-batch-export.ps1 -Source C:\my\parts -Dest C:\my\step
#>
param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Dest
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force $Dest | Out-Null

Write-Host "Starting SolidWorks (this can take a moment)..."
$sw = New-Object -ComObject "SldWorks.Application"
$sw.Visible = $false
# swDocPART = 1, swDocASSEMBLY = 2; open silently, read-only
$openOpts = 128  # swOpenDocOptions_Silent

$files = Get-ChildItem -Path $Source -Recurse -Include *.sldprt, *.sldasm
$done = 0; $failed = @()
foreach ($f in $files) {
    $docType = if ($f.Extension -ieq ".sldprt") { 1 } else { 2 }
    $errors = 0; $warnings = 0
    try {
        $doc = $sw.OpenDoc6($f.FullName, $docType, $openOpts, "", [ref]$errors, [ref]$warnings)
        if ($null -eq $doc) { throw "OpenDoc6 returned null (errors=$errors)" }
        $rel = [System.IO.Path]::GetRelativePath($Source, $f.FullName)
        $out = Join-Path $Dest ([System.IO.Path]::ChangeExtension($rel, ".step"))
        New-Item -ItemType Directory -Force (Split-Path $out) | Out-Null
        # SaveAs to .step uses the STEP AP214 translator by extension
        $ok = $doc.SaveAs3($out, 0, 0)
        $sw.CloseDoc($doc.GetTitle())
        if (-not $ok) { throw "SaveAs3 returned false" }
        $done++
        Write-Host ("  ok   {0}" -f $rel)
    } catch {
        $failed += $f.FullName
        Write-Host ("  FAIL {0}: {1}" -f $f.FullName, $_.Exception.Message)
    }
}
$sw.ExitApp() | Out-Null
Write-Host ""
Write-Host ("Exported {0}/{1} files to {2}" -f $done, $files.Count, $Dest)
if ($failed.Count -gt 0) {
    Write-Host "Failed files:"; $failed | ForEach-Object { Write-Host "  $_" }
    exit 1
}
Write-Host "Next: import into gitcad with model_import(path) per STEP file."

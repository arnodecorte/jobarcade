# build.ps1 — compile one application's CV + motivation letter from Typst.
# Usage:  ./Base/build.ps1 -App "Paramount-Content-Coordinator"
# Exits non-zero (loud) if a guard-rail assertion trips, so an agent can read
# the message, fix the YAML, and recompile until it passes.
param([Parameter(Mandatory)][string]$App)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent           # workspace root
$appDir = Join-Path $root "Applications\$App"
if (-not (Test-Path $appDir)) { throw "No application folder: $appDir" }
$themeRel = $null
$fontPaths = @()
$themePath = Join-Path $appDir "brand-theme.yaml"
if (Test-Path $themePath) {
  try {
    $themeText = Get-Content -Raw $themePath
    if ($themeText -match "(?m)^\s*enabled:\s*true\s*$" -and $themeText -notmatch "(?m)^\s*fallback:\s*true\s*$") {
      $themeRel = "/Applications/$App/brand-theme.yaml"
      if ($themeText -match "(?m)^\s*typography_enabled:\s*true\s*$") {
        foreach ($m in [regex]::Matches($themeText, "(?m)^\s*font_path:\s*([^\r\n]+)\s*$")) {
          $fontRel = $m.Groups[1].Value.Trim().Trim("'`"")
          if (-not $fontRel) { continue }
          $candidate = Join-Path $root $fontRel
          if (Test-Path $candidate) {
            if ($fontPaths -notcontains $candidate) { $fontPaths += $candidate }
          } else {
            Write-Warning "Chameleon typography is enabled but font path '$fontRel' is missing; skipping it."
          }
        }
      }
    } elseif ($themeText -match "(?m)^\s*enabled:\s*true\s*$") {
      Write-Warning "brand-theme.yaml is enabled but marked fallback; using the base theme."
    }
  } catch {
    Write-Warning "Could not read brand-theme.yaml; using the base theme."
  }
}

# Locate typst (PATH may not be refreshed in a fresh shell after winget install).
$typst = (Get-Command typst -EA SilentlyContinue).Source
if (-not $typst) {
  $typst = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse `
    -Filter typst.exe -EA SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $typst) { throw "typst not found. Install: winget install Typst.Typst" }

$jobs = @(
  @{ tpl = "cv.typ";     data = "cv-data.yaml";     out = "cv.pdf" },
  @{ tpl = "letter.typ"; data = "letter-data.yaml"; out = "motivation-letter.pdf" }
)

foreach ($j in $jobs) {
  $dataRel = "/Applications/$App/$($j.data)"       # root-relative for yaml()
  $outPath = Join-Path $appDir $j.out
  Write-Host "Compiling $($j.tpl) -> $($j.out)" -ForegroundColor Cyan
  $fontArgs = @()
  foreach ($p in $fontPaths) { $fontArgs += @("--font-path", $p) }
  if ($themeRel) {
    & $typst compile --root $root @fontArgs (Join-Path $PSScriptRoot $j.tpl) $outPath --input "data=$dataRel" --input "theme=$themeRel"
  } else {
    & $typst compile --root $root @fontArgs (Join-Path $PSScriptRoot $j.tpl) $outPath --input "data=$dataRel"
  }
  if ($LASTEXITCODE -ne 0) { throw "BUILD FAILED on $($j.tpl) — fix $($j.data) and retry." }
}
Write-Host "OK — $App built." -ForegroundColor Green

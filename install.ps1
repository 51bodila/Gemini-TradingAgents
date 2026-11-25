# gemini-desk installer for Windows PowerShell 5.1 and PowerShell 7.
# Like pipx: every tool gets its own environment, because their dependencies clash
# (ai-hedge-fund pins langchain-core<0.4, Vibe-Trading needs langchain-core>=1.0).
#   .venv          gemini-desk + google-adk
#   .tools\vibe    vibe-trading-ai 0.1.19
#   .tools\aihf    aihf 2.7.2 (optional: -WithHedgeFund)
#   WSL            TradingAgents 1.0.1 (Linux/macOS builds only)
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -WithHedgeFund
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -DryRun        (print every command, run nothing)
param([switch]$DryRun, [switch]$WithHedgeFund)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Step([string]$text) { Write-Host ""; Write-Host $text -ForegroundColor Cyan }

function Invoke-Cmd([string]$exe, [string[]]$arguments) {
    Write-Host ("  > " + $exe + " " + ($arguments -join " "))
    if ($DryRun) { return }
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $exe $($arguments -join ' ')" }
}

function Invoke-Optional([string]$what, [scriptblock]$block) {
    try { & $block } catch { Write-Host "  $what failed: $($_.Exception.Message)" -ForegroundColor Yellow; Write-Host "  Continuing without it." -ForegroundColor Yellow }
}

function Find-Python {
    # py launcher first (3.12, 3.11, 3.13), then python on PATH. Returns the full path of python.exe.
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in @("3.12", "3.11", "3.13")) {
            $exe = & py "-$v" "-c" "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe) { return ([string]$exe).Trim() }
        }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) {
        $ok = & $cmd.Source "-c" "import sys; print(int((3,11) <= sys.version_info[:2] < (3,14)))" 2>$null
        if ($ok -eq "1") { return $cmd.Source }
    }
    throw "Python 3.11, 3.12 or 3.13 not found. Install it from python.org and run this script again."
}

function New-Venv([string]$dir) {
    $py = Join-Path $PSScriptRoot "$dir\Scripts\python.exe"
    if (Test-Path $py) { Write-Host "  $dir already exists" } else { Invoke-Cmd $python @("-m", "venv", $dir) }
    return $py
}

Step "[1/6] Finding Python 3.11-3.13"
$python = Find-Python
Write-Host "  using $python"

Step "[2/6] .venv: gemini-desk + google-adk"
$venvPy = New-Venv ".venv"
Invoke-Cmd $venvPy @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Cmd $venvPy @("-m", "pip", "install", "-e", ".")

Step "[3/6] .tools\vibe: Vibe-Trading 0.1.19 (a few minutes)"
$vibePy = New-Venv ".tools\vibe"
Invoke-Cmd $vibePy @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Cmd $vibePy @("-m", "pip", "install", "vibe-trading-ai==0.1.19")

Step "[4/6] .tools\aihf: ai-hedge-fund 2.7.2 (optional)"
if ($WithHedgeFund) {
    Invoke-Optional "ai-hedge-fund install" {
        $aihfPy = New-Venv ".tools\aihf"
        Invoke-Cmd $aihfPy @("-m", "pip", "install", "aihf==2.7.2")
        Invoke-Cmd $aihfPy @("tools\patch_aihf_models.py")
    }
} else {
    Write-Host "  skipped (needs a paid data key). Add it later: .\install.ps1 -WithHedgeFund"
}

Step "[5/6] TradingAgents 1.0.1 (needs WSL on Windows)"
$distros = ""
if (Get-Command wsl -ErrorAction SilentlyContinue) {
    $env:WSL_UTF8 = "1"
    $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"   # wsl writes "no distribution" to stderr
    try { $distros = ((wsl -l -q 2>$null) -join "").Trim([char]0, " ", "`r", "`n") } catch { $distros = "" }
    if ($LASTEXITCODE -ne 0) { $distros = "" }
    $ErrorActionPreference = $prev
}
if ($distros) {
    Invoke-Optional "TradingAgents install" { Invoke-Cmd "wsl" @("-e", "bash", "-lc", "curl -fsSL https://tauric.ai/tradingagents/install.sh | sh -s -- 1.0.1") }
} else {
    Write-Host "  WSL has no Linux yet. To add TradingAgents later, run once as administrator:  wsl --install"
    Write-Host "  then reboot and run this installer again. Until then the Neon step goes straight to Gemini."
}

Step "[6/6] Settings file"
if (Test-Path .env) { Write-Host "  .env already exists (your key stays)" } elseif ($DryRun) { Write-Host "  > copy .env.example .env" } else { Copy-Item .env.example .env; Write-Host "  created .env - put your GEMINI_API_KEY in it" }

Step "Done."
Write-Host "  Check:  .\.venv\Scripts\gemini-desk.exe doctor"
Write-Host "  Run:    .\.venv\Scripts\gemini-desk.exe AAPL"

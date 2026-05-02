$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$WebDir = Join-Path $RepoRoot "web"
$VenvDir = Join-Path $RepoRoot ".venv"
$CacheDir = Join-Path $RepoRoot ".webcalyzer-launcher"
$HostName = if ($env:WEBCALYZER_HOST) { $env:WEBCALYZER_HOST } else { "127.0.0.1" }
$Port = if ($env:WEBCALYZER_PORT) { $env:WEBCALYZER_PORT } else { "8765" }
$Url = "http://${HostName}:${Port}"
$FingerprintScript = Join-Path $RepoRoot "scripts\launcher_fingerprint.py"

function Write-LauncherLog {
    param([string] $Message)
    Write-Host "[webcalyzer-launcher] $Message"
}

function Stop-WithMessage {
    param([string] $Message)
    Write-Host ""
    Write-Host "[webcalyzer-launcher] ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Test-PythonCandidate {
    param(
        [string] $Command,
        [string[]] $Arguments
    )
    if (-not $Command) {
        return $false
    }
    try {
        & $Command @Arguments -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Get-PythonCandidate {
    $Candidates = @()
    if ($env:PYTHON) {
        $Candidates += @{ Command = $env:PYTHON; Arguments = @() }
    }
    $Candidates += @{ Command = "python"; Arguments = @() }
    $Candidates += @{ Command = "python3"; Arguments = @() }
    $Candidates += @{ Command = "py"; Arguments = @("-3.11") }
    $Candidates += @{ Command = "py"; Arguments = @("-3") }

    foreach ($Candidate in $Candidates) {
        if (Test-PythonCandidate -Command $Candidate.Command -Arguments $Candidate.Arguments) {
            return $Candidate
        }
    }
    return $null
}

function Invoke-CandidatePython {
    param(
        [hashtable] $Candidate,
        [string[]] $Arguments
    )
    & $Candidate.Command @($Candidate.Arguments + $Arguments)
}

function Get-Fingerprint {
    param([string] $Name)
    return (& $VenvPython $FingerprintScript $Name $RepoRoot).Trim()
}

function Test-CacheMatch {
    param(
        [string] $Name,
        [string] $Value
    )
    $CacheFile = Join-Path $CacheDir "$Name.sha256"
    return (Test-Path $CacheFile) -and ((Get-Content $CacheFile -Raw).Trim() -eq $Value)
}

function Write-Cache {
    param(
        [string] $Name,
        [string] $Value
    )
    Set-Content -Path (Join-Path $CacheDir "$Name.sha256") -Value $Value -Encoding utf8
}

function Test-PythonImports {
    try {
        & $VenvPython -c "import fastapi, uvicorn, webcalyzer" *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Get-ModernNodeDir {
    $Candidates = @()
    $NodeCommand = Get-Command node -ErrorAction SilentlyContinue
    if ($NodeCommand) {
        $Candidates += $NodeCommand.Source
    }
    $Candidates += @(
        "$env:ProgramFiles\nodejs\node.exe",
        "${env:ProgramFiles(x86)}\nodejs\node.exe",
        "$env:LOCALAPPDATA\Programs\nodejs\node.exe"
    )

    foreach ($Candidate in ($Candidates | Where-Object { $_ } | Select-Object -Unique)) {
        if (-not (Test-Path $Candidate)) {
            continue
        }
        try {
            & $Candidate -e "const major = Number(process.versions.node.split('.')[0]); process.exit(major >= 18 ? 0 : 1)" *> $null
            if ($LASTEXITCODE -eq 0) {
                return Split-Path -Parent $Candidate
            }
        } catch {
        }
    }
    return $null
}

function Invoke-Npm {
    param([string[]] $Arguments)
    $NodeDir = Get-ModernNodeDir
    if (-not $NodeDir) {
        Stop-WithMessage "Node.js 18 or newer was not found. Install Node.js first, then rerun this launcher."
    }

    $OldPath = $env:PATH
    $env:PATH = "$NodeDir;$OldPath"
    Push-Location $WebDir
    try {
        & npm @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "npm failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
        $env:PATH = $OldPath
    }
}

Set-Location $RepoRoot
New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null

$PythonCandidate = Get-PythonCandidate
if (-not $PythonCandidate) {
    Stop-WithMessage "Python 3.11 or newer was not found. Install Python first, then rerun this launcher."
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-LauncherLog "Creating local Python environment at .venv"
    Invoke-CandidatePython -Candidate $PythonCandidate -Arguments @("-m", "venv", $VenvDir)
    if ($LASTEXITCODE -ne 0) {
        Stop-WithMessage "Could not create .venv."
    }
}

$PythonFingerprint = Get-Fingerprint "python"
if ((-not (Test-CacheMatch "python" $PythonFingerprint)) -or (-not (Test-PythonImports))) {
    Write-LauncherLog "Installing Python package into .venv"
    & $VenvPython -m pip install -e $RepoRoot
    if ($LASTEXITCODE -ne 0) {
        Stop-WithMessage "Python dependency install failed. Check your internet connection for first-time setup."
    }
    Write-Cache "python" $PythonFingerprint
} else {
    Write-LauncherLog "Python environment is up to date"
}

$FrontendDepsFingerprint = Get-Fingerprint "frontend-deps"
if ((-not (Test-CacheMatch "frontend-deps" $FrontendDepsFingerprint)) -or (-not (Test-Path (Join-Path $WebDir "node_modules")))) {
    Write-LauncherLog "Installing frontend dependencies"
    if (Test-Path (Join-Path $WebDir "package-lock.json")) {
        Invoke-Npm @("ci")
    } else {
        Invoke-Npm @("install")
    }
    Write-Cache "frontend-deps" $FrontendDepsFingerprint
} else {
    Write-LauncherLog "Frontend dependencies are up to date"
}

$FrontendBuildFingerprint = Get-Fingerprint "frontend-build"
if ((-not (Test-CacheMatch "frontend-build" $FrontendBuildFingerprint)) -or (-not (Test-Path (Join-Path $WebDir "dist\index.html")))) {
    Write-LauncherLog "Building frontend bundle"
    Invoke-Npm @("run", "build")
    Write-Cache "frontend-build" $FrontendBuildFingerprint
} else {
    Write-LauncherLog "Frontend bundle is up to date"
}

Write-LauncherLog "Launching webcalyzer at $Url"
Write-LauncherLog "Press Control-C in this terminal to stop the server."

$ReadyJob = Start-Job -ScriptBlock {
    param([string] $ProbeUrl, [string] $BrowserUrl)
    for ($i = 0; $i -lt 90; $i++) {
        try {
            $Response = Invoke-WebRequest -UseBasicParsing -Uri $ProbeUrl -TimeoutSec 1
            if ($Response.StatusCode -eq 200) {
                Start-Process $BrowserUrl
                break
            }
        } catch {
        }
        Start-Sleep -Seconds 1
    }
} -ArgumentList "$Url/api/meta", $Url

try {
    & $VenvPython -m webcalyzer serve --host $HostName --port $Port --root $RepoRoot --templates-dir (Join-Path $RepoRoot "configs")
    $ExitCode = $LASTEXITCODE
} finally {
    if ($ReadyJob.State -eq "Running") {
        Stop-Job $ReadyJob | Out-Null
    }
    Remove-Job $ReadyJob -Force | Out-Null
}

exit $ExitCode

<#
Install a patched local version of gh-secrets-migrator as a GitHub CLI extension.

Supports:
- Using the current checkout (default)
- Cloning a specific repo URL + branch and installing from that clone

Examples:
  pwsh -File ./script/install-local-extension.ps1
  pwsh -File ./script/install-local-extension.ps1 -Clone -RepoUrl https://github.com/im-open/gh-secrets-migrator.git -Branch fix-pygithub-issue-3021
#>

[CmdletBinding()]
param(
    [switch]$Clone,
    [switch]$UseCurrent = $true,
    [string]$RepoUrl = "https://github.com/im-open/gh-secrets-migrator.git",
    [string]$Branch = "fix-pygithub-issue-3021",
    [string]$Workdir = $env:TEMP
)

$ErrorActionPreference = "Stop"

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

Require-Command gh
Require-Command git
Require-Command python
Require-Command make

if ($Clone) {
    $UseCurrent = $false
}

if ($UseCurrent) {
    $RepoDir = (Get-Location).Path
    Write-Host "Using current checkout: $RepoDir"
}
else {
    if (-not (Test-Path $Workdir)) {
        New-Item -ItemType Directory -Path $Workdir | Out-Null
    }

    $RepoDir = Join-Path $Workdir "gh-secrets-migrator-$Branch"
    if (Test-Path $RepoDir) {
        Remove-Item -Recurse -Force $RepoDir
    }

    Write-Host "Cloning $RepoUrl (branch: $Branch) into $RepoDir"
    git clone --depth 1 --single-branch --branch $Branch $RepoUrl $RepoDir
}

Set-Location $RepoDir

$PythonBin = "python"
if (Test-Path "venv/Scripts/python.exe") {
    $PythonBin = "venv/Scripts/python.exe"
    Write-Host "Using existing venv interpreter: $PythonBin"
}
elseif (Test-Path "venv/bin/python") {
    $PythonBin = "venv/bin/python"
    Write-Host "Using existing venv interpreter: $PythonBin"
}
else {
    Write-Host "No venv found, using default interpreter: $PythonBin"
}

& $PythonBin -m pip install -r requirements.txt
make build

Write-Host "Removing old extension install if present..."
try {
    gh extension remove secrets-migrator | Out-Null
}
catch {
}

Write-Host "Installing patched extension from local checkout..."
gh extension install .

Write-Host ""
Write-Host "Installed extension version:"
try {
    gh extension list | Select-String "secrets-migrator"
}
catch {
}

Write-Host ""
Write-Host "Smoke test:"
gh secrets-migrator --help

Write-Host ""
Write-Host "Done. Patched extension installed from: $RepoDir"

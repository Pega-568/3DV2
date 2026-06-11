param(
    [Parameter(Mandatory=$true)][string]$input_image,
    [Parameter(Mandatory=$true)][string]$output_dir,
    [Parameter(Mandatory=$true)][string]$job_id,
    [Parameter(Mandatory=$true)][string]$version_id,
    [string]$engine_root = ""
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

function Resolve-ConfiguredPath {
    param([string]$Value, [string]$BaseDir)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ""
    }
    $expanded = [Environment]::ExpandEnvironmentVariables($Value.Trim())
    if ([System.IO.Path]::IsPathRooted($expanded)) {
        return $expanded
    }
    return (Join-Path $BaseDir $expanded)
}

function Load-LocalConfig {
    param([string]$RepoRoot)
    $configPath = Join-Path $RepoRoot "hy3d_local_config.json"
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
        return @{}
    }
    try {
        $json = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
        $table = @{}
        $json.PSObject.Properties | ForEach-Object { $table[$_.Name] = [string]$_.Value }
        return $table
    } catch {
        return @{}
    }
}

function Resolve-EngineRoot {
    param([string]$RepoRoot, [hashtable]$Config, [string]$ExplicitEngineRoot)
    if (-not [string]::IsNullOrWhiteSpace($ExplicitEngineRoot)) {
        return Resolve-ConfiguredPath $ExplicitEngineRoot $RepoRoot
    }
    if (-not [string]::IsNullOrWhiteSpace($env:HY3D_ENGINE_ROOT)) {
        return Resolve-ConfiguredPath $env:HY3D_ENGINE_ROOT $RepoRoot
    }
    foreach ($key in @("HY3D_ENGINE_ROOT", "engine_root")) {
        if ($Config.ContainsKey($key)) {
            return Resolve-ConfiguredPath $Config[$key] $RepoRoot
        }
    }
    $candidates = @(
        (Join-Path (Split-Path $RepoRoot -Parent) "3D_ENGINES\triposr-local"),
        (Join-Path $RepoRoot "external_engines\triposr-local"),
        (Join-Path $RepoRoot "engines\triposr-local")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Container) {
            return $candidate
        }
    }
    return $candidates[1]
}

function Write-RunReport {
    param([string]$Path, [hashtable]$Payload)
    $Payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Path -Encoding UTF8
}

$repoRoot = Resolve-RepoRoot
$config = Load-LocalConfig $repoRoot
$resolvedEngineRoot = Resolve-EngineRoot $repoRoot $config $engine_root
$resolvedOutputDir = Resolve-ConfiguredPath $output_dir $repoRoot
$resolvedInputImage = Resolve-ConfiguredPath $input_image $repoRoot

New-Item -ItemType Directory -Force -Path $resolvedOutputDir | Out-Null
$runReportPath = Join-Path $resolvedOutputDir "run_report.json"
$rawDir = Join-Path $resolvedOutputDir "engine_raw\0"
New-Item -ItemType Directory -Force -Path $rawDir | Out-Null

$pythonExe = Join-Path $resolvedEngineRoot ".venv\Scripts\python.exe"
$triposrRun = Join-Path $resolvedEngineRoot "TripoSR\run.py"
$meshPath = Join-Path $rawDir "mesh.glb"
$modelPath = Join-Path $resolvedOutputDir "model.glb"
$manifestPath = Join-Path $resolvedOutputDir "result_manifest.json"
$zipPath = Join-Path $resolvedOutputDir "result_package.zip"

$startedAt = (Get-Date).ToUniversalTime().ToString("o")
try {
    if (-not (Test-Path -LiteralPath $resolvedInputImage -PathType Leaf)) {
        throw "Input image does not exist: $resolvedInputImage"
    }
    if (-not (Test-Path -LiteralPath $resolvedEngineRoot -PathType Container)) {
        throw "HY3D_ENGINE_ROOT is not available: $resolvedEngineRoot"
    }
    if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
        throw "TripoSR venv python is missing: $pythonExe"
    }
    if (-not (Test-Path -LiteralPath $triposrRun -PathType Leaf)) {
        throw "TripoSR run.py is missing: $triposrRun"
    }

    Push-Location (Split-Path $triposrRun -Parent)
    try {
        & $pythonExe $triposrRun $resolvedInputImage --output-dir $rawDir --device cpu --model-save-format glb
        if ($LASTEXITCODE -ne 0) {
            & $pythonExe $triposrRun $resolvedInputImage --output-dir $rawDir --device cpu
        }
    } finally {
        Pop-Location
    }

    $foundMesh = Get-ChildItem -LiteralPath $rawDir -Recurse -File -Filter "*.glb" | Select-Object -First 1
    if ($null -eq $foundMesh) {
        throw "TripoSR did not produce a GLB under $rawDir"
    }
    Copy-Item -LiteralPath $foundMesh.FullName -Destination $meshPath -Force
    Copy-Item -LiteralPath $meshPath -Destination $modelPath -Force

    $manifest = @{
        result_package_version = 1
        engine_id = "triposr_local"
        job_id = $job_id
        version_id = $version_id
        candidate_path = "model.glb"
        source_image = $resolvedInputImage
        created_at = (Get-Date).ToUniversalTime().ToString("o")
    }
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

    if (Test-Path -LiteralPath $zipPath -PathType Leaf) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    Compress-Archive -LiteralPath $manifestPath, $modelPath -DestinationPath $zipPath -Force

    Write-RunReport $runReportPath @{
        success = $true
        status = "completed"
        job_id = $job_id
        version_id = $version_id
        repo_root = $repoRoot
        engine_root = $resolvedEngineRoot
        input_image = $resolvedInputImage
        output_dir = $resolvedOutputDir
        output_glb = $modelPath
        result_package = $zipPath
        started_at = $startedAt
        finished_at = (Get-Date).ToUniversalTime().ToString("o")
        error = $null
    }
    exit 0
} catch {
    Write-RunReport $runReportPath @{
        success = $false
        status = "failed"
        job_id = $job_id
        version_id = $version_id
        repo_root = $repoRoot
        engine_root = $resolvedEngineRoot
        input_image = $resolvedInputImage
        output_dir = $resolvedOutputDir
        result_package = ""
        started_at = $startedAt
        finished_at = (Get-Date).ToUniversalTime().ToString("o")
        error = $_.Exception.Message
    }
    Write-Error $_.Exception.Message
    exit 1
}

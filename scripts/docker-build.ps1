<#
.SYNOPSIS
  Build the Estima3D backend and frontend images together from this checkout.

.DESCRIPTION
  Both images get the same SOURCE_REVISION (the commit) and BUILD_ID (the short
  commit, or "<short>-dirty-<UTC time>" when tracked files differ from it), and
  are tagged :<BUILD_ID> and :current. `docker compose up -d` then runs :current.
  See docs/DOCKER.md.

.EXAMPLE
  .\scripts\docker-build.ps1
  .\scripts\docker-build.ps1 -Up      # build, then (re)start the stack
#>
param([switch]$Up)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $revision = (git rev-parse HEAD).Trim()
    $short = $revision.Substring(0, 7)
    # Tracked changes only: untracked runtime files are outside the build context.
    $dirty = git status --porcelain --untracked-files=no -- backend frontend docker-compose.yml
    $buildId = if ($dirty) { "$short-dirty-$((Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss'))" } else { $short }

    $env:SOURCE_REVISION = $revision
    $env:BUILD_ID = $buildId
    $env:IMAGE_TAG = "current"
    Write-Host "Building estima3d-api and estima3d-web: revision $revision, build $buildId"
    docker compose build backend frontend
    if ($LASTEXITCODE -ne 0) { throw "docker compose build failed ($LASTEXITCODE)" }
    if ($Up) {
        docker compose up -d
        if ($LASTEXITCODE -ne 0) { throw "docker compose up failed ($LASTEXITCODE)" }
    }
    Write-Host "Built $buildId. Images: estima3d-api:$buildId, estima3d-web:$buildId (also :current)."
}
finally {
    Remove-Item Env:SOURCE_REVISION, Env:BUILD_ID, Env:IMAGE_TAG -ErrorAction SilentlyContinue
    Pop-Location
}

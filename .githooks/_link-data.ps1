# Link data/ of a worktree to the one in the main worktree, so that every worktree reads and writes the same task data.
# Failures only print a warning: the checkout itself must not fail because of this.
$ErrorActionPreference = 'Stop'

try {
    $commonGit = git rev-parse --path-format=absolute --git-common-dir
    $primaryRoot = [System.IO.Path]::GetFullPath((Split-Path $commonGit -Parent))
    $worktreeRoot = [System.IO.Path]::GetFullPath((git rev-parse --show-toplevel))

    # PowerShell compares strings case-insensitively, which matches Windows paths.
    if ($worktreeRoot.TrimEnd('\') -eq $primaryRoot.TrimEnd('\')) {
        exit 0
    }

    $target = Join-Path $primaryRoot 'data'
    $link = Join-Path $worktreeRoot 'data'

    # Get-Item also finds a dangling link, which Test-Path does not.
    if (Get-Item -LiteralPath $link -Force -ErrorAction SilentlyContinue) {
        exit 0
    }
    # Create data/ in the main worktree first, so that a worktree never gets its own data/.
    if (-not (Test-Path -LiteralPath $target -PathType Container)) {
        New-Item -ItemType Directory -Path $target | Out-Null
    }

    # A junction (not a symbolic link) needs neither Developer Mode nor administrator rights.
    New-Item -ItemType Junction -Path $link -Target $target | Out-Null
    Write-Host "[link-data] Linked $link -> $target"
}
catch {
    Write-Warning "[link-data] Could not link data/ to the main worktree: $_"
}
exit 0

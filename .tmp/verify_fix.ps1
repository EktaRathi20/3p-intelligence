# Mirrors Backend/services/assessment_engine.py gather_evidence task matching
# (pre- and post-fix) against the REAL Database files. Read-only.
$ErrorActionPreference = 'Stop'
$tasks = (Get-Content Database/tasks.json -Raw | ConvertFrom-Json).PSObject.Properties.Value
$regions = (Get-Content Database/regions.json -Raw | ConvertFrom-Json).PSObject.Properties
$regionKey = 'IN-PY-YNM'  # what the Recovery console sends (managed code)

# OLD logic: case-sensitive equality
$old = @($tasks | Where-Object { [string]$_.regionKey -ceq $regionKey })

# NEW logic: case-insensitive + region id/code variants
$accepted = New-Object Collections.Generic.HashSet[string]
$v = $regionKey.Trim().ToLower(); if ($v) { [void]$accepted.Add($v) }
$match = $regions | Where-Object {
  ([string]$_.Value.code).ToLower() -eq $regionKey.ToLower() -or [string]$_.Name -ceq $regionKey
} | Select-Object -First 1
Write-Host "region matched: $($match.Value.name) id=$($match.Name) code=$($match.Value.code)"
foreach ($c in @($match.Name, $match.Value.code)) {
  $t = [string]$c; if ($t) { $t = $t.Trim().ToLower() }; if ($t) { [void]$accepted.Add($t) }
}
$new = @($tasks | Where-Object { $k = ([string]$_.regionKey).Trim().ToLower(); $k -and $accepted.Contains($k) })

$submitted = @($new | Where-Object { $_.status -ceq 'Submitted' }).Count
$reports = 0; $assisted = 0
foreach ($t in $new) { foreach ($r in @($t.reports)) { $reports++; $assisted += [int]$r.peopleAssisted } }
Write-Host "OLD case-sensitive tasks: $($old.Count)"
Write-Host "NEW matched tasks: $($new.Count) submitted=$submitted reports=$reports assisted=$assisted"
if ($old.Count -ne 0) { throw "premise broken: old logic matched tasks" }
if ($new.Count -eq 0) { throw "fix ineffective: new logic matched nothing" }
Write-Host "PROBE PASS"

$root_dir = Split-Path -Parent $PSScriptRoot

Set-Location "$root_dir"
$Env:APP_ROOT = "$root_dir"

& "venv\Scripts\activate.ps1"

if ($args.Count -eq 0) {
    Start-Process -Wait -NoNewWindow -FilePath RFWScopeDAQ -ArgumentList '-h'
} else {
    Start-Process -Wait -NoNewWindow -FilePath RFWScopeDAQ -ArgumentList "$($args -join ' ')"
}

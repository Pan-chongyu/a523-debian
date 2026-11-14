param([ValidateSet('zh-CN','en','ja','es')][string]$Language='zh-CN',[switch]$DryRun)
$ErrorActionPreference='Stop'
$tzxIdentity=[Security.Principal.WindowsIdentity]::GetCurrent()
$tzxPrincipal=[Security.Principal.WindowsPrincipal]::new($tzxIdentity)
if (-not $DryRun -and -not $tzxPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell.exe -Verb RunAs -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$PSCommandPath+'"'),'-Language',$Language) -Wait
    exit
}
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    py -3 -m venv .venv
    if ($LASTEXITCODE) { throw 'Install Python 3.10 or newer from https://www.python.org/downloads/windows/' }
}
& ./.venv/Scripts/python.exe -m pip install --use-feature=truststore --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE) { throw 'Dependency installation failed' }
$tzxArgs=@('flash.py','--lang',$Language)
if ($DryRun) { $tzxArgs+='--dry-run' }
& ./.venv/Scripts/python.exe @tzxArgs
if ($LASTEXITCODE) { throw 'Flashing failed; see the message above' }

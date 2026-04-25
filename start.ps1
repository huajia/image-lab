$ErrorActionPreference = "Stop"
$env:IMAGE_LAB_ROOT = (Get-Location).Path
if (-not $env:IMAGE_LAB_HOST) { $env:IMAGE_LAB_HOST = "127.0.0.1" }
if (-not $env:IMAGE_LAB_PORT) { $env:IMAGE_LAB_PORT = "28081" }
python .\image_lab_server.py

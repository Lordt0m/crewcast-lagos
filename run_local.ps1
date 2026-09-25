# CrewCast Lagos Local Startup Script

Write-Host "Starting CrewCast Lagos..." -ForegroundColor Cyan

# Activate venv if it exists
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    & ".\.venv\Scripts\Activate.ps1"
}

# Run database migrations
Write-Host "Applying database migrations..." -ForegroundColor Yellow
python manage.py migrate

# Start web server
Write-Host "Starting Django development server at http://127.0.0.1:8000..." -ForegroundColor Green
python manage.py runserver 127.0.0.1:8000

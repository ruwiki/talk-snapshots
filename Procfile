migrate: python -m app.migrate
daily:   python -m app.cli daily
smoke:   python -m app.smoke
web:     gunicorn -w 2 -b 0.0.0.0:$PORT --timeout 120 app.web:app

from recruitment.wsgi import app

if __name__ == "__main__":
    host = app.config["HOST"]
    port = int(app.config["PORT"])
    try:
        app.run(host=host, port=port, debug=False)
    except OSError as exc:
        print()
        print(f"ERROR: Could not start on http://{host}:{port}")
        print("Another program is already using this port.")
        print("Close the other recruitment window, then run start.bat again.")
        print(exc)
        raise SystemExit(1) from exc

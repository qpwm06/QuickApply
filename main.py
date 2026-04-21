import os

from app.main import app, ensure_scheduler_started


def main() -> None:
    ensure_scheduler_started(app)
    port = int(os.getenv("PORT", "5273"))
    host = os.getenv("HOST", "0.0.0.0")
    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()

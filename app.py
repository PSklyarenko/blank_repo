import json
import os
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


PORT = int(os.environ.get("PORT", "3000"))
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", "/db/local.db"))


def validate_database_path(path: Path) -> Path:
    resolved = path if path.is_absolute() else Path("/db") / path
    resolved = resolved.resolve()
    db_root = Path("/db").resolve()

    if resolved != db_root and db_root not in resolved.parents:
        raise RuntimeError("DATABASE_PATH must point to a SQLite file under /db")

    return resolved


DB_FILE = validate_database_path(DATABASE_PATH)


def get_connection() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_FILE)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS request_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.commit()
    return connection


def log_request(path: str) -> int:
    with get_connection() as connection:
        connection.execute("INSERT INTO request_log (path) VALUES (?)", (path,))
        (count,) = connection.execute("SELECT COUNT(*) FROM request_log").fetchone()
        return count


class Handler(BaseHTTPRequestHandler):
    server_version = "BlankRepoHTTP/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/healthz":
            self.respond_json({"ok": True, "database": str(DB_FILE)})
            return

        if parsed.path == "/":
            total_requests = log_request(parsed.path)
            self.respond_json(
                {
                    "message": "blank_repo is running",
                    "database": str(DB_FILE),
                    "requests_logged": total_requests,
                }
            )
            return

        self.respond_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def respond_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        print("%s - - %s" % (self.address_string(), format % args), flush=True)


def main() -> None:
    get_connection().close()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Listening on 0.0.0.0:{PORT}; SQLite database: {DB_FILE}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

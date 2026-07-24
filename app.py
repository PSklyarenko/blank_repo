import json
import os
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


PORT = int(os.environ.get("PORT", "3000"))
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", "/db/local.db"))
INDEX_HTML = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>blank_repo preview</title>
    <style>
      :root {
        color-scheme: light;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: #f6f3ee;
        color: #1b1d21;
      }

      * {
        box-sizing: border-box;
      }

      body {
        min-height: 100vh;
        margin: 0;
        display: grid;
        place-items: center;
        padding: 24px;
      }

      main {
        width: min(100%, 440px);
        border: 1px solid #d9d2c7;
        border-radius: 8px;
        background: #ffffff;
        padding: 28px;
        box-shadow: 0 18px 42px rgba(28, 31, 35, 0.12);
      }

      h1 {
        margin: 0 0 8px;
        font-size: 28px;
        line-height: 1.15;
        letter-spacing: 0;
      }

      p {
        margin: 0;
        color: #555b63;
        line-height: 1.5;
      }

      .counter {
        margin: 28px 0 18px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
      }

      .value {
        min-width: 96px;
        font-size: 54px;
        font-weight: 750;
        line-height: 1;
        color: #0e7c66;
        font-variant-numeric: tabular-nums;
      }

      button {
        min-height: 48px;
        border: 0;
        border-radius: 8px;
        background: #283044;
        color: #ffffff;
        cursor: pointer;
        font: inherit;
        font-weight: 700;
        padding: 0 18px;
      }

      button:hover {
        background: #151a2a;
      }

      button:disabled {
        cursor: wait;
        opacity: 0.7;
      }

      .status {
        min-height: 22px;
        font-size: 14px;
        color: #69717a;
      }
    </style>
  </head>
  <body>
    <main>
      <h1>blank_repo preview</h1>
      <p>This page is served by the container and stores its counter in SQLite under /db.</p>
      <section class="counter" aria-label="Counter preview">
        <div>
          <p>Current count</p>
          <div class="value" id="count">__COUNT__</div>
        </div>
        <button id="increment" type="button">Increment</button>
      </section>
      <p class="status" id="status" aria-live="polite"></p>
    </main>
    <script>
      const button = document.getElementById("increment");
      const count = document.getElementById("count");
      const status = document.getElementById("status");

      button.addEventListener("click", async () => {
        button.disabled = true;
        status.textContent = "Saving...";

        try {
          const response = await fetch("/increment", { method: "POST" });
          if (!response.ok) {
            throw new Error("Request failed");
          }

          const payload = await response.json();
          count.textContent = payload.count;
          status.textContent = "Saved in /db/local.db";
        } catch (error) {
          status.textContent = "Could not increment the counter.";
        } finally {
          button.disabled = false;
        }
      });
    </script>
  </body>
</html>
"""


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
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS counters (
            name TEXT PRIMARY KEY,
            value INTEGER NOT NULL DEFAULT 0
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


def get_counter() -> int:
    with get_connection() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO counters (name, value) VALUES ('preview', 0)"
        )
        (count,) = connection.execute(
            "SELECT value FROM counters WHERE name = 'preview'"
        ).fetchone()
        return count


def increment_counter() -> int:
    with get_connection() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO counters (name, value) VALUES ('preview', 0)"
        )
        connection.execute(
            "UPDATE counters SET value = value + 1 WHERE name = 'preview'"
        )
        (count,) = connection.execute(
            "SELECT value FROM counters WHERE name = 'preview'"
        ).fetchone()
        return count


class Handler(BaseHTTPRequestHandler):
    server_version = "BlankRepoHTTP/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/healthz":
            self.respond_json({"ok": True, "database": str(DB_FILE)})
            return

        if parsed.path == "/":
            log_request(parsed.path)
            self.respond_html(INDEX_HTML.replace("__COUNT__", str(get_counter())))
            return

        if parsed.path == "/api/count":
            self.respond_json({"count": get_counter()})
            return

        self.respond_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/increment":
            self.respond_json({"count": increment_counter()})
            return

        self.respond_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def respond_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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

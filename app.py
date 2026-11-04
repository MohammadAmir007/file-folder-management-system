from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import shutil
import urllib.parse

BASE = Path(__file__).resolve().parent
ROOT = (BASE / "workspace").resolve()
STATIC = BASE / "static"

def safe_path(relative=""):
    """Resolve a user path and prevent access outside the workspace."""
    candidate = (ROOT / relative).resolve()
    if candidate != ROOT and ROOT not in candidate.parents:
        raise ValueError("Path is outside the workspace.")
    return candidate

def folder_tree(path):
    """Build a simple tree representation of folders and files."""
    result = {"name": path.name or "workspace", "type": "folder", "children": []}
    try:
        for item in sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            node = {"name": item.name, "type": "file" if item.is_file() else "folder"}
            if item.is_dir():
                node["children"] = folder_tree(item)["children"]
            result["children"].append(node)
    except PermissionError:
        pass
    return result

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            return super().do_GET()
        if parsed.path == "/api/list":
            query = urllib.parse.parse_qs(parsed.query)
            rel = query.get("path", [""])[0]
            try:
                directory = safe_path(rel)
                if not directory.is_dir():
                    return self.send_json({"error": "Folder not found."}, 404)
                items = []
                for p in sorted(directory.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
                    items.append({
                        "name": p.name,
                        "type": "folder" if p.is_dir() else "file",
                        "size": p.stat().st_size if p.is_file() else 0
                    })
                return self.send_json({"path": rel, "items": items, "tree": folder_tree(ROOT)})
            except Exception as exc:
                return self.send_json({"error": str(exc)}, 400)
        if parsed.path == "/api/read":
            query = urllib.parse.parse_qs(parsed.query)
            try:
                p = safe_path(query.get("path", [""])[0])
                if not p.is_file():
                    return self.send_json({"error": "File not found."}, 404)
                return self.send_json({"content": p.read_text(encoding="utf-8")})
            except Exception as exc:
                return self.send_json({"error": str(exc)}, 400)
        return self.send_json({"error": "Not found."}, 404)

    def do_POST(self):
        try:
            data = self.read_body()
            action = data.get("action")
            rel = data.get("path", "")
            target = safe_path(rel)
            name = data.get("name", "").strip()

            if action == "create_folder":
                if not name: raise ValueError("Enter a folder name.")
                (target / name).mkdir()
            elif action == "create_file":
                if not name: raise ValueError("Enter a file name.")
                (target / name).touch(exist_ok=False)
            elif action == "write":
                p = safe_path(data.get("file", ""))
                if not p.is_file(): raise ValueError("File not found.")
                p.write_text(data.get("content", ""), encoding="utf-8")
            elif action == "rename":
                if not name: raise ValueError("Enter the new name.")
                source = safe_path(data.get("item", ""))
                source.rename(source.with_name(name))
            elif action in ("copy", "move"):
                source = safe_path(data.get("item", ""))
                destination = safe_path(data.get("destination", ""))
                if not source.exists() or not destination.is_dir():
                    raise ValueError("Source or destination folder not found.")
                new_path = destination / source.name
                if action == "copy":
                    shutil.copytree(source, new_path) if source.is_dir() else shutil.copy2(source, new_path)
                else:
                    shutil.move(str(source), str(new_path))
            elif action == "delete":
                source = safe_path(data.get("item", ""))
                if source.is_dir(): shutil.rmtree(source)
                elif source.is_file(): source.unlink()
                else: raise ValueError("Item not found.")
            elif action == "search":
                term = name.lower()
                matches = []
                for p in ROOT.rglob("*"):
                    if term in p.name.lower():
                        matches.append(str(p.relative_to(ROOT)))
                return self.send_json({"matches": matches})
            elif action == "sort":
                entries = list(target.iterdir())
                entries.sort(key=lambda p: p.name.lower(), reverse=bool(data.get("descending")))
                return self.send_json({"items": [p.name for p in entries]})
            else:
                raise ValueError("Unknown action.")
            return self.send_json({"message": "Operation completed successfully."})
        except FileExistsError:
            return self.send_json({"error": "An item with that name already exists."}, 400)
        except Exception as exc:
            return self.send_json({"error": str(exc)}, 400)

if __name__ == "__main__":
    ROOT.mkdir(exist_ok=True)
    print("File & Folder Management System")
    print("Open http://localhost:8000 in your browser")
    ThreadingHTTPServer(("localhost", 8000), Handler).serve_forever()

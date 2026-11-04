import os
import uuid
from functools import wraps

from flask import (
    Flask, request, jsonify, send_file, render_template,
    redirect, url_for, session
)
import mysql.connector
from mysql.connector import pooling
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# ================= CONFIGURATION =================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key-in-production")

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

MAX_FILE_SIZE = 500 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", "root"),
    "database": os.environ.get("DB_NAME", "file_manager_db"),
}

connection_pool = pooling.MySQLConnectionPool(
    pool_name="file_manager_pool",
    pool_size=5,
    **DB_CONFIG
)

def get_db():
    return connection_pool.get_connection()


# ================= DATABASE MIGRATION =================
def init_database():
    """Create auth tables/columns while preserving the existing file-manager structure."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Add user_id to existing folders/files if it does not already exist.
    cur.execute("SHOW COLUMNS FROM folders LIKE 'user_id'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE folders ADD COLUMN user_id INT NULL AFTER id")
        cur.execute("CREATE INDEX idx_folder_user ON folders(user_id)")
    cur.execute("SHOW COLUMNS FROM files LIKE 'user_id'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE files ADD COLUMN user_id INT NULL AFTER id")
        cur.execute("CREATE INDEX idx_file_user ON files(user_id)")

    # If this is an old installation, its existing data is temporarily NULL.
    # The first registered user will claim that legacy data.
    conn.commit()
    cur.close()
    conn.close()


# ================= AUTH HELPERS =================
def login_required_json(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Login required"}), 401
        return fn(*args, **kwargs)
    return wrapper

def current_user_id():
    return session.get("user_id")

def ensure_user_root(user_id):
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute(
        "SELECT id FROM folders WHERE user_id = %s AND parent_id IS NULL ORDER BY id LIMIT 1",
        (user_id,)
    )
    root = cur.fetchone()

    if not root:
        cur.execute(
            "INSERT INTO folders (user_id, name, parent_id) VALUES (%s, %s, NULL)",
            (user_id, "Root")
        )
        conn.commit()
        root_id = cur.lastrowid
    else:
        root_id = root["id"]

    cur.close()
    conn.close()
    return root_id

def get_root_id(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM folders WHERE user_id = %s AND parent_id IS NULL ORDER BY id LIMIT 1",
        (user_id,)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else ensure_user_root(user_id)

def folder_belongs_to_user(cursor, folder_id, user_id):
    cursor.execute(
        "SELECT id, name, parent_id FROM folders WHERE id = %s AND user_id = %s",
        (folder_id, user_id)
    )
    return cursor.fetchone()

def file_belongs_to_user(cursor, file_id, user_id):
    cursor.execute(
        "SELECT * FROM files WHERE id = %s AND user_id = %s",
        (file_id, user_id)
    )
    return cursor.fetchone()


# ================= FILE TYPE =================
EXTENSION_TYPE_MAP = {
    "pdf": "pdf",
    "jpg": "image", "jpeg": "image", "png": "image", "gif": "image",
    "webp": "image", "bmp": "image", "svg": "image",
    "mp4": "video", "mkv": "video", "avi": "video", "mov": "video",
    "webm": "video", "3gp": "video",
    "mp3": "audio", "wav": "audio", "m4a": "audio",
    "doc": "document", "docx": "document", "txt": "document",
    "xls": "document", "xlsx": "document", "ppt": "document", "pptx": "document",
    "zip": "archive", "rar": "archive", "7z": "archive",
}

def get_file_type(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return EXTENSION_TYPE_MAP.get(ext, "other")

def format_size(size_bytes):
    if size_bytes is None:
        return "0 B"
    size_bytes = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# ================= PAGE ROUTES =================
@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "GET":
        if "user_id" in session:
            return redirect(url_for("index"))
        return render_template("login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password:
        return render_template("login.html", error="Username aur password dono bhariye.")

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, username, password_hash FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Username ya password galat hai.")

    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    ensure_user_root(user["id"])
    return redirect(url_for("index"))

@app.route("/register", methods=["GET", "POST"])
def register_page():
    if request.method == "GET":
        if "user_id" in session:
            return redirect(url_for("index"))
        return render_template("register.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")

    if len(username) < 3:
        return render_template("register.html", error="Username kam se kam 3 characters ka ho.")
    if len(password) < 6:
        return render_template("register.html", error="Password kam se kam 6 characters ka ho.")
    if password != confirm:
        return render_template("register.html", error="Passwords match nahi karte.")

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
            (username, generate_password_hash(password))
        )
        user_id = cur.lastrowid

        # On an upgraded old installation, the first registered user claims legacy data.
        cur.execute("SELECT COUNT(*) FROM users")
        user_count = cur.fetchone()[0]
        if user_count == 1:
            cur.execute("UPDATE folders SET user_id = %s WHERE user_id IS NULL", (user_id,))
            cur.execute("UPDATE files SET user_id = %s WHERE user_id IS NULL", (user_id,))

        conn.commit()
    except mysql.connector.IntegrityError:
        conn.rollback()
        cur.close()
        conn.close()
        return render_template("register.html", error="Ye username pehle se maujood hai.")
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass

    ensure_user_root(user_id)
    session.clear()
    session["user_id"] = user_id
    session["username"] = username
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


# ================= FOLDER APIs =================
@app.route("/api/me")
@login_required_json
def me():
    return jsonify({"username": session["username"]})

@app.route("/api/root")
@login_required_json
def root():
    return jsonify({"root_id": get_root_id(current_user_id())})

@app.route("/api/folder/<int:folder_id>", methods=["GET"])
@login_required_json
def get_folder_contents(folder_id):
    user_id = current_user_id()
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    current_folder = folder_belongs_to_user(cursor, folder_id, user_id)
    if not current_folder:
        cursor.close()
        conn.close()
        return jsonify({"error": "Folder nahi mila"}), 404

    breadcrumb = []
    node = current_folder
    while node:
        breadcrumb.insert(0, {"id": node["id"], "name": node["name"]})
        if node["parent_id"] is None:
            break
        node = folder_belongs_to_user(cursor, node["parent_id"], user_id)

    cursor.execute(
        "SELECT id, name, created_at FROM folders WHERE parent_id = %s AND user_id = %s ORDER BY name",
        (folder_id, user_id)
    )
    folders = cursor.fetchall()

    cursor.execute(
        """SELECT id, original_name, file_type, file_extension, file_size, uploaded_at
           FROM files WHERE folder_id = %s AND user_id = %s ORDER BY original_name""",
        (folder_id, user_id)
    )
    files = cursor.fetchall()

    for f in files:
        f["file_size_readable"] = format_size(f["file_size"])
        f["uploaded_at"] = f["uploaded_at"].strftime("%d-%m-%Y %H:%M")
    for fo in folders:
        fo["created_at"] = fo["created_at"].strftime("%d-%m-%Y %H:%M")

    cursor.close()
    conn.close()

    return jsonify({
        "current_folder": current_folder,
        "breadcrumb": breadcrumb,
        "folders": folders,
        "files": files
    })

@app.route("/api/folder", methods=["POST"])
@login_required_json
def create_folder():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    parent_id = data.get("parent_id")

    if not name:
        return jsonify({"error": "Folder ka naam zaroori hai"}), 400

    user_id = current_user_id()
    if not parent_id:
        parent_id = get_root_id(user_id)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM folders WHERE id = %s AND user_id = %s",
        (parent_id, user_id)
    )
    if not cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({"error": "Invalid parent folder"}), 403

    cursor.execute(
        "INSERT INTO folders (user_id, name, parent_id) VALUES (%s, %s, %s)",
        (user_id, name, parent_id)
    )
    conn.commit()
    new_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return jsonify({"message": "Folder ban gaya", "id": new_id}), 201

@app.route("/api/folder/<int:folder_id>", methods=["DELETE"])
@login_required_json
def delete_folder(folder_id):
    user_id = current_user_id()
    root_id = get_root_id(user_id)
    if folder_id == root_id:
        return jsonify({"error": "Root folder delete nahi ho sakta"}), 400

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    folder = folder_belongs_to_user(cursor, folder_id, user_id)
    if not folder:
        cursor.close()
        conn.close()
        return jsonify({"error": "Folder nahi mila"}), 404

    # Collect all physical files recursively before DB cascade.
    cursor.execute(
        """WITH RECURSIVE tree AS (
             SELECT id FROM folders WHERE id = %s AND user_id = %s
             UNION ALL
             SELECT f.id FROM folders f
             INNER JOIN tree t ON f.parent_id = t.id
             WHERE f.user_id = %s
           )
           SELECT file_path FROM files
           WHERE user_id = %s AND folder_id IN (SELECT id FROM tree)""",
        (folder_id, user_id, user_id, user_id)
    )
    paths = cursor.fetchall()

    for row in paths:
        try:
            os.remove(row["file_path"])
        except OSError:
            pass

    cursor.execute("DELETE FROM folders WHERE id = %s AND user_id = %s", (folder_id, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Folder delete ho gaya"})

@app.route("/api/folder/<int:folder_id>/rename", methods=["PUT"])
@login_required_json
def rename_folder(folder_id):
    data = request.get_json(silent=True) or {}
    new_name = data.get("name", "").strip()
    if not new_name:
        return jsonify({"error": "Naya naam zaroori hai"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE folders SET name = %s WHERE id = %s AND user_id = %s",
        (new_name, folder_id, current_user_id())
    )
    if cursor.rowcount == 0:
        cursor.close()
        conn.close()
        return jsonify({"error": "Folder nahi mila"}), 404
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Naam badal gaya"})


# ================= FILE APIs =================
@app.route("/api/upload", methods=["POST"])
@login_required_json
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "Koi file nahi mili"}), 400

    file = request.files["file"]
    user_id = current_user_id()
    folder_id = request.form.get("folder_id")

    if file.filename == "":
        return jsonify({"error": "File select nahi ki gayi"}), 400

    if not folder_id:
        folder_id = get_root_id(user_id)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM folders WHERE id = %s AND user_id = %s",
        (folder_id, user_id)
    )
    if not cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({"error": "Invalid folder"}), 403
    cursor.close()
    conn.close()

    original_name = secure_filename(file.filename)
    if not original_name:
        return jsonify({"error": "Invalid filename"}), 400

    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    stored_name = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
    file_path = os.path.join(UPLOAD_FOLDER, stored_name)

    try:
        file.save(file_path)
        file_size = os.path.getsize(file_path)
        file_type = get_file_type(original_name)

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO files
               (user_id, original_name, stored_name, folder_id, file_type,
                file_extension, file_size, file_path)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (user_id, original_name, stored_name, folder_id, file_type,
             ext, file_size, file_path)
        )
        conn.commit()
        new_id = cursor.lastrowid
        cursor.close()
        conn.close()
    except Exception:
        try:
            os.remove(file_path)
        except OSError:
            pass
        raise

    return jsonify({"message": "File upload ho gayi", "id": new_id}), 201

@app.route("/api/file/<int:file_id>/download", methods=["GET"])
@login_required_json
def download_file(file_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    file_row = file_belongs_to_user(cursor, file_id, current_user_id())
    cursor.close()
    conn.close()

    if not file_row or not os.path.exists(file_row["file_path"]):
        return jsonify({"error": "File nahi mili"}), 404

    return send_file(
        file_row["file_path"],
        as_attachment=True,
        download_name=file_row["original_name"]
    )

@app.route("/api/file/<int:file_id>/preview", methods=["GET"])
@login_required_json
def preview_file(file_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    file_row = file_belongs_to_user(cursor, file_id, current_user_id())
    cursor.close()
    conn.close()

    if not file_row or not os.path.exists(file_row["file_path"]):
        return jsonify({"error": "File nahi mili"}), 404

    return send_file(file_row["file_path"])

@app.route("/api/file/<int:file_id>", methods=["DELETE"])
@login_required_json
def delete_file(file_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    row = file_belongs_to_user(cursor, file_id, current_user_id())

    if not row:
        cursor.close()
        conn.close()
        return jsonify({"error": "File nahi mili"}), 404

    try:
        os.remove(row["file_path"])
    except OSError:
        pass

    cursor.execute(
        "DELETE FROM files WHERE id = %s AND user_id = %s",
        (file_id, current_user_id())
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "File delete ho gayi"})

@app.route("/api/file/<int:file_id>/rename", methods=["PUT"])
@login_required_json
def rename_file(file_id):
    data = request.get_json(silent=True) or {}
    new_name = data.get("name", "").strip()
    if not new_name:
        return jsonify({"error": "Naya naam zaroori hai"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE files SET original_name = %s WHERE id = %s AND user_id = %s",
        (new_name, file_id, current_user_id())
    )
    if cursor.rowcount == 0:
        cursor.close()
        conn.close()
        return jsonify({"error": "File nahi mili"}), 404
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Naam badal gaya"})


# ================= SEARCH =================
@app.route("/api/search", methods=["GET"])
@login_required_json
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"folders": [], "files": []})

    user_id = current_user_id()
    like_query = f"%{query}%"

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT id, name, parent_id FROM folders WHERE user_id = %s AND name LIKE %s",
        (user_id, like_query)
    )
    folders = cursor.fetchall()

    cursor.execute(
        """SELECT id, original_name, file_type, file_size, folder_id
           FROM files WHERE user_id = %s AND original_name LIKE %s""",
        (user_id, like_query)
    )
    files = cursor.fetchall()

    for f in files:
        f["file_size_readable"] = format_size(f["file_size"])

    cursor.close()
    conn.close()
    return jsonify({"folders": folders, "files": files})


# ================= ERROR HANDLING =================
@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "File 500 MB se badi hai"}), 413

@app.errorhandler(401)
def unauthorized(_):
    return jsonify({"error": "Login required"}), 401


if __name__ == "__main__":
    init_database()
    app.run(host="0.0.0.0", port=5000, debug=True)

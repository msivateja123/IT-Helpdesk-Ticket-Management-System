import os
import sqlite3
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, g, abort
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "helpdesk.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-development-secret")
app.config["DATABASE"] = DATABASE

STATUSES = ["Open", "In Progress", "Resolved", "Closed"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]
CATEGORIES = ["Hardware", "Software", "Network", "Email", "Access / Password", "Other"]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'requester'
            CHECK(role IN ('admin', 'agent', 'requester')),
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        category TEXT NOT NULL,
        priority TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Open',
        requester_id INTEGER NOT NULL,
        assigned_to INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(requester_id) REFERENCES users(id),
        FOREIGN KEY(assigned_to) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)
    db.commit()


@app.cli.command("init-db")
def init_db_command():
    init_db()
    print("Database tables created.")


@app.cli.command("seed-admin")
def seed_admin_command():
    init_db()
    db = get_db()
    email = os.environ.get("ADMIN_EMAIL", "admin@helpdesk.local")
    password = os.environ.get("ADMIN_PASSWORD", "Admin123!")
    existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        print(f"Admin account already exists: {email}")
        return
    db.execute(
        "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?, ?, ?, 'admin', ?)",
        ("System Admin", email, generate_password_hash(password), now())
    )
    db.commit()
    print(f"Admin created: {email}")
    print("Temporary password is the ADMIN_PASSWORD value (default: Admin123!). Change it after first login.")


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone() if user_id else None


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login"))
        return view(**kwargs)
    return wrapped_view


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped_view(**kwargs):
            if g.user["role"] not in roles:
                abort(403)
            return view(**kwargs)
        return wrapped_view
    return decorator


def get_ticket_or_404(ticket_id):
    ticket = get_db().execute("""
        SELECT t.*, requester.name AS requester_name, requester.email AS requester_email,
               agent.name AS agent_name
        FROM tickets t
        JOIN users requester ON requester.id = t.requester_id
        LEFT JOIN users agent ON agent.id = t.assigned_to
        WHERE t.id = ?
    """, (ticket_id,)).fetchone()
    if ticket is None:
        abort(404)
    if g.user["role"] == "requester" and ticket["requester_id"] != g.user["id"]:
        abort(403)
    return ticket


@app.route("/")
def index():
    return redirect(url_for("dashboard") if g.user else url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        errors = []
        if not name:
            errors.append("Name is required.")
        if "@" not in email or "." not in email:
            errors.append("Enter a valid email address.")
        if len(password) < 8:
            errors.append("Password must contain at least 8 characters.")
        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            try:
                db = get_db()
                db.execute(
                    "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?, ?, ?, 'requester', ?)",
                    (name, email, generate_password_hash(password), now())
                )
                db.commit()
                flash("Account created. You can now sign in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("An account with that email already exists.", "danger")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    filters = []
    params = []
    if g.user["role"] == "requester":
        filters.append("requester_id = ?")
        params.append(g.user["id"])
    elif g.user["role"] == "agent":
        filters.append("(assigned_to = ? OR assigned_to IS NULL)")
        params.append(g.user["id"])

    search = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    if search:
        filters.append("(title LIKE ? OR CAST(id AS TEXT) LIKE ? OR description LIKE ?)")
        params.extend([f"%{search}%"] * 3)
    if status in STATUSES:
        filters.append("status = ?")
        params.append(status)

    where = (" WHERE " + " AND ".join(filters)) if filters else ""
    tickets = db.execute("""
        SELECT t.*, u.name AS requester_name, a.name AS agent_name
        FROM tickets t JOIN users u ON u.id = t.requester_id
        LEFT JOIN users a ON a.id = t.assigned_to
    """ + where + " ORDER BY t.updated_at DESC", params).fetchall()

    count_filter = " WHERE requester_id = ?" if g.user["role"] == "requester" else ""
    count_params = [g.user["id"]] if count_filter else []
    counts = {}
    for item in STATUSES:
        row = db.execute(
            "SELECT COUNT(*) AS n FROM tickets" + count_filter + (" AND " if count_filter else " WHERE ") + "status = ?",
            count_params + [item]
        ).fetchone()
        counts[item] = row["n"]
    return render_template("dashboard.html", tickets=tickets, counts=counts,
                           statuses=STATUSES, search=search, selected_status=status)


@app.route("/tickets/new", methods=["GET", "POST"])
@roles_required("requester", "admin")
def new_ticket():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "")
        priority = request.form.get("priority", "")
        if not title or not description or category not in CATEGORIES or priority not in PRIORITIES:
            flash("Complete all fields with valid values.", "danger")
        else:
            db = get_db()
            cursor = db.execute("""
                INSERT INTO tickets (title, description, category, priority, status,
                                     requester_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'Open', ?, ?, ?)
            """, (title, description, category, priority, g.user["id"], now(), now()))
            db.commit()
            flash(f"Ticket HD-{cursor.lastrowid:05d} created successfully.", "success")
            return redirect(url_for("ticket_detail", ticket_id=cursor.lastrowid))
    return render_template("new_ticket.html", categories=CATEGORIES, priorities=PRIORITIES)


@app.route("/tickets/<int:ticket_id>", methods=["GET", "POST"])
@login_required
def ticket_detail(ticket_id):
    ticket = get_ticket_or_404(ticket_id)
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "comment":
            message = request.form.get("message", "").strip()
            if message:
                db.execute(
                    "INSERT INTO comments (ticket_id, user_id, message, created_at) VALUES (?, ?, ?, ?)",
                    (ticket_id, g.user["id"], message, now())
                )
                db.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now(), ticket_id))
                db.commit()
                flash("Comment added.", "success")
            else:
                flash("Comment cannot be empty.", "danger")
        elif action == "update" and g.user["role"] in ("admin", "agent"):
            status = request.form.get("status")
            priority = request.form.get("priority")
            assigned_to = request.form.get("assigned_to") or None
            valid_agent = None
            if assigned_to:
                valid_agent = db.execute("SELECT id FROM users WHERE id = ? AND role IN ('agent','admin')",
                                         (assigned_to,)).fetchone()
            if status in STATUSES and priority in PRIORITIES and (not assigned_to or valid_agent):
                db.execute("""
                    UPDATE tickets SET status = ?, priority = ?, assigned_to = ?, updated_at = ?
                    WHERE id = ?
                """, (status, priority, assigned_to, now(), ticket_id))
                db.commit()
                flash("Ticket details updated.", "success")
            else:
                flash("Invalid ticket update.", "danger")
        return redirect(url_for("ticket_detail", ticket_id=ticket_id))

    ticket = get_ticket_or_404(ticket_id)
    comments = db.execute("""
        SELECT c.*, u.name AS author_name, u.role AS author_role
        FROM comments c JOIN users u ON u.id = c.user_id
        WHERE c.ticket_id = ? ORDER BY c.created_at
    """, (ticket_id,)).fetchall()
    agents = db.execute("SELECT id, name FROM users WHERE role IN ('agent','admin') ORDER BY name").fetchall()
    return render_template("ticket_detail.html", ticket=ticket, comments=comments,
                           statuses=STATUSES, priorities=PRIORITIES, agents=agents)


@app.route("/admin/users", methods=["GET", "POST"])
@roles_required("admin")
def manage_users():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "")
        if not name or "@" not in email or len(password) < 8 or role not in ("agent", "requester"):
            flash("Enter a name, valid email, password (8+ characters) and valid role.", "danger")
        else:
            try:
                db.execute(
                    "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
                    (name, email, generate_password_hash(password), role, now())
                )
                db.commit()
                flash(f"{role.title()} account created.", "success")
            except sqlite3.IntegrityError:
                flash("That email address is already registered.", "danger")
    users = db.execute("SELECT id, name, email, role, created_at FROM users ORDER BY created_at DESC").fetchall()
    return render_template("users.html", users=users)


@app.errorhandler(403)
def forbidden(error):
    return render_template("error.html", code=403, message="You do not have permission to access this page."), 403


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message="The page or ticket could not be found."), 404


if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(debug=True)

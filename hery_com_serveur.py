import os
import json
import sqlite3
import hashlib
import secrets
import re

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


# ============================================================
# HERY.COM - SERVEUR COMPLET
# Client + Propriétaire
# GitHub + Render
# Python 3 + SQLite
# Aucune bibliothèque externe
# ============================================================

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 8080))

DB_FILE = "hery_com.db"

# Identifiants du propriétaire
# À configurer dans Render > Environment
OWNER_GMAIL = os.environ.get("OWNER_GMAIL", "")
OWNER_PASSWORD = os.environ.get("OWNER_PASSWORD", "")

# token -> informations de session
TOKENS = {}


# ============================================================
# BASE DE DONNÉES
# ============================================================

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database():

    conn = get_db()
    cur = conn.cursor()

    # ---------------- USERS ----------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            gmail TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ---------------- PRODUCTS ----------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            price INTEGER NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            emoji TEXT DEFAULT '🛍️',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ---------------- ORDERS ----------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            total INTEGER NOT NULL,
            address TEXT NOT NULL,
            city TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'En attente',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id)
                REFERENCES users(id)
        )
    """)

    # ---------------- ORDER ITEMS ----------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            price INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY(order_id)
                REFERENCES orders(id)
                ON DELETE CASCADE
        )
    """)

    # ---------------- PRODUITS DE DÉPART ----------------

    cur.execute(
        "SELECT COUNT(*) AS n FROM products"
    )

    if cur.fetchone()["n"] == 0:

        products = [

            (
                "Smartphone HERY X1",
                "Téléphones",
                "Smartphone moderne avec grand écran, bonne autonomie et appareil photo performant.",
                250000,
                20,
                "📱"
            ),

            (
                "Ordinateur Portable Pro",
                "Informatique",
                "Ordinateur portable rapide pour les études et le travail.",
                650000,
                10,
                "💻"
            ),

            (
                "Casque Bluetooth",
                "Audio",
                "Casque sans fil confortable avec une excellente qualité sonore.",
                35000,
                30,
                "🎧"
            ),

            (
                "Montre Connectée",
                "Accessoires",
                "Montre connectée élégante avec notifications.",
                80000,
                15,
                "⌚"
            ),

            (
                "Sac à Dos",
                "Mode",
                "Sac à dos solide et pratique.",
                25000,
                40,
                "🎒"
            ),

            (
                "Écouteurs Sans Fil",
                "Audio",
                "Écouteurs Bluetooth avec boîtier de recharge.",
                45000,
                25,
                "🎵"
            )
        ]

        cur.executemany("""
            INSERT INTO products
            (
                name,
                category,
                description,
                price,
                stock,
                emoji
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, products)

    conn.commit()
    conn.close()


# ============================================================
# SÉCURITÉ
# ============================================================

def hash_password(password):

    salt = secrets.token_hex(16)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120000
    ).hex()

    return salt + ":" + digest


def verify_password(password, stored):

    try:

        salt, digest = stored.split(":", 1)

        check = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            120000
        ).hex()

        return secrets.compare_digest(
            check,
            digest
        )

    except Exception:
        return False


def valid_gmail(gmail):

    return bool(
        re.fullmatch(
            r"[A-Za-z0-9._%+-]+@gmail\.com",
            gmail
        )
    )


def create_token(user_id=None, role="client"):

    token = secrets.token_urlsafe(32)

    TOKENS[token] = {
        "id": user_id,
        "role": role
    }

    return token


# ============================================================
# JSON / HTTP
# ============================================================

def row_to_dict(row):

    if row is None:
        return None

    return dict(row)


def send_json(handler, status, data):

    body = json.dumps(
        data,
        ensure_ascii=False
    ).encode("utf-8")

    handler.send_response(status)

    handler.send_header(
        "Content-Type",
        "application/json; charset=utf-8"
    )

    handler.send_header(
        "Content-Length",
        str(len(body))
    )

    # CORS
    handler.send_header(
        "Access-Control-Allow-Origin",
        "*"
    )

    handler.send_header(
        "Access-Control-Allow-Headers",
        "Content-Type, Authorization"
    )

    handler.send_header(
        "Access-Control-Allow-Methods",
        "GET, POST, PUT, DELETE, OPTIONS"
    )

    handler.end_headers()

    handler.wfile.write(body)


def error(handler, status, message):

    send_json(
        handler,
        status,
        {
            "success": False,
            "message": message
        }
    )


def get_body(handler):

    try:

        length = int(
            handler.headers.get(
                "Content-Length",
                "0"
            )
        )

    except Exception:

        length = 0

    if length <= 0:
        return {}

    raw = handler.rfile.read(length)

    try:

        return json.loads(
            raw.decode("utf-8")
        )

    except Exception:

        raise ValueError(
            "JSON invalide"
        )


# ============================================================
# AUTHENTIFICATION CLIENT
# ============================================================

def get_session(handler):

    auth = handler.headers.get(
        "Authorization",
        ""
    )

    if not auth.startswith("Bearer "):
        return None

    token = auth[7:].strip()

    return TOKENS.get(token)


def get_client(handler):

    session = get_session(handler)

    if not session:
        return None

    if session["role"] != "client":
        return None

    user_id = session["id"]

    conn = get_db()

    user = conn.execute("""
        SELECT
            id,
            name,
            phone,
            gmail,
            created_at
        FROM users
        WHERE id=?
    """, (user_id,)).fetchone()

    conn.close()

    return user


def require_client(handler):

    user = get_client(handler)

    if not user:

        error(
            handler,
            401,
            "Authentification client requise"
        )

        return None

    return user


# ============================================================
# AUTHENTIFICATION PROPRIÉTAIRE
# ============================================================

def require_owner(handler):

    session = get_session(handler)

    if not session:
        error(
            handler,
            401,
            "Authentification propriétaire requise"
        )
        return False

    if session["role"] != "owner":

        error(
            handler,
            403,
            "Accès propriétaire refusé"
        )

        return False

    return True


# ============================================================
# HANDLER PRINCIPAL
# ============================================================

class HeryHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):

        print(
            "[%s] %s"
            % (
                self.log_date_time_string(),
                fmt % args
            )
        )

    # ========================================================
    # OPTIONS
    # ========================================================

    def do_OPTIONS(self):

        send_json(
            self,
            200,
            {
                "success": True
            }
        )

    # ========================================================
    # GET
    # ========================================================

    def do_GET(self):

        path = (
            urlparse(self.path)
            .path
            .rstrip("/")
            or "/"
        )

        # ----------------------------------------------------
        # ACCUEIL
        # ----------------------------------------------------

        if path == "/":

            return send_json(
                self,
                200,
                {
                    "success": True,
                    "application": "HERY.COM",
                    "server": "online",
                    "version": "2.0"
                }
            )

        # ----------------------------------------------------
        # HEALTH
        # ----------------------------------------------------

        if path == "/api/health":

            return send_json(
                self,
                200,
                {
                    "success": True,
                    "server": "HERY.COM",
                    "database": "SQLite",
                    "status": "online"
                }
            )

        # ----------------------------------------------------
        # CLIENT : PRODUITS
        # ----------------------------------------------------

        if path == "/api/products":

            return self.products()

        # ----------------------------------------------------
        # CLIENT : PRODUIT
        # ----------------------------------------------------

        if path.startswith("/api/products/"):

            try:

                product_id = int(
                    path.split("/")[-1]
                )

            except ValueError:

                return error(
                    self,
                    400,
                    "ID produit invalide"
                )

            return self.product(
                product_id
            )

        # ----------------------------------------------------
        # CLIENT : CATÉGORIES
        # ----------------------------------------------------

        if path == "/api/categories":

            return self.categories()

        # ----------------------------------------------------
        # CLIENT : PROFIL
        # ----------------------------------------------------

        if path == "/api/me":

            user = require_client(self)

            if not user:
                return

            return send_json(
                self,
                200,
                {
                    "success": True,
                    "user": row_to_dict(user)
                }
            )

        # ----------------------------------------------------
        # CLIENT : COMMANDES
        # ----------------------------------------------------

        if path == "/api/orders":

            user = require_client(self)

            if not user:
                return

            return self.orders(
                user["id"]
            )

        # ----------------------------------------------------
        # PROPRIÉTAIRE : PRODUITS
        # ----------------------------------------------------

        if path == "/api/owner/products":

            if not require_owner(self):
                return

            return self.owner_products()

        # ----------------------------------------------------
        # PROPRIÉTAIRE : COMMANDES
        # ----------------------------------------------------

        if path == "/api/owner/orders":

            if not require_owner(self):
                return

            return self.owner_orders()

        # ----------------------------------------------------
        # PROPRIÉTAIRE : UTILISATEURS
        # ----------------------------------------------------

        if path == "/api/owner/users":

            if not require_owner(self):
                return

            return self.owner_users()

        # ----------------------------------------------------
        # PROPRIÉTAIRE : STATISTIQUES
        # ----------------------------------------------------

        if path == "/api/owner/stats":

            if not require_owner(self):
                return

            return self.owner_stats()

        return error(
            self,
            404,
            "Route introuvable"
        )

    # ========================================================
    # POST
    # ========================================================

    def do_POST(self):

        path = (
            urlparse(self.path)
            .path
            .rstrip("/")
            or "/"
        )

        try:

            data = get_body(self)

        except ValueError as e:

            return error(
                self,
                400,
                str(e)
            )

        # ----------------------------------------------------
        # CLIENT : INSCRIPTION
        # ----------------------------------------------------

        if path == "/api/register":

            return self.register(data)

        # ----------------------------------------------------
        # CLIENT : LOGIN
        # ----------------------------------------------------

        if path == "/api/login":

            return self.login(data)

        # ----------------------------------------------------
        # CLIENT : LOGOUT
        # ----------------------------------------------------

        if path == "/api/logout":

            self.logout()

            return send_json(
                self,
                200,
                {
                    "success": True,
                    "message": "Déconnexion réussie"
                }
            )

        # ----------------------------------------------------
        # CLIENT : COMMANDE
        # ----------------------------------------------------

        if path == "/api/orders":

            user = require_client(self)

            if not user:
                return

            return self.create_order(
                user["id"],
                data
            )

        # ----------------------------------------------------
        # PROPRIÉTAIRE : LOGIN
        # ----------------------------------------------------

        if path == "/api/owner/login":

            return self.owner_login(data)

        # ----------------------------------------------------
        # PROPRIÉTAIRE : AJOUT PRODUIT
        # ----------------------------------------------------

        if path == "/api/owner/products":

            if not require_owner(self):
                return

            return self.owner_add_product(
                data
            )

        # ----------------------------------------------------
        # PROPRIÉTAIRE : LOGOUT
        # ----------------------------------------------------

        if path == "/api/owner/logout":

            self.logout()

            return send_json(
                self,
                200,
                {
                    "success": True,
                    "message": "Déconnexion propriétaire réussie"
                }
            )

        return error(
            self,
            404,
            "Route introuvable"
        )

    # ========================================================
    # PUT
    # ========================================================

    def do_PUT(self):

        path = (
            urlparse(self.path)
            .path
            .rstrip("/")
            or "/"
        )

        try:

            data = get_body(self)

        except ValueError as e:

            return error(
                self,
                400,
                str(e)
            )

        # ----------------------------------------------------
        # PROPRIÉTAIRE : MODIFIER PRODUIT
        # ----------------------------------------------------

        if path.startswith(
            "/api/owner/products/"
        ):

            if not require_owner(self):
                return

            try:

                product_id = int(
                    path.split("/")[-1]
                )

            except ValueError:

                return error(
                    self,
                    400,
                    "ID produit invalide"
                )

            return self.owner_update_product(
                product_id,
                data
            )

        # ----------------------------------------------------
        # PROPRIÉTAIRE : MODIFIER STATUT COMMANDE
        # ----------------------------------------------------

        if path.startswith(
            "/api/owner/orders/"
        ) and path.endswith("/status"):

            if not require_owner(self):
                return

            parts = path.split("/")

            try:

                order_id = int(
                    parts[-2]
                )

            except ValueError:

                return error(
                    self,
                    400,
                    "ID commande invalide"
                )

            return self.owner_update_order_status(
                order_id,
                data
            )

        return error(
            self,
            404,
            "Route introuvable"
        )

    # ========================================================
    # DELETE
    # ========================================================

    def do_DELETE(self):

        path = (
            urlparse(self.path)
            .path
            .rstrip("/")
            or "/"
        )

        # ----------------------------------------------------
        # PROPRIÉTAIRE : SUPPRIMER PRODUIT
        # ----------------------------------------------------

        if path.startswith(
            "/api/owner/products/"
        ):

            if not require_owner(self):
                return

            try:

                product_id = int(
                    path.split("/")[-1]
                )

            except ValueError:

                return error(
                    self,
    

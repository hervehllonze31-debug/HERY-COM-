import os
import json
import sqlite3
import hashlib
import secrets
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 8080))
DB_FILE = "hery_com.db"

TOKENS = {}


# =========================
# BASE DE DONNÉES
# =========================

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database():
    conn = get_db()
    cur = conn.cursor()

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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            total INTEGER NOT NULL,
            address TEXT NOT NULL,
            city TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'En attente',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            price INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id)
            ON DELETE CASCADE
        )
    """)

    cur.execute("SELECT COUNT(*) AS n FROM products")

    if cur.fetchone()["n"] == 0:
        products = [
            (
                "Smartphone HERY X1",
                "Téléphones",
                "Smartphone moderne avec grand écran.",
                250000, 20, "📱"
            ),
            (
                "Ordinateur Portable Pro",
                "Informatique",
                "Ordinateur portable pour études et travail.",
                650000, 10, "💻"
            ),
            (
                "Casque Bluetooth",
                "Audio",
                "Casque sans fil confortable.",
                35000, 30, "🎧"
            ),
            (
                "Montre Connectée",
                "Accessoires",
                "Montre connectée élégante.",
                80000, 15, "⌚"
            ),
            (
                "Sac à Dos",
                "Mode",
                "Sac solide et pratique.",
                25000, 40, "🎒"
            ),
            (
                "Écouteurs Sans Fil",
                "Audio",
                "Écouteurs Bluetooth.",
                45000, 25, "🎵"
            )
        ]

        cur.executemany("""
            INSERT INTO products
            (name, category, description, price, stock, emoji)
            VALUES (?, ?, ?, ?, ?, ?)
        """, products)

    conn.commit()
    conn.close()


# =========================
# SÉCURITÉ
# =========================

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

        return secrets.compare_digest(check, digest)

    except Exception:
        return False


def valid_gmail(gmail):
    return bool(
        re.fullmatch(
            r"[A-Za-z0-9._%+-]+@gmail\.com",
            gmail
        )
    )


def create_token(user_id):
    token = secrets.token_urlsafe(32)
    TOKENS[token] = user_id
    return token


# =========================
# OUTILS
# =========================

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
    length = int(
        handler.headers.get(
            "Content-Length",
            "0"
        )
    )

    if length <= 0:
        return {}

    raw = handler.rfile.read(length)

    try:
        return json.loads(
            raw.decode("utf-8")
        )

    except Exception:
        raise ValueError("JSON invalide")


def get_user(handler):
    auth = handler.headers.get(
        "Authorization",
        ""
    )

    if not auth.startswith("Bearer "):
        return None

    token = auth[7:].strip()
    user_id = TOKENS.get(token)

    if not user_id:
        return None

    conn = get_db()

    user = conn.execute("""
        SELECT id, name, phone, gmail, created_at
        FROM users
        WHERE id=?
    """, (user_id,)).fetchone()

    conn.close()

    return user


def row_to_dict(row):
    return dict(row) if row else None


# =========================
# SERVEUR
# =========================

class HeryHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(
            "[%s] %s"
            % (
                self.log_date_time_string(),
                fmt % args
            )
        )

    def do_OPTIONS(self):
        send_json(
            self,
            200,
            {"success": True}
        )

    # =====================
    # GET
    # =====================

    def do_GET(self):

        path = urlparse(
            self.path
        ).path.rstrip("/") or "/"

        if path == "/":
            return send_json(
                self,
                200,
                {
                    "success": True,
                    "application": "HERY.COM",
                    "server": "online",
                    "version": "1.0"
                }
            )

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

        if path == "/api/products":
            return self.products()

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

            return self.product(product_id)

        if path == "/api/categories":
            return self.categories()

        if path == "/api/me":

            user = get_user(self)

            if not user:
                return error(
                    self,
                    401,
                    "Authentification requise"
                )

            return send_json(
                self,
                200,
                {
                    "success": True,
                    "user": row_to_dict(user)
                }
            )

        if path == "/api/orders":

            user = get_user(self)

            if not user:
                return error(
                    self,
                    401,
                    "Authentification requise"
                )

            return self.orders(
                user["id"]
            )

        return error(
            self,
            404,
            "Route introuvable"
        )

    # =====================
    # POST
    # =====================

    def do_POST(self):

        path = urlparse(
            self.path
        ).path.rstrip("/") or "/"

        try:
            data = get_body(self)

        except ValueError as e:
            return error(
                self,
                400,
                str(e)
            )

        if path == "/api/register":
            return self.register(data)

        if path == "/api/login":
            return self.login(data)

        if path == "/api/logout":

            auth = self.headers.get(
                "Authorization",
                ""
            )

            if auth.startswith("Bearer "):
                TOKENS.pop(
                    auth[7:].strip(),
                    None
                )

            return send_json(
                self,
                200,
                {
                    "success": True,
                    "message": "Déconnexion réussie"
                }
            )

        if path == "/api/orders":

            user = get_user(self)

            if not user:
                return error(
                    self,
                    401,
                    "Authentification requise"
                )

            return self.create_order(
                user["id"],
                data
            )

        return error(
            self,
            404,
            "Route introuvable"
        )

    # =====================
    # INSCRIPTION
    # =====================

    def register(self, data):

        name = str(
            data.get("name", "")
        ).strip()

        phone = str(
            data.get("phone", "")
        ).strip()

        gmail = str(
            data.get("gmail", "")
        ).strip().lower()

        password = str(
            data.get("password", "")
        )

        if not name or not phone or not gmail or not password:
            return error(
                self,
                400,
                "Tous les champs sont obligatoires"
            )

        if not valid_gmail(gmail):
            return error(
                self,
                400,
                "Une adresse Gmail valide est obligatoire"
            )

        if len(password) < 4:
            return error(
                self,
                400,
                "Mot de passe trop court"
            )

        conn = get_db()

        try:

            cur = conn.execute("""
                INSERT INTO users
                (name, phone, gmail, password_hash)
                VALUES (?, ?, ?, ?)
            """, (
                name,
                phone,
                gmail,
                hash_password(password)
            ))

            conn.commit()

            user_id = cur.lastrowid
            token = create_token(user_id)

            user = conn.execute("""
                SELECT id, name, phone, gmail, created_at
                FROM users
                WHERE id=?
            """, (user_id,)).fetchone()

            return send_json(
                self,
                201,
                {
                    "success": True,
                    "message": "Compte créé avec succès",
                    "token": token,
                    "user": row_to_dict(user)
                }
            )

        except sqlite3.IntegrityError:

            return error(
                self,
                409,
                "Cette adresse Gmail est déjà utilisée"
            )

        finally:
            conn.close()

    # =====================
    # CONNEXION
    # =====================

    def login(self, data):

        gmail = str(
            data.get("gmail", "")
        ).strip().lower()

        password = str(
            data.get("password", "")
        )

        if not gmail or not password:
            return error(
                self,
                400,
                "Gmail et mot de passe obligatoires"
            )

        conn = get_db()

        user = conn.execute("""
            SELECT *
            FROM users
            WHERE gmail=?
        """, (gmail,)).fetchone()

        conn.close()

        if (
            not user
            or not verify_password(
                password,
                user["password_hash"]
            )
        ):
            return error(
                self,
                401,
                "Gmail ou mot de passe incorrect"
            )

        token = create_token(
            user["id"]
        )

        return send_json(
            self,
            200,
            {
                "success": True,
                "message": "Connexion réussie",
                "token": token,
                "user": {
                    "id": user["id"],
                    "name": user["name"],
                    "phone": user["phone"],
                    "gmail": user["gmail"],
                    "created_at": user["created_at"]
                }
            }
        )

    # =====================
    # PRODUITS
    # =====================

    def products(self):

        conn = get_db()

        rows = conn.execute("""
            SELECT
                id,
                name,
                category,
                description,
                price,
                stock,
                emoji
            FROM products
            WHERE active=1
            ORDER BY id DESC
        """).fetchall()

        conn.close()

        return send_json(
            self,
            200,
            {
                "success": True,
                "products": [
                    row_to_dict(r)
                    for r in rows
                ]
            }
        )

    def product(self, product_id):

        conn = get_db()

        row = conn.execute("""
            SELECT
                id,
                name,
                category,
                description,
                price,
                stock,
                emoji
            FROM products
            WHERE id=?
            AND active=1
        """, (product_id,)).fetchone()

        conn.close()

        if not row:
            return error(
                self,
                404,
                "Produit introuvable"
            )

        return send_json(
            self,
            200,
            {
                "success": True,
                "product": row_to_dict(row)
            }
        )

    def categories(self):

        conn = get_db()

        rows = conn.execute("""
            SELECT DISTINCT category
            FROM products
            WHERE active=1
            ORDER BY category
        """).fetchall()

        conn.close()

        return send_json(
            self,
            200,
            {
                "success": True,
                "categories": [
                    r["category"]
                    for r in rows
                ]
            }
        )

    # =====================
    # COMMANDES
    # =====================

    def create_order(self, user_id, data):

        address = str(
            data.get("address", "")
        ).strip()

        city = str(
            data.get("city", "")
        ).strip()

        items = data.get(
            "items",
            []
        )

        if not address or not city:
            return error(
                self,
                400,
                "Adresse et ville obligatoires"
            )

        if not isinstance(items, list) or not items:
            return error(
                self,
                400,
                "La commande est vide"
            )

        conn = get_db()

        try:

            conn.execute("BEGIN")

            total = 0
            prepared = []

            for item in items:

                try:
                    product_id = int(
                        item.get("product_id")
                    )

                    quantity = int(
                        item.get(
                            "quantity",
                            1
                        )
                    )

                except Exception:

                    conn.rollback()

                    return error(
                        self,
                        400,
                        "Produit ou quantité invalide"
                    )

                if quantity < 1 or quantity > 100:

                    conn.rollback()

                    return error(
                        self,
                        400,
                        "Quantité invalide"
                    )

                product = conn.execute("""
                    SELECT
                        id,
                        name,
                        price,
                        stock
                    FROM products
                    WHERE id=?
                    AND active=1
                """, (
                    product_id,
                )).fetchone()

                if not product:

                    conn.rollback()

                    return error(
                        self,
                        404,
                        "Produit introuvable"
                    )

                if product["stock"] < quantity:

                    conn.rollback()

                    return error(
                        self,
                        409,
                        "Stock insuffisant"
                    )

                total += (
                    product["price"]
                    * quantity
                )

                prepared.append(
                    (
                        product,
                        quantity
                    )
                )

            cur = conn.execute("""
                INSERT INTO orders
                (user_id, total, address, city, status)
                VALUES (?, ?, ?, ?, 'En attente')
            """, (
                user_id,
                total,
                address,
                city
            ))

            order_id = cur.lastrowid

            for product, quantity in prepared:

                conn.execute("""
                    INSERT INTO order_items
                    (order_id, product_id,
                     product_name, price, quantity)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    order_id,
                    product["id"],
                    product["name"],
                    product["price"],
                    quantity
                ))

                conn.execute("""
                    UPDATE products
                    SET stock = stock - ?
                    WHERE id=?
                """, (
                    quantity,
                    product["id"]
                ))

            conn.commit()

            return send_json(
                self,
                201,
                {
                    "success": True,
                    "message": "Commande enregistrée",
                    "order": {
                        "id": order_id,
                        "total": total,
                        "address": address,
                        "city": city,
                        "status": "En attente"
                    }
                }
            )

        except Exception as e:

            conn.rollback()

            return error(
                self,
                500,
                "Erreur serveur : " + str(e)
            )

        finally:
            conn.close()

    def orders(self, user_id):

        conn = get_db()

        rows = conn.execute("""
            SELECT
                id,
                total,
                address,
                city,
                status,
                created_at
            FROM orders
            WHERE user_id=?
            ORDER BY id DESC
        """, (
            user_id,
        )).fetchall()

        result = []

        for order in rows:

            items = conn.execute("""
                SELECT
                    product_id,
                    product_name,
                    price,
                    quantity
                FROM order_items
                WHERE order_id=?
            """, (
                order["id"],
            )).fetchall()

            obj = row_to_dict(order)

            obj["items"] = [
                row_to_dict(x)
                for x in items
            ]

            result.append(obj)

        conn.close()

        return send_json(
            self,
            200,
            {
                "success": True,
                "orders": result
            }
        )


# =========================
# DÉMARRAGE
# =========================

def main():

    init_database()

    print("=" * 50)
    print("HERY.COM - SERVEUR")
    print("=" * 50)
    print("Serveur démarré")
    print("Port :", PORT)
    print("Paiement : désactivé")
    print("=" * 50)

    server = ThreadingHTTPServer(
        (HOST, PORT),
        HeryHandler
    )

    try:
        server.serve_forever()

    except KeyboardInterrupt:
        print("Arrêt du serveur...")

    finally:
        server.server_close()


if __name__ == "__main__":
    main()

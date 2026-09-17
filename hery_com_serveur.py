from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import sqlite3

HOST = "0.0.0.0"
PORT = 8080
DATABASE = "hery.db"


def init_database():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT NOT NULL,
            prix REAL NOT NULL,
            description TEXT,
            image TEXT
        )
    """)

    conn.commit()
    conn.close()


class HeryServer(BaseHTTPRequestHandler):

    def envoyer_json(self, donnees, code=200):
        resultat = json.dumps(donnees, ensure_ascii=False).encode("utf-8")

        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

        self.wfile.write(resultat)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):

        if self.path == "/":
            self.envoyer_json({
                "application": "HERY.COM",
                "serveur": "OK",
                "message": "API HERY.COM démarrée"
            })

        elif self.path == "/produits":
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, nom, prix, description, image
                FROM produits
            """)

            produits = []

            for ligne in cursor.fetchall():
                produits.append({
                    "id": ligne[0],
                    "nom": ligne[1],
                    "prix": ligne[2],
                    "description": ligne[3],
                    "image": ligne[4]
                })

            conn.close()

            self.envoyer_json(produits)

        else:
            self.envoyer_json({
                "erreur": "Route introuvable"
            }, 404)

    def do_POST(self):

        if self.path == "/produits":

            longueur = int(self.headers.get("Content-Length", 0))
            donnees = self.rfile.read(longueur)

            try:
                produit = json.loads(donnees.decode("utf-8"))

                nom = produit.get("nom")
                prix = produit.get("prix")
                description = produit.get("description", "")
                image = produit.get("image", "")

                if not nom or prix is None:
                    self.envoyer_json({
                        "erreur": "Nom et prix obligatoires"
                    }, 400)
                    return

                conn = sqlite3.connect(DATABASE)
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO produits
                    (nom, prix, description, image)
                    VALUES (?, ?, ?, ?)
                """, (nom, prix, description, image))

                conn.commit()

                nouvel_id = cursor.lastrowid

                conn.close()

                self.envoyer_json({
                    "message": "Produit ajouté",
                    "id": nouvel_id
                }, 201)

            except Exception as erreur:
                self.envoyer_json({
                    "erreur": str(erreur)
                }, 400)

        else:
            self.envoyer_json({
                "erreur": "Route introuvable"
            }, 404)


init_database()

serveur = HTTPServer((HOST, PORT), HeryServer)

print("================================")
print("       HERY.COM SERVEUR")
print("================================")
print("Serveur démarré")
print("Adresse : http://localhost:8080")
print("Produits : http://localhost:8080/produits")
print("Appuyez sur CTRL+C pour arrêter")
print("================================")

try:
    serveur.serve_forever()
except KeyboardInterrupt:
    print("\nServeur arrêté")
    serveur.server_close()

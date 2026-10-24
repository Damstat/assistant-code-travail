"""Partie 3c : interface web (HTML + CSS + JavaScript) pour la démo.

Lancer :
    python -m src.web                (puis ouvrir http://localhost:8000)
    python -m src.web 8080           (autre port)

Le serveur utilise uniquement la bibliothèque standard de Python (http.server) :
aucune dépendance à installer en plus. Il sert les fichiers de src/static/ et
expose deux routes JSON :
    GET  /api/infos              -> modèles et réglages (affichés dans l'en-tête)
    POST /api/question           -> {"question": "..."} ; renvoie le résultat de repondre()

Mise en ligne : les variables HOST et PORT (lues dans l'environnement) permettent
d'écouter sur 0.0.0.0 dans un conteneur (voir Dockerfile et la section du README).
"""
import json
import os
import sys
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src.config import EMBED_MODEL, LLM_MODEL, MIN_SCORE, TOP_K
from src.index import charger_modele
from src.pipeline import repondre

STATIC_DIR = Path(__file__).resolve().parent / "static"
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml"}
LONGUEUR_MAX = 1000  # caractères : une question plus longue est refusée

# Garde-fou pour la version en ligne : chaque adresse IP a droit à QUESTIONS_PAR_MINUTE
# questions par minute, pour ne pas épuiser le quota gratuit de Groq.
QUESTIONS_PAR_MINUTE = int(os.getenv("QUESTIONS_PAR_MINUTE", "10"))
_historique_ip = defaultdict(deque)

# Les pages et fichiers sont servis en parallèle, mais les questions passent une par une
# dans le pipeline : le modèle d'embeddings et traces.jsonl ne sont pas partagés en même temps.
_verrou_pipeline = threading.Lock()
_verrou_ip = threading.Lock()


def trop_de_questions(ip):
    """True si cette IP a déjà posé QUESTIONS_PAR_MINUTE questions dans la dernière minute."""
    maintenant = time.monotonic()
    with _verrou_ip:
        dates = _historique_ip[ip]
        while dates and maintenant - dates[0] > 60:
            dates.popleft()
        if len(dates) >= QUESTIONS_PAR_MINUTE:
            return True
        dates.append(maintenant)
        return False


class Gestionnaire(BaseHTTPRequestHandler):
    def envoyer(self, code, corps, type_contenu):
        self.send_response(code)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def envoyer_json(self, code, donnees):
        self.envoyer(code, json.dumps(donnees, ensure_ascii=False).encode("utf-8"),
                     "application/json; charset=utf-8")

    def adresse_client(self):
        # Derrière un hébergeur (Hugging Face, Render...), la vraie IP est dans X-Forwarded-For
        transmise = self.headers.get("X-Forwarded-For", "")
        return transmise.split(",")[0].strip() or self.client_address[0]

    def do_GET(self):
        if self.path == "/api/infos":
            self.envoyer_json(200, {"embeddings": EMBED_MODEL, "llm": LLM_MODEL,
                                    "top_k": TOP_K, "min_score": MIN_SCORE})
            return
        # Fichiers statiques : uniquement ceux présents dans src/static/ (pas de "../")
        nom = self.path.split("?")[0].lstrip("/") or "index.html"
        fichier = (STATIC_DIR / nom).resolve()
        if fichier.parent != STATIC_DIR or not fichier.is_file():
            self.envoyer(404, b"Introuvable", "text/plain; charset=utf-8")
            return
        self.envoyer(200, fichier.read_bytes(), TYPES.get(fichier.suffix, "application/octet-stream"))

    def do_POST(self):
        if self.path != "/api/question":
            self.envoyer_json(404, {"erreur": "Route inconnue"})
            return
        try:
            taille = int(self.headers.get("Content-Length", 0))
            question = str(json.loads(self.rfile.read(taille) or b"{}").get("question", "")).strip()
        except (ValueError, json.JSONDecodeError):
            self.envoyer_json(400, {"erreur": "Requête mal formée"})
            return
        if not question:
            self.envoyer_json(400, {"erreur": "La question est vide."})
            return
        if len(question) > LONGUEUR_MAX:
            self.envoyer_json(400, {"erreur": f"Question trop longue (maximum {LONGUEUR_MAX} caractères)."})
            return
        if trop_de_questions(self.adresse_client()):
            self.envoyer_json(429, {"erreur": "Trop de questions en peu de temps : patientez une minute."})
            return
        try:
            with _verrou_pipeline:
                resultat = repondre(question)
            self.envoyer_json(200, resultat)
        except Exception as erreur:  # clé absente, réseau coupé, quota Groq dépassé...
            self.envoyer_json(500, {"erreur": str(erreur)})

    def log_message(self, format, *args):
        # On n'affiche que les questions (les traces complètes sont dans logs/traces.jsonl)
        if self.command == "POST":
            sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")


def main():
    hote = os.getenv("HOST", "127.0.0.1")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.getenv("PORT", "8000"))
    print("Assistant Code du Travail du Sénégal (loi n° 2026-18) : interface web")
    print(f"Embeddings : {EMBED_MODEL} | LLM : {LLM_MODEL} | TOP_K = {TOP_K} | MIN_SCORE = {MIN_SCORE}")

    # Chargé au démarrage pour que la première question ne soit pas plus lente
    debut = time.perf_counter()
    charger_modele()
    print(f"Modèle chargé en {time.perf_counter() - debut:.1f} s.")

    serveur = ThreadingHTTPServer((hote, port), Gestionnaire)
    print(f"Ouvrez http://localhost:{port} dans votre navigateur (Ctrl+C pour arrêter).")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        print("\nAu revoir.")


if __name__ == "__main__":
    main()

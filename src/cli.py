"""Partie 3b : interface en ligne de commande pour la démo.

Lancer :
    python -m src.cli                         (mode conversation : on pose plusieurs questions)
    python -m src.cli "Ma question"           (une seule question, puis le programme s'arrête)

En mode conversation, tapez « quitter » (ou Entrée sur une ligne vide) pour sortir.
"""
import sys
import time

from src.config import EMBED_MODEL, LLM_MODEL, MIN_SCORE, TOP_K
from src.index import charger_modele
from src.pipeline import repondre

LIGNE = "-" * 70


def afficher(resultat):
    """Affiche la réponse, puis les sources avec leur score, puis les mesures."""
    print(f"\n{LIGNE}\nRéponse :\n{resultat['reponse']}\n")
    if resultat.get("garde_fou") in ("injection", "trop_long"):
        print(f"(Garde-fou : question bloquée, motif « {resultat['garde_fou']} ».)")
    elif resultat["hors_corpus"]:
        print("(Question jugée hors du Code du Travail.)")
    if resultat.get("garde_fou") == "donnees_personnelles":
        print("(Garde-fou : données personnelles masquées avant l'envoi au LLM.)")
    for outil in resultat.get("outils", []):
        print(f"(Outil appelé par le LLM : {outil['nom']}({outil['arguments']}))")
    print("Sources consultées (de la plus proche à la moins proche) :")
    for numero, p in enumerate(resultat["passages"], start=1):
        print(f"  [{numero}] score {p['score']:.3f}  {p['titre']}  ({p['id']})")
    trace = resultat["trace"]
    print(f"\nTemps : {trace['total_ms']:.0f} ms  {trace['etapes_ms']}  |  "
          f"tokens : {trace['tokens_entree']} entrée + {trace['tokens_sortie']} sortie  |  "
          f"coût : {trace['cout_usd']} $\n{LIGNE}")


def poser(question):
    """Pose une question en attrapant les erreurs, pour que la démo ne s'arrête pas."""
    try:
        afficher(repondre(question))
    except Exception as erreur:  # clé absente, réseau coupé, quota Groq dépassé...
        print(f"\n[Erreur] {erreur}\n")


def main():
    print("Assistant Code du Travail du Sénégal (loi n° 2026-18)")
    print(f"Embeddings : {EMBED_MODEL} | LLM : {LLM_MODEL} | TOP_K = {TOP_K} | MIN_SCORE = {MIN_SCORE}")

    # Le modèle d'embeddings se charge une seule fois au démarrage (environ 2 s)
    debut = time.perf_counter()
    charger_modele()
    print(f"Modèle chargé en {time.perf_counter() - debut:.1f} s.")

    if len(sys.argv) > 1:
        poser(" ".join(sys.argv[1:]))
        return

    print("Posez votre question (ou tapez « quitter »).")
    while True:
        try:
            question = input("\nVotre question > ").strip()
        except (EOFError, KeyboardInterrupt):  # Ctrl+C ou Ctrl+Z : sortie propre
            break
        if question.lower() in ("", "quitter", "exit", "q"):
            break
        poser(question)
    print("Au revoir.")


if __name__ == "__main__":
    main()

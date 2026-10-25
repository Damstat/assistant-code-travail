"""Partie 4 : évaluation du système RAG.

Étape 1 (pertinence) : pour chaque question de data/eval/questions.jsonl, la recherche
retrouve-t-elle le bon article parmi les passages donnés au LLM ?
Elle aide aussi à choisir MIN_SCORE (seuil de score en dessous duquel on refuse).

Utilisation : python -m src.evaluate
"""
import json
import statistics
from pathlib import Path

from src.config import TOP_K
from src.retrieve import retrieve

QUESTIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "eval" / "questions.jsonl"


def charger_questions(chemin=QUESTIONS_PATH):
    """Lit le jeu de questions : une ligne JSON = une question."""
    with open(chemin, encoding="utf-8") as f:
        return [json.loads(ligne) for ligne in f if ligne.strip()]


def evaluer_pertinence(questions, k=TOP_K):
    """Pour chaque question, cherche les k passages et note le rang du premier
    qui vient d'un bon article (1 = en tête, None = absent)."""
    resultats = []
    for q in questions:
        passages = retrieve(q["question"], k=k)
        articles_trouves = [p["article"] for p in passages]
        rang = None
        for numero, article in enumerate(articles_trouves, start=1):
            if article in q["articles"]:
                rang = numero
                break
        resultats.append({
            "id": q["id"],
            "type": q["type"],
            "question": q["question"],
            "rang": rang,
            "meilleur_score": passages[0]["score"] if passages else 0.0,
            "articles_trouves": articles_trouves,
        })
    return resultats


def afficher_pertinence(resultats, k=TOP_K):
    """Affiche le bilan de la recherche et une aide pour choisir MIN_SCORE."""
    avec_reponse = [r for r in resultats if r["type"] != "hors_corpus"]
    trouves = [r for r in avec_reponse if r["rang"] is not None]
    mrr = statistics.mean(1 / r["rang"] if r["rang"] else 0 for r in avec_reponse)

    print(f"Pertinence de la recherche (k = {k}) sur {len(avec_reponse)} questions du corpus")
    print(f"  Bon article retrouvé : {len(trouves)}/{len(avec_reponse)} ({100 * len(trouves) / len(avec_reponse):.0f} %)")
    print(f"  Rang moyen inversé (MRR) : {mrr:.2f}  (1.00 = toujours en tête)")

    ratees = [r for r in avec_reponse if r["rang"] is None]
    if ratees:
        print("\nQuestions où le bon article n'est PAS dans les passages :")
        for r in ratees:
            print(f"  {r['id']} | {r['question'][:60]} | trouvés : {r['articles_trouves']}")

    # Aide au choix de MIN_SCORE : on compare les scores des questions du corpus
    # avec ceux des questions hors sujet.
    scores_corpus = [r["meilleur_score"] for r in avec_reponse]
    scores_hors = [r["meilleur_score"] for r in resultats if r["type"] == "hors_corpus"]
    if scores_hors:
        print("\nScore du meilleur passage")
        print(f"  Questions du corpus : de {min(scores_corpus):.3f} à {max(scores_corpus):.3f}")
        print(f"  Questions hors sujet : de {min(scores_hors):.3f} à {max(scores_hors):.3f}")
        if max(scores_hors) < min(scores_corpus):
            seuil = (max(scores_hors) + min(scores_corpus)) / 2
            print(f"  -> Les deux groupes sont séparés. Seuil possible : MIN_SCORE = {seuil:.2f}")
        else:
            print("  -> Les scores se chevauchent : un seuil seul ne suffit pas à tout séparer.")


def main():
    questions = charger_questions()
    resultats = evaluer_pertinence(questions)
    afficher_pertinence(resultats)


if __name__ == "__main__":
    main()

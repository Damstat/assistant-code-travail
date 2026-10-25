"""Partie 4 : évaluation des réponses du LLM (fidélité et refus).

Pour chaque question de data/eval/questions.jsonl, on pose la question au pipeline
complet (recherche + LLM) et on vérifie :
- questions du corpus : la réponse contient les faits attendus (mots_cles), cite le bon
  article, et n'est pas un refus à tort ;
- questions hors sujet : le système refuse bien de répondre ;
- cas limite : la réponse est affichée pour être lue à la main.

Le détail de chaque réponse est écrit dans logs/evaluation_reponses.jsonl.
Utilisation : python -m src.evaluate_reponses
"""
import json
import re
import statistics
import time

from src.config import LOGS_DIR
from src.evaluate import charger_questions
from src.pipeline import repondre

SORTIE = LOGS_DIR / "evaluation_reponses.jsonl"
PAUSE_S = 2  # pause entre deux questions, pour rester sous la limite du niveau gratuit de Groq


def articles_cites(reponse):
    """Numéros d'articles cités dans la réponse, par exemple 'article 277' ou 'art. 277'."""
    return {int(n) for n in re.findall(r"art(?:icles?|\.)\s*(\d+)", reponse, flags=re.IGNORECASE)}


def evaluer_une(q):
    """Pose la question au pipeline et note si la réponse est correcte."""
    resultat = repondre(q["question"])
    reponse = resultat["reponse"]
    refus = resultat["hors_corpus"]
    ligne = {
        "id": q["id"],
        "type": q["type"],
        "question": q["question"],
        "reponse": reponse,
        "refus": refus,
        "total_ms": resultat["trace"]["total_ms"],
    }
    if q["type"] == "corpus":
        manquants = [m for m in q["mots_cles"] if m.lower() not in reponse.lower()]
        cites = articles_cites(reponse)
        ligne["mots_manquants"] = manquants
        ligne["article_cite"] = any(a in cites for a in q["articles"])
        ligne["correct"] = (not refus) and not manquants
    elif q["type"] == "hors_corpus":
        ligne["correct"] = refus
    else:
        ligne["correct"] = None  # cas limite : à juger à la main
    return ligne


def afficher(lignes):
    """Affiche le bilan : fidélité, citations, refus à tort, refus attendus."""
    corpus = [l for l in lignes if l["type"] == "corpus"]
    hors = [l for l in lignes if l["type"] == "hors_corpus"]
    limites = [l for l in lignes if l["type"] == "partielle"]

    bonnes = [l for l in corpus if l["correct"]]
    print(f"Questions du corpus : {len(bonnes)}/{len(corpus)} réponses correctes")
    print(f"  Refus à tort : {sum(l['refus'] for l in corpus)}")
    print(f"  Bon article cité : {sum(l['article_cite'] for l in corpus)}/{len(corpus)}")
    for l in corpus:
        if not l["correct"]:
            print(f"  ! {l['id']} | manquants : {l['mots_manquants']} | refus : {l['refus']}")
            print(f"      {l['reponse'][:160]}")

    refus_ok = [l for l in hors if l["correct"]]
    print(f"\nQuestions hors sujet : {len(refus_ok)}/{len(hors)} bien refusées")
    for l in hors:
        if not l["correct"]:
            print(f"  ! {l['id']} | {l['question']}")
            print(f"      {l['reponse'][:160]}")

    for l in limites:
        print(f"\nCas limite {l['id']} (à juger à la main) : {l['question']}")
        print(f"  {l['reponse'][:300]}")

    print(f"\nDurée moyenne par question : {statistics.mean(l['total_ms'] for l in lignes):.0f} ms")


def main():
    lignes = []
    for q in charger_questions():
        print(f"{q['id']} ...", flush=True)
        lignes.append(evaluer_une(q))
        time.sleep(PAUSE_S)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(SORTIE, "w", encoding="utf-8") as f:
        for l in lignes:
            f.write(json.dumps(l, ensure_ascii=False) + "\n")
    print()
    afficher(lignes)
    print(f"\nDétail : {SORTIE}")


if __name__ == "__main__":
    main()

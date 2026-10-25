"""Partie 4 : bilan des traces écrites dans logs/traces.jsonl.

Affiche, pour toutes les questions tracées : le nombre de requêtes, la latence
(moyenne, médiane, 95e percentile), la durée moyenne de chaque étape, les tokens,
le coût (payé et estimé), les refus du LLM, les garde-fous et les outils appelés.

Utilisation : python -m src.bilan
"""
import json
import math
import statistics
from collections import Counter

from src.observability import TRACES_PATH

# Tarif public de Groq pour llama-3.3-70b-versatile, en dollars par million de tokens.
# Vérifier ces chiffres sur la page tarifs de Groq avant de les citer dans le rapport.
PRIX_PUBLIC_ENTREE = 0.59
PRIX_PUBLIC_SORTIE = 0.79


def lire_traces(chemin=TRACES_PATH):
    """Lit le fichier .jsonl : une ligne = une question. Renvoie une liste de dicts."""
    traces = []
    if not chemin.exists():
        return traces
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip()
            if ligne:
                traces.append(json.loads(ligne))
    return traces


def percentile(valeurs, p):
    """Valeur sous laquelle se trouvent p % des mesures (ex. p=95 : les 5 % les plus lentes sont au-dessus)."""
    valeurs = sorted(valeurs)
    rang = max(math.ceil(p / 100 * len(valeurs)) - 1, 0)
    return valeurs[rang]


def resume_latence(valeurs):
    """Moyenne, médiane, 95e percentile et maximum, en millisecondes."""
    return {
        "moyenne": round(statistics.mean(valeurs), 1),
        "mediane": round(statistics.median(valeurs), 1),
        "p95": round(percentile(valeurs, 95), 1),
        "max": round(max(valeurs), 1),
    }


def bilan(traces):
    """Calcule tous les chiffres du bilan et les renvoie dans un dict."""
    n = len(traces)
    tokens_entree = sum(t.get("tokens_entree", 0) for t in traces)
    tokens_sortie = sum(t.get("tokens_sortie", 0) for t in traces)
    avec_llm = [t for t in traces if "llm" in t.get("etapes_ms", {})]

    # Durée moyenne de chaque étape (recherche, llm, ...) sur les questions qui l'ont faite
    par_etape = {}
    for t in traces:
        for nom, ms in t.get("etapes_ms", {}).items():
            par_etape.setdefault(nom, []).append(ms)

    outils = Counter(o["nom"] for t in traces for o in t.get("outils") or [])
    garde_fous = Counter(t["garde_fou"] for t in traces if t.get("garde_fou"))

    return {
        "requetes": n,
        "requetes_avec_llm": len(avec_llm),
        "latence_totale_ms": resume_latence([t["total_ms"] for t in traces]),
        "latence_llm_ms": resume_latence([t["etapes_ms"]["llm"] for t in avec_llm]) if avec_llm else None,
        "etape_moyenne_ms": {nom: round(statistics.mean(v), 1) for nom, v in par_etape.items()},
        "tokens_entree": tokens_entree,
        "tokens_sortie": tokens_sortie,
        "cout_paye_usd": round(sum(t.get("cout_usd", 0) for t in traces), 6),
        "cout_estime_usd": round(
            (tokens_entree * PRIX_PUBLIC_ENTREE + tokens_sortie * PRIX_PUBLIC_SORTIE) / 1_000_000, 6
        ),
        "refus": sum(1 for t in traces if t.get("hors_corpus")),
        "garde_fous": dict(garde_fous),
        "outils": dict(outils),
    }


def main():
    traces = lire_traces()
    if not traces:
        print(f"Aucune trace dans {TRACES_PATH}. Posez d'abord quelques questions (python -m src.pipeline).")
        return
    b = bilan(traces)
    print(f"Requêtes tracées : {b['requetes']} (dont {b['requetes_avec_llm']} avec appel au LLM)")
    print(f"Refus (hors corpus) : {b['refus']}")
    print(f"Garde-fous déclenchés : {b['garde_fous'] or 'aucun'}")
    print(f"Outils appelés : {b['outils'] or 'aucun'}")
    print("\nLatence totale (ms) :", b["latence_totale_ms"])
    if b["latence_llm_ms"]:
        print("Latence du LLM (ms) :", b["latence_llm_ms"])
    print("Durée moyenne par étape (ms) :", b["etape_moyenne_ms"])
    print(f"\nTokens : {b['tokens_entree']} en entrée, {b['tokens_sortie']} en sortie")
    print(f"Coût payé : {b['cout_paye_usd']} $ (niveau gratuit Groq)")
    print(f"Coût estimé au tarif public : {b['cout_estime_usd']} $")


if __name__ == "__main__":
    main()

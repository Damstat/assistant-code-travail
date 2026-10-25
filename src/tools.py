"""Partie 5a : function calling (le LLM décide lui-même d'appeler une fonction Python).

Idée : un LLM est mauvais en calcul et peut se tromper de chiffre. Pour certaines
questions, on lui donne des « outils » : des fonctions Python qu'il peut demander
d'exécuter. Le LLM ne lance rien lui-même : il renvoie le NOM de l'outil et ses
ARGUMENTS (en JSON), notre code exécute la fonction, puis renvoie le résultat
au LLM, qui rédige la réponse finale.

Deux outils :
    calculer_conges_payes : nombre de jours de congé payé (articles 248 et 249)
    lire_article          : texte exact d'un article à partir de son numéro
                            (recherche structurée, plus fiable que les embeddings
                            pour une question du type « que dit l'article 277 ? »)

Test sans LLM ni clé Groq : python -m src.tools
"""
import json
from functools import lru_cache

from src.config import CHUNKS_PATH

# Nombre maximal d'allers-retours LLM -> outil -> LLM pour une question.
# Évite une boucle infinie si le modèle redemande des outils sans fin.
MAX_TOURS_OUTILS = 3


# ---------------------------------------------------------------------------
# 1) Les fonctions Python elles-mêmes
# ---------------------------------------------------------------------------

def calculer_conges_payes(mois_service, jeune_travailleur=False, enfants_moins_14_ans=0):
    """Calcule les jours de congé payé selon les articles 248 et 249 du Code du Travail.

    - Article 249 : 2 jours ouvrables par mois de service effectif.
    - Article 249 : +1 jour par mois pour un jeune travailleur (16 à 18 ans, article 3).
    - Article 249 : les mères de famille ont +1 jour par an et par enfant de moins de 14 ans.
    - Article 248 : le droit de prendre le congé est acquis après 12 mois (période de référence).
    Le bonus d'ancienneté dépend des conventions collectives : il n'est pas calculé ici.
    """
    # Le LLM peut envoyer "12" (texte) au lieu de 12 : on convertit prudemment.
    mois = int(float(mois_service))
    enfants = int(float(enfants_moins_14_ans or 0))
    if mois < 0 or enfants < 0:
        return {"erreur": "Le nombre de mois et le nombre d'enfants doivent être positifs."}

    base = 2 * mois                                  # article 249
    bonus_jeune = mois if jeune_travailleur else 0   # article 249 (1 jour par mois)
    bonus_enfants = enfants * (mois // 12)           # article 249 (1 jour par an et par enfant)
    total = base + bonus_jeune + bonus_enfants

    return {
        "jours_ouvrables": total,
        "detail": {
            "base_2_jours_par_mois": base,
            "bonus_jeune_travailleur": bonus_jeune,
            "bonus_enfants_moins_14_ans": bonus_enfants,
        },
        "droit_de_jouissance_acquis": mois >= 12,    # article 248
        "articles": [248, 249],
        "remarque": "Les jours supplémentaires liés à l'ancienneté dépendent des conventions "
                    "collectives (article 249) et ne sont pas inclus.",
    }


@lru_cache(maxsize=None)
def _chunks_par_article():
    """Lit chunks.jsonl une seule fois et range les chunks par numéro d'article."""
    articles = {}
    with open(CHUNKS_PATH, encoding="utf-8") as f:
        for ligne in f:
            chunk = json.loads(ligne)
            articles.setdefault(chunk["article"], []).append(chunk)
    return articles


def lire_article(numero):
    """Renvoie le texte complet d'un article (tous ses chunks, dans l'ordre)."""
    numero = int(float(numero))
    chunks = _chunks_par_article().get(numero)
    if not chunks:
        return {"erreur": f"L'article {numero} n'existe pas dans le corpus (articles 1 à "
                          f"{max(_chunks_par_article())})."}
    return {
        "article": numero,
        "titre": chunks[0]["titre"],
        "source": chunks[0]["source"],
        # Les articles longs sont scindés avec un chevauchement : on recolle les morceaux.
        "texte": "\n".join(c["texte"] for c in chunks),
    }


# ---------------------------------------------------------------------------
# 2) La « notice » des outils, envoyée au LLM (format JSON Schema attendu par Groq)
#    Le LLM lit la description pour décider QUAND appeler l'outil et AVEC QUOI.
# ---------------------------------------------------------------------------

OUTILS = [
    {
        "type": "function",
        "function": {
            "name": "calculer_conges_payes",
            "description": "Calcule le nombre de jours ouvrables de congé payé acquis selon "
                           "les articles 248 et 249 du Code du Travail. À utiliser dès que la "
                           "question demande un nombre de jours de congé pour une durée de travail.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mois_service": {
                        "type": "integer",
                        "description": "Nombre de mois de service effectif (1 an = 12 mois).",
                    },
                    "jeune_travailleur": {
                        "type": "boolean",
                        "description": "Vrai si le travailleur a entre 16 et 18 ans.",
                    },
                    "enfants_moins_14_ans": {
                        "type": "integer",
                        "description": "Pour une mère de famille : nombre d'enfants de moins "
                                       "de 14 ans. 0 sinon.",
                    },
                },
                "required": ["mois_service"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lire_article",
            "description": "Renvoie le texte exact d'un article du Code du Travail à partir de "
                           "son numéro. À utiliser quand la question cite un numéro d'article.",
            "parameters": {
                "type": "object",
                "properties": {
                    "numero": {"type": "integer", "description": "Numéro de l'article, ex. 277."},
                },
                "required": ["numero"],
            },
        },
    },
]

# Nom envoyé par le LLM -> vraie fonction Python à exécuter.
FONCTIONS = {
    "calculer_conges_payes": calculer_conges_payes,
    "lire_article": lire_article,
}

# Règle ajoutée au prompt système (pipeline.py) pour expliquer les outils au LLM.
REGLE_OUTILS = (
    "6. Pour calculer un nombre de jours de congé payé, appelle l'outil calculer_conges_payes "
    "et recopie son résultat. Pour lire un article dont le numéro est donné, appelle "
    "lire_article. Cite les articles renvoyés par l'outil."
)


# ---------------------------------------------------------------------------
# 3) Exécution d'un outil demandé par le LLM, et boucle d'appels
# ---------------------------------------------------------------------------

def executer_outil(nom, arguments_json):
    """Exécute l'outil `nom` avec les arguments (texte JSON) choisis par le LLM.
    Ne plante jamais : en cas de problème, renvoie {"erreur": ...} que le LLM pourra lire.
    """
    if nom not in FONCTIONS:
        return {"erreur": f"Outil inconnu : {nom}"}
    try:
        arguments = json.loads(arguments_json or "{}")
        return FONCTIONS[nom](**arguments)
    except Exception as erreur:  # JSON mal formé, argument inattendu, mauvais type...
        return {"erreur": f"Appel invalide de {nom} : {erreur}"}


def appeler_llm_avec_outils(client, modele, messages, tracer=None, **options):
    """Appelle le LLM en lui proposant les outils, exécute ceux qu'il demande,
    et recommence jusqu'à obtenir une réponse en texte.

    Renvoie (texte_de_la_reponse, liste_des_outils_utilises).
    `tracer` (src.observability.Tracer) cumule les tokens de chaque appel.
    """
    messages = list(messages)  # copie : on ne modifie pas la liste de l'appelant
    outils_utilises = []

    for tour in range(MAX_TOURS_OUTILS + 1):
        # Au dernier tour, on retire les outils pour forcer une réponse en texte.
        avec_outils = tour < MAX_TOURS_OUTILS
        parametres = {"tools": OUTILS, "tool_choice": "auto"} if avec_outils else {}
        rep = client.chat.completions.create(
            model=modele, messages=messages, **parametres, **options
        )
        if tracer is not None and rep.usage is not None:
            tracer.tokens(entree=rep.usage.prompt_tokens, sortie=rep.usage.completion_tokens)

        message = rep.choices[0].message
        if not message.tool_calls:  # le LLM a répondu en texte : c'est fini
            return (message.content or "").strip(), outils_utilises

        # Le LLM demande un ou plusieurs outils. On recopie sa demande dans l'historique...
        messages.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {"id": appel.id, "type": "function",
                 "function": {"name": appel.function.name,
                              "arguments": appel.function.arguments}}
                for appel in message.tool_calls
            ],
        })
        # ... puis on exécute chaque outil et on ajoute son résultat (rôle "tool").
        for appel in message.tool_calls:
            resultat = executer_outil(appel.function.name, appel.function.arguments)
            outils_utilises.append({"nom": appel.function.name,
                                    "arguments": appel.function.arguments,
                                    "resultat": resultat})
            messages.append({
                "role": "tool",
                "tool_call_id": appel.id,
                "content": json.dumps(resultat, ensure_ascii=False),
            })

    return "", outils_utilises  # sécurité : on n'arrive normalement jamais ici


def main():
    """Teste les outils directement, sans LLM (aucune clé Groq nécessaire)."""
    print("12 mois :", calculer_conges_payes(12))
    print("\n6 mois, jeune travailleur :", calculer_conges_payes(6, jeune_travailleur=True))
    print("\n12 mois, mère de 2 enfants :", calculer_conges_payes(12, enfants_moins_14_ans=2))
    print("\nArgument envoyé par un LLM :", executer_outil("calculer_conges_payes",
                                                           '{"mois_service": 24}'))
    print("\nArgument faux :", executer_outil("calculer_conges_payes", '{"mois": 24}'))
    article = lire_article(277)
    print(f"\nlire_article(277) : {article['titre']}\n{article['texte'][:300]}...")
    print("\nlire_article(9999) :", lire_article(9999))


if __name__ == "__main__":
    main()

# Partie 4 : évaluation du système

## Objectif
Mesurer deux choses : (1) la recherche retrouve-t-elle les bons passages ? (2) le modèle répond-il fidèlement au corpus, et refuse-t-il quand il le faut ?

## Système évalué
Pipeline RAG sur le Code du Travail : embeddings `intfloat/multilingual-e5-small` (en local), base ChromaDB, modèle `openai/gpt-oss-120b` via Groq (niveau gratuit), 4 passages donnés au modèle par défaut.

## Jeu d'évaluation
Le fichier `data/eval/questions.jsonl` contient 23 questions :
- 17 questions du corpus, avec une réponse de référence écrite à partir du texte de l'article ;
- 1 cas limite : la durée du préavis de licenciement (le corpus renvoie à un décret, art. 144) ;
- 5 questions hors sujet : cuisine, football, salaire minimum en France, création d'une SARL, capitale du Japon.

Chaque question a une réponse de référence, le ou les articles attendus et des mots-clés.

## Méthode
- **Pertinence** (`src/evaluate.py`) : le bon article est-il parmi les k passages donnés au modèle ? Mesures : taux de réussite et rang moyen inversé (MRR).
- **Réponses** (`src/evaluate_reponses.py`) : chaque question est posée au pipeline complet. Une réponse du corpus est jugée correcte si elle n'est pas un refus et contient tous les mots-clés. On vérifie aussi que le bon article est cité. Une question hors sujet est correcte si le système refuse.
- **Coût et latence** : `src/observability.py` trace chaque requête, `src/bilan.py` résume les traces.

## Résultats

**Recherche**

| Passages (k) | Bon article retrouvé | MRR |
|---|---|---|
| 4 | 17/18 (94 %) | 0,85 |
| 5 | 18/18 (100 %) | 0,86 |
| 6 | 18/18 (100 %) | 0,86 |

**Seuil de refus (MIN_SCORE)** : le meilleur passage a un score de 0,867 à 0,921 pour les questions du corpus et de 0,753 à 0,838 pour les questions hors sujet. Un seuil d'environ 0,85 les sépare, mais la marge est étroite (environ 0,03).

**Réponses du modèle (k = 4)**
- Questions du corpus : 12/17 correctes selon le contrôle automatique (71 %).
- Bon article cité : 16/17.
- Refus à tort : 1/17.
- Questions hors sujet : 5/5 bien refusées.
- Cas limite (préavis) : refus complet.

**Coût et latence** (30 requêtes tracées : 7 essais et les 23 questions d'évaluation)
- Latence totale : moyenne 4,9 s, médiane 4,6 s, 95e percentile 9,7 s.
- Latence du modèle : moyenne 4,0 s, médiane 2,5 s, 95e percentile 9,6 s.
- Tokens : 40 517 en entrée, 1 940 en sortie.
- Coût payé : 0 $ (niveau gratuit de Groq).
- Coût estimé au tarif public de Groq pour `gpt-oss-120b` (0,15 $ par million de tokens en entrée, 0,60 $ en sortie) : environ 0,007 $ pour les 30 requêtes, soit environ 0,00025 $ par requête.

## Erreurs constatées
1. **q14, cessation totale d'activité (vrai échec).** Le modèle refuse de répondre. La recherche a donné les articles 158 à 161 au lieu du 162, qui contient la réponse (indemnité spéciale d'un mois de salaire). Avec 5 passages, la recherche retrouve l'article 162. Nous n'avons pas relancé la réponse complète avec k = 5.
2. **Faux négatifs du contrôle automatique (q01, q07, q13, q16).** Les réponses sont justes sur le fond, mais plus courtes que la référence (elles omettent « 12 semaines après l'accouchement », « dimanche », « payés à plein salaire ») ou utilisent une autre forme du mot (« violente » au lieu de « violence »). Nos mots-clés étaient trop stricts. Nous avons gardé le score automatique tel quel (12/17) pour ne pas ajuster le test aux résultats. Après lecture, 16 réponses sur 17 donnent l'information principale demandée.
3. **Cas limite, préavis de licenciement (q18).** Les passages indiquent seulement qu'un décret fixe la durée (art. 144). Le modèle refuse. Une réponse partielle citant l'article 144 serait préférable.

## Limites
- Seulement 23 questions : les pourcentages sont peu fiables, et le seuil de 0,85 repose sur 5 questions hors sujet.
- Le contrôle par mots-clés est grossier : il ne vérifie ni le sens, ni l'absence d'invention.
- Les questions ont été écrites par l'équipe à partir d'articles que nous avons lus : pas de formulations d'utilisateurs réels, pas de questions pièges.
- La latence du modèle varie beaucoup avec le niveau gratuit de Groq (médiane 2,5 s, 95e percentile 9,6 s).
- Le coût estimé est calculé au tarif public de Groq (les sources consultées donnent 0,60 $ ou 0,75 $ par million de tokens en sortie selon la date), il n'a pas été payé.

## Ce que nous changerions
1. Passer `TOP_K` de 4 à 5.
2. Assouplir la règle 3 du prompt : si un passage renvoie à un décret ou à une convention collective, donner une réponse partielle qui cite l'article, au lieu de refuser.
3. Passer `MIN_SCORE` de 0,25 (qui ne filtre rien) à environ 0,85, après avoir agrandi le jeu de questions hors sujet.
4. Accepter des variantes dans les mots-clés, ou ajouter un juge (humain ou modèle).
5. Agrandir le jeu à une cinquantaine de questions, avec des formulations variées.

## Reproduire l'évaluation
Avec la clé `GROQ_API_KEY` dans `.env` :
- `python -m src.index`
- `python -m src.evaluate`
- `python -m src.evaluate_reponses`
- `python -m src.bilan`

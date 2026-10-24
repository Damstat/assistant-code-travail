"""Partie 2a : calcul des embeddings des chunks et indexation dans ChromaDB.

Usage : python -m src.index

Relançable sans doublons : la collection est supprimée puis recréée à chaque
lancement. À relancer si chunks.jsonl ou EMBED_MODEL changent.
"""
import json
import time

import chromadb
import numpy as np

from src.config import CHROMA_DIR, CHUNKS_PATH, COLLECTION_NAME, EMBED_BACKEND, EMBED_MODEL

# Version ONNX quantifiée (int8, 118 Mo) du même modèle e5-small, pour la mise en ligne :
# elle tourne avec onnxruntime, sans PyTorch, et tient dans 512 Mo de RAM.
ONNX_REPO = "Xenova/multilingual-e5-small"
ONNX_FICHIER = "onnx/model_quantized.onnx"


def prefixes(model_name):
    """Retourne (préfixe des questions, préfixe des passages) attendus par le modèle.

    Les modèles e5 ont été entraînés avec "query: " devant les questions et
    "passage: " devant les textes : sans ces préfixes, leurs résultats se dégradent.
    Les autres modèles (ex. MiniLM) n'en utilisent pas.
    """
    if "e5" in model_name.lower():
        return "query: ", "passage: "
    return "", ""


class ModeleOnnx:
    """Même usage que SentenceTransformer (méthode encode), mais avec onnxruntime.

    Reproduit le calcul de sentence-transformers pour e5 : moyenne des vecteurs
    des tokens (sans compter le remplissage), puis normalisation à une longueur de 1.
    Le découpage en tokens passe par sentencepiece (5 Mo) plutôt que par tokenizer.json,
    qui occupe à lui seul près de 300 Mo de RAM une fois chargé.
    """

    # Numérotation de XLM-RoBERTa (base de e5) : 4 tokens spéciaux en tête,
    # puis les ids de sentencepiece décalés de 1
    DEBUT, REMPLISSAGE, FIN, INCONNU, DECALAGE = 0, 1, 2, 3, 1
    LONGUEUR_MAX = 512

    def __init__(self, repo=ONNX_REPO, fichier=ONNX_FICHIER):
        import onnxruntime as ort
        import sentencepiece as spm
        from huggingface_hub import hf_hub_download

        self.sp = spm.SentencePieceProcessor(model_file=hf_hub_download(repo, "sentencepiece.bpe.model"))
        options = ort.SessionOptions()
        options.enable_cpu_mem_arena = False  # moins de mémoire réservée d'avance
        self.session = ort.InferenceSession(hf_hub_download(repo, fichier), options,
                                            providers=["CPUExecutionProvider"])
        self.entrees = {e.name for e in self.session.get_inputs()}

    def tokens(self, texte):
        """Ids des tokens d'un texte, encadrés par <s> et </s>, coupés à 512 au total."""
        ids = [i + self.DECALAGE if i else self.INCONNU for i in self.sp.encode(texte)]
        return [self.DEBUT] + ids[:self.LONGUEUR_MAX - 2] + [self.FIN]

    def encode(self, textes, batch_size=32, normalize_embeddings=True, show_progress_bar=False):
        paquets = []
        for debut in range(0, len(textes), batch_size):
            lots = [self.tokens(t) for t in textes[debut:debut + batch_size]]
            longueur = max(len(l) for l in lots)
            ids = np.full((len(lots), longueur), self.REMPLISSAGE, dtype=np.int64)
            masque = np.zeros((len(lots), longueur), dtype=np.int64)
            for n, l in enumerate(lots):
                ids[n, :len(l)] = l
                masque[n, :len(l)] = 1
            flux = {"input_ids": ids, "attention_mask": masque}
            if "token_type_ids" in self.entrees:
                flux["token_type_ids"] = np.zeros_like(ids)
            tokens = self.session.run(None, flux)[0]  # (textes, tokens, 384)
            poids = masque[:, :, None].astype(np.float32)
            paquets.append((tokens * poids).sum(axis=1) / poids.sum(axis=1))
            if show_progress_bar:
                print(f"  {min(debut + batch_size, len(textes))}/{len(textes)} chunks", end="\r")
        vecteurs = np.vstack(paquets).astype(np.float32)
        if normalize_embeddings:
            vecteurs /= np.linalg.norm(vecteurs, axis=1, keepdims=True)
        return vecteurs


# Modèles déjà chargés, rangés par nom : on ne charge chaque modèle qu'une fois
_MODELES = {}


def charger_modele(model_name=EMBED_MODEL):
    """Charge le modèle d'embeddings une seule fois (téléchargé au premier appel)."""
    if model_name not in _MODELES and EMBED_BACKEND == "onnx" and model_name == EMBED_MODEL:
        _MODELES[model_name] = ModeleOnnx()
    if model_name not in _MODELES:
        # Import ici : la version en ligne (EMBED_BACKEND=onnx) n'installe pas PyTorch
        from sentence_transformers import SentenceTransformer
        try:
            # D'abord depuis le disque, sans contacter Hugging Face : plus rapide,
            # et ça marche même quand la connexion est coupée ou instable.
            _MODELES[model_name] = SentenceTransformer(model_name, local_files_only=True)
        except Exception:
            # Premier lancement : le modèle n'est pas encore sur le disque, on le télécharge.
            _MODELES[model_name] = SentenceTransformer(model_name)
    return _MODELES[model_name]


def lire_chunks(path=CHUNKS_PATH):
    """Lit chunks.jsonl : une ligne JSON = un chunk (id, texte, titre, source, article)."""
    with open(path, encoding="utf-8") as f:
        return [json.loads(ligne) for ligne in f if ligne.strip()]


def construire_index(model_name=EMBED_MODEL, collection_name=COLLECTION_NAME):
    """Calcule les embeddings de tous les chunks et les range dans ChromaDB.

    Retourne (nombre de chunks indexés, durée du calcul des embeddings en secondes).
    """
    chunks = lire_chunks()
    modele = charger_modele(model_name)
    _, prefixe_passage = prefixes(model_name)

    # 1) Embeddings : une liste de nombres par chunk, calculés par paquets de 32.
    #    normalize_embeddings=True ramène chaque vecteur à une longueur de 1,
    #    ce qui rend la similarité cosinus juste et stable.
    debut = time.perf_counter()
    embeddings = modele.encode(
        [prefixe_passage + c["texte"] for c in chunks],
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    duree = time.perf_counter() - debut

    # 2) Base vectorielle enregistrée sur le disque, dans le dossier chroma_db/
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    # 3) On repart de zéro à chaque lancement : c'est ce qui évite les doublons.
    #    (la première fois, la collection n'existe pas encore : on ignore l'erreur)
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    # 4) "hnsw:space": "cosine" -> ChromaDB compare les vecteurs avec la distance
    #    cosinus. On note aussi le modèle utilisé, pour que retrieve.py vérifie
    #    qu'il interroge la base avec le même modèle.
    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine", "embed_model": model_name},
    )

    # 5) On range, pour chaque chunk : son id, son texte (sans préfixe),
    #    son embedding et ses étiquettes (pour citer la source plus tard).
    collection.add(
        ids=[c["id"] for c in chunks],
        documents=[c["texte"] for c in chunks],
        embeddings=embeddings.tolist(),
        metadatas=[
            {"titre": c["titre"], "source": c["source"], "article": c["article"]}
            for c in chunks
        ],
    )
    return collection.count(), duree


def main():
    print(f"Modèle d'embeddings : {EMBED_MODEL}")
    nombre, duree = construire_index()
    print(f"{nombre} chunks indexés dans {CHROMA_DIR} (collection « {COLLECTION_NAME} »)")
    print(f"Calcul des embeddings : {duree:.1f} s, soit {1000 * duree / nombre:.0f} ms par chunk")


if __name__ == "__main__":
    main()

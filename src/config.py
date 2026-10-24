"""Configuration partagée par toutes les parties du projet."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Chemins -----------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
EVAL_DIR = DATA_DIR / "eval"
REPORTS_DIR = ROOT / "reports"
LOGS_DIR = ROOT / "logs"
CHROMA_DIR = ROOT / "chroma_db"

PDF_PATH = RAW_DIR / "code_travail_loi_2026-18.pdf"
RAW_TEXT_PATH = RAW_DIR / "code_travail.txt"
CHUNKS_PATH = PROCESSED_DIR / "chunks.jsonl"
SOURCES_CSV = DATA_DIR / "sources.csv"

# --- Corpus ------------------------------------------------------------
SOURCE_LABEL = (
    "Loi n° 2026-18 du 03 septembre 2026 portant Code du Travail "
    "(JO du Sénégal n° 7931 du 17 septembre 2026)"
)

# --- Partie 1 : découpage ----------------------------------------------
CHUNK_MAX_CHARS = 1200   # au-delà, un article est scindé en plusieurs chunks
CHUNK_OVERLAP = 150      # chevauchement entre deux chunks d'un même article

# --- Parties 2 à 5 (à ajuster par les personnes concernées) ------------
COLLECTION_NAME = "code_travail"

# Partie 2 : e5-small lit 512 tokens (0 chunk tronqué) au lieu de 128 pour
# paraphrase-multilingual-MiniLM-L12-v2 (393 chunks sur 524 tronqués).
# Il attend les préfixes "query: " / "passage: " (gérés dans src/index.py).
EMBED_MODEL = "intfloat/multilingual-e5-small"

# "torch" (par défaut) : sentence-transformers. "onnx" : même modèle au format ONNX,
# sans PyTorch, utilisé pour la mise en ligne (voir Dockerfile et src/index.py).
EMBED_BACKEND = os.getenv("EMBED_BACKEND", "torch")

TOP_K = int(os.getenv("TOP_K", "4"))
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.25"))

# --- Parties 3 à 5 (à ajuster par les personnes concernées) ------------

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

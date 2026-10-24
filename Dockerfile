# Image de mise en ligne de l'interface web (Render, offre gratuite : 512 Mo de RAM).
# Version allégée : embeddings e5-small au format ONNX, sans PyTorch (voir requirements-web.txt).
# Construire et tester en local :
#   docker build -t assistant-code-travail .
#   docker run -p 10000:10000 -e GROQ_API_KEY=gsk_... assistant-code-travail
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.cache/huggingface \
    EMBED_BACKEND=onnx \
    HOST=0.0.0.0 \
    PORT=10000
WORKDIR /app

COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

COPY src/ src/
COPY data/processed/chunks.jsonl data/processed/chunks.jsonl
RUN mkdir -p logs

# La base vectorielle est construite pendant la construction de l'image (1 à 2 min) :
# le modèle ONNX est téléchargé une fois pour toutes et chroma_db/ est prêt au démarrage.
RUN python -m src.index

EXPOSE 10000
CMD ["python", "-m", "src.web"]

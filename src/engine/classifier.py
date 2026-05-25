import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from typing import List, Tuple, Dict, Optional
from src.config import Config


class TextClassifier:
    """
    Semantic classification engine using Sentence-Transformers and Cosine Similarity.
    """
    def __init__(self, model_name: Optional[str] = None):
        if model_name is None:
            model_name = Config.CLASSIFIER_MODEL_NAME
        try:
            self.model = SentenceTransformer(model_name)
        except Exception as e:
            print(f"Error loading SentenceTransformer model '{model_name}': {e}")
            raise

    def encode(self, texts: List[str]) -> np.ndarray:
        """Encodes a list of strings into embeddings."""
        if not texts:
            return np.array([])
        return self.model.encode(texts)

    def classify(
        self, 
        item_text: str, 
        taxonomy_embeddings: np.ndarray, 
        taxonomy_ids: List[str]
    ) -> Tuple[str, float]:
        """
        Classifies a single item text against taxonomy embeddings.
        Returns (category_uidentifier, confidence_score).
        """
        if not taxonomy_ids or taxonomy_embeddings.size == 0:
            return "unknown", 0.0

        # Encode the item text
        item_embedding = self.encode([item_text])

        # Compute cosine similarity between item embedding and all taxonomy embeddings
        similarities = cosine_similarity(item_embedding, taxonomy_embeddings)[0]

        # Find the index of the highest similarity score
        best_idx = np.argmax(similarities)
        confidence = float(similarities[best_idx])
        category_id = taxonomy_ids[best_idx]

        return category_id, confidence

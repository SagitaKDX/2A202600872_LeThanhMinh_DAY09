from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
import google.generativeai as genai

# Clean up proxy environment variables containing ::1 to prevent httpx url parsing bug
for var in ["no_proxy", "NO_PROXY", "No_Proxy"]:
    if var in os.environ:
        os.environ[var] = ",".join([p for p in os.environ[var].split(",") if "::1" not in p])


class SentenceTransformerEmbeddings:
    """Wrapper that emulates SentenceTransformerEmbeddings interface but uses Gemini embedding-2 with multi-key switching."""

    def __init__(self, model_name: str) -> None:
        self.model_name = "models/gemini-embedding-2"
        self.keys = []
        self.current_key_idx = 0
        
        # Load API keys from apikey.txt
        root_dir = Path(__file__).resolve().parents[2]
        api_key_path = root_dir / "apikey.txt"
        if api_key_path.exists():
            with open(api_key_path, "r", encoding="utf-8") as f:
                for line in f:
                    k = line.strip()
                    if k and not k.startswith("#"):
                        self.keys.append(k)
                        
        # Fallback to environment variable if apikey.txt is empty
        if not self.keys:
            env_key = os.getenv("GOOGLE_API_KEY")
            if env_key:
                self.keys.append(env_key)
                
        if not self.keys:
            raise ValueError("No Gemini API keys found in apikey.txt or GOOGLE_API_KEY env var.")
            
        print(f"[GeminiEmbeddings] Loaded {len(self.keys)} API keys for rotation.")
        self._set_active_key()
        
    def _set_active_key(self) -> None:
        key = self.keys[self.current_key_idx]
        genai.configure(api_key=key)
        
    def _rotate_key(self) -> None:
        self.current_key_idx = (self.current_key_idx + 1) % len(self.keys)
        print(f"[GeminiEmbeddings] Rotating API key. Active key index: {self.current_key_idx}")
        self._set_active_key()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        results = []
        batch_size = 100
        max_attempts = len(self.keys) * 2
        
        i = 0
        while i < len(texts):
            batch = texts[i : i + batch_size]
            success = False
            attempts = 0
            
            while not success and attempts < max_attempts:
                try:
                    response = genai.embed_content(
                        model=self.model_name,
                        content=batch,
                        task_type="retrieval_document"
                    )
                    results.extend(response["embedding"])
                    success = True
                except Exception as e:
                    err_msg = str(e)
                    print(f"[GeminiEmbeddings] Error during document embedding: {err_msg}")
                    self._rotate_key()
                    attempts += 1
                    time.sleep(0.5)
                    
            if not success:
                raise RuntimeError("Failed to embed documents after trying all available Gemini keys.")
            i += batch_size
            
        return results

    def embed_query(self, text: str) -> list[float]:
        max_attempts = len(self.keys) * 2
        attempts = 0
        
        while attempts < max_attempts:
            try:
                response = genai.embed_content(
                    model=self.model_name,
                    content=text,
                    task_type="retrieval_query"
                )
                return response["embedding"]
            except Exception as e:
                err_msg = str(e)
                print(f"[GeminiEmbeddings] Error during query embedding: {err_msg}")
                self._rotate_key()
                attempts += 1
                time.sleep(0.5)
                
        raise RuntimeError("Failed to embed query after trying all available Gemini keys.")

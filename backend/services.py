"""Shared local-model clients; application storage lives in the migrated schema."""
import os
from functools import lru_cache
from langchain_ollama import ChatOllama,OllamaEmbeddings

OLLAMA_URL=os.getenv("OLLAMA_BASE_URL","http://localhost:11434")
EMBEDDING_MODEL=os.getenv("EMBEDDING_MODEL","nomic-embed-text")
CHAT_MODEL=os.getenv("CHAT_MODEL","qwen2.5:7b-instruct")
MODEL_TIMEOUT=float(os.getenv("MODEL_TIMEOUT_SECONDS","300"))

@lru_cache
def get_embeddings():
    return OllamaEmbeddings(model=EMBEDDING_MODEL,base_url=OLLAMA_URL,keep_alive=600,
                            client_kwargs={"timeout":MODEL_TIMEOUT})

@lru_cache
def get_llm():
    return ChatOllama(model=CHAT_MODEL,base_url=OLLAMA_URL,temperature=0,keep_alive="10m",
        num_ctx=int(os.getenv("MODEL_CONTEXT_SIZE","4096")),num_predict=int(os.getenv("MODEL_MAX_TOKENS","1024")),
        client_kwargs={"timeout":MODEL_TIMEOUT})

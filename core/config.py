import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_LLM_MODEL: str = os.getenv("GEMINI_LLM_MODEL", "gemini-3.6-flash")
    GEMINI_EMBED_MODEL: str = os.getenv("GEMINI_EMBED_MODEL", "models/gemini-embedding-001")

    WORKSPACE_DIR: str = os.getenv("WORKSPACE_DIR", "./workspace")

    MAX_ZIP_SIZE_MB: int = int(os.getenv("MAX_ZIP_SIZE_MB", "100"))
    MAX_EXTRACTED_FILES: int = int(os.getenv("MAX_EXTRACTED_FILES", "5000"))
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "5"))

    # --- Supabase / Vercel deployment ---
    # Local dev (default): SQLite registry + FAISS index + local disk, exactly as before.
    # Set these to switch each layer to its Supabase-backed equivalent independently --
    # e.g. you can run Postgres locally while still using local FAISS.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")  # Supabase Postgres connection string
    VECTOR_BACKEND: str = os.getenv("VECTOR_BACKEND", "faiss")  # "faiss" | "pgvector"
    STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "local")  # "local" | "supabase"

    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    SUPABASE_STORAGE_BUCKET: str = os.getenv("SUPABASE_STORAGE_BUCKET", "project-zips")


settings = Settings()

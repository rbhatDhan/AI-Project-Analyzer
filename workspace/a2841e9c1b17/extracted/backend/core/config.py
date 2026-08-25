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


settings = Settings()

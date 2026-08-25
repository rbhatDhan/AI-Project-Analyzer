"""
LLM abstraction for answer generation. Only Gemini is implemented, but the
function signature (`generate_answer`) is what the rest of the app depends
on -- swap providers here without touching api/chat.py.
"""
import google.generativeai as genai

from core.config import settings

_configured = False


def _ensure_configured():
    global _configured
    if not _configured:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set. See .env.example.")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _configured = True


SYSTEM_INSTRUCTION = """You are a code assistant answering questions about ONE specific \
uploaded software project, using only the retrieved context chunks provided below.

Rules:
- Base your answer strictly on the provided context. Do not invent file names, \
functions, or behavior that isn't shown.
- When you reference code, cite the file path and, if available, the symbol/function \
name and line range, e.g. "backend/services/authService.js (loginUser, lines 20-58)".
- If the retrieved context does not contain enough information to answer confidently, \
say: "I could not verify this from the uploaded project." Do not guess.
- Keep answers concise and technical, suitable for someone who wrote the code."""


def _format_context(chunks: list) -> str:
    blocks = []
    for c in chunks:
        loc = f"{c.get('file_path')} (lines {c.get('line_start')}-{c.get('line_end')})"
        blocks.append(f"### {loc} — {c.get('type')} `{c.get('symbol')}`\n```{c.get('language','')}\n{c.get('text','')}\n```")
    return "\n\n".join(blocks) if blocks else "(no relevant context retrieved)"


def generate_answer(question: str, chunks: list) -> str:
    _ensure_configured()
    model = genai.GenerativeModel(
        model_name=settings.GEMINI_LLM_MODEL,
        system_instruction=SYSTEM_INSTRUCTION,
    )
    context = _format_context(chunks)
    prompt = f"Retrieved project context:\n\n{context}\n\nQuestion: {question}"
    response = model.generate_content(prompt)
    return response.text

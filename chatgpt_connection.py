"""Small, safe connectivity check for the OpenAI API."""

import os

from dotenv import load_dotenv
from openai import OpenAI


def create_client() -> OpenAI:
    """Create an OpenAI client using the local .env configuration."""
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not api_key or api_key == "coloque_sua_chave_openai_aqui":
        raise RuntimeError(
            "OPENAI_API_KEY não configurada. "
            "Preencha o arquivo .env na raiz do projeto."
        )

    return OpenAI(api_key=api_key)


def ask_chatgpt(prompt: str) -> str:
    """Send one prompt and return the text response."""
    load_dotenv()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    client = create_client()

    response = client.responses.create(
        model=model,
        input=prompt,
    )

    return response.output_text


if __name__ == "__main__":
    try:
        answer = ask_chatgpt(
            "Responda apenas: conexão com o ChatGPT funcionando."
        )
        print(answer)
    except Exception as error:
        print(f"Erro na conexão com o ChatGPT: {error}")
        raise SystemExit(1)
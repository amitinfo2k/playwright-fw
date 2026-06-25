"""
utils/llm_factory.py
Centralized factory for initializing OpenAI-compatible LLMs with Langfuse observability.
"""

import os
import logging
from langchain_openai import ChatOpenAI
from langfuse.callback import CallbackHandler

logger = logging.getLogger(__name__)

def get_llm(temperature: float = 0):
    """
    Initialize and return a ChatOpenAI instance using generic LLM_* env variables.
    Configures Langfuse callback if credentials are present.
    """
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    api_key  = os.getenv("LLM_API_KEY")
    model    = os.getenv("LLM_MODEL", "gpt-4o")

    if not api_key:
        logger.error("LLM_API_KEY is not set in environment.")
        raise ValueError("LLM_API_KEY is mandatory.")

    # Optional Langfuse Callback
    callbacks = []
    lf_public = os.getenv("LANGFUSE_PUBLIC_KEY")
    lf_secret = os.getenv("LANGFUSE_SECRET_KEY")
    lf_host   = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if lf_public and lf_secret:
        logger.info(f"Langfuse observability enabled (Host: {lf_host})")
        langfuse_handler = CallbackHandler(
            public_key=lf_public,
            secret_key=lf_secret,
            host=lf_host
        )
        callbacks.append(langfuse_handler)
    else:
        logger.warning("Langfuse credentials missing — LLM tracing disabled.")

    return ChatOpenAI(
        model=model,
        openai_api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        callbacks=callbacks
    )

import sys
from pathlib import Path

MODEL_PATH = Path(__file__).parent.parent / "models" / "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"

try:
    from llama_cpp import Llama
except ImportError:
    Llama = None  # Можна поставити заглушку

llm = None

def load_model():
    global llm
    if llm is None and Llama is not None:
        llm = Llama(
            model_path=str(MODEL_PATH),
            n_ctx=2048,
            n_threads=4,
            verbose=False,
        )

def generate(prompt: str) -> str:
    if Llama is None:
        raise RuntimeError("llama_cpp is not available in this environment.")

    load_model()
    output = llm(prompt=prompt, stop=["</s>"])
    return output["choices"][0]["text"]

# generate_report.py

from collections import defaultdict
from pathlib import Path

from backend.config import OUTPUT_DIR, FINAL_REPORT_PATH, PROMPTS_DIR
from backend.ollama_client import generate

# Prompt template for final report
PROMPT_TEMPLATE_PATH = PROMPTS_DIR / "final_report.txt"


def collect_summaries(directory: Path) -> dict:
    summaries = defaultdict(list)

    for file in directory.rglob("*_summary.txt"):
        # Extract document type from file name
        doc_type_raw = file.name.split("_")[0]
        doc_type = ''.join(filter(str.isalpha, doc_type_raw)).upper()

        text = file.read_text(encoding="utf-8").strip()
        summaries[doc_type].append(text)

    return summaries


def build_prompt(summaries_by_type: dict) -> str:
    if not PROMPT_TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Prompt template not found: {PROMPT_TEMPLATE_PATH}")

    base_prompt = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8").strip() + "\n\n"

    for doc_type, summaries in summaries_by_type.items():
        base_prompt += f"=== Documenttype: {doc_type} ===\n"
        for i, summary in enumerate(summaries, 1):
            base_prompt += f"- Samenvatting {i}:\n{summary}\n\n"

    return base_prompt


def main():
    summaries_by_type = collect_summaries(OUTPUT_DIR)

    if not summaries_by_type:
        print("⚠️ Geen samenvattingen gevonden in output_summaries/")
        return

    prompt = build_prompt(summaries_by_type)
    report = generate(prompt)

    FINAL_REPORT_PATH.write_text(report.strip(), encoding="utf-8")
    print(f"✅ Rapport opgeslagen in: {FINAL_REPORT_PATH.resolve()}")


if __name__ == "__main__":
    main()

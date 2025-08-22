# app/utils.py
import pandas as pd
from pathlib import Path
from docx import Document as DocxDocument
import json

def extract_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()

    try:
        if suffix == ".pdf":
            from PyPDF2 import PdfReader
            reader = PdfReader(str(file_path))
            return "\n".join([page.extract_text() or "" for page in reader.pages])

        elif suffix in [".csv", ".tsv"]:
            df = pd.read_csv(file_path, sep="\t" if suffix == ".tsv" else ",", dtype=str)
            df.fillna("", inplace=True)
            rows = df.apply(
                lambda row: " | ".join([
                    f"{col.strip()}: {str(val).strip()}"
                    for col, val in row.items()
                    if str(val).strip() != ""
                ]),
                axis=1
            )
            return "\n".join(rows)

        elif suffix in [".xls", ".xlsx"]:
            # SKIP Excel here — handled in ingest.py for structured row-level embedding
            return ""

        elif suffix in [".txt", ".md"]:
            return file_path.read_text(encoding="utf-8", errors="ignore")

        elif suffix == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return json.dumps(data, indent=2)

        elif suffix == ".docx":
            doc = DocxDocument(str(file_path))
            return "\n".join([para.text for para in doc.paragraphs])

        else:
            return ""

    except Exception as e:
        print(f"❌ Error extracting {file_path.name}: {e}")
        return ""

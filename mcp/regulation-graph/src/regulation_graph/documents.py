"""The registry of source documents (`data/documents.json`): what each one is and how its text was obtained."""

import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

DATA = Path(__file__).resolve().parents[2] / "data"


class Kind(str, Enum):
    REGULATION = "regulation"
    AMENDMENT = "amendment"
    COUNCIL_CONCLUSION = "council_conclusion"
    # The school's merged text of a regulation and its amendments: used to check version resolution, never cited
    CONSOLIDATED = "consolidated"


class TextMethod(str, Enum):
    PDF_TEXT = "pdf_text"
    DOCX = "docx"
    # Scanned PDF transcribed page by page from the page images (data/vision/<id>.md)
    VISION = "vision"
    # Scanned PDF whose OCR text the regulation-server package already holds
    REGULATION_SERVER = "regulation_server"


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[A-Z0-9-]+$")
    number: str | None
    issued: str | None
    kind: Kind
    # dh: undergraduate; chung: every level; dh_sdh: undergraduate and graduate
    level: str
    title: str
    file_name: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    text_method: TextMethod
    amends: list[str] = Field(default_factory=list)
    note: str = ""


def load_documents(path: Path | None = None) -> list[Document]:
    docs = [Document.model_validate(d) for d in json.loads((path or DATA / "documents.json").read_text("utf-8"))]
    ids = {d.id for d in docs}
    if len(ids) != len(docs):
        raise ValueError("duplicate document ids")
    for d in docs:
        if missing := set(d.amends) - ids:
            raise ValueError(f"{d.id} amends unknown documents {sorted(missing)}")
    return docs

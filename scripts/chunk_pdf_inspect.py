from services.pdf_parser import open_pdf
from services.chunker import chunk_pdf, save_chunks

PDF = "temp/books/AI_ENGINEERING_BUILDING.pdf"
OUTPUT = "temp/chunks.json"

doc = open_pdf(PDF)
chunks = chunk_pdf(doc)
save_chunks(chunks, OUTPUT)

print(f"Total chunks: {len(chunks)}")
print()
for chunk in chunks[:5]:
    print(
        f"[{chunk['chunk_index']}]"
        f" pages {chunk['page_start']}-{chunk['page_end']}"
        f" | level={chunk['section_level']}"
        f" | path={chunk['section_path']}"
    )
    print(f"  {chunk['text'][:120]!r}")
    print()

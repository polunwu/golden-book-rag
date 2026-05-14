# BookRAG MVP Architecture

## Goal

Build a minimal but production-minded BookRAG system that can:

1. Upload a PDF book
2. Parse and chunk the content
3. Generate embeddings
4. Store chunks + vectors
5. Perform semantic search
6. Answer questions with citations/page references
7. Support a future frontend UI

---

# High-Level Architecture

```text
Frontend (future)
    ↓
FastAPI
    ↓
PDF Processing Pipeline
    ↓
Postgres + pgvector
    ↓
Semantic Retrieval
    ↓
LLM Response Generation
```

---

# Tech Stack

| Layer | Tech |
|---|---|
| Backend API | FastAPI |
| Database | PostgreSQL |
| Vector Search | pgvector |
| Embedding Model | OpenAI text-embedding-3-small |
| PDF Parsing | PyMuPDF |
| ORM | SQLAlchemy (optional) |
| Frontend (future) | React / Next.js |

FastAPI is used for the MVP because its typed API design, built-in validation,
automatic documentation, and async support fit modern AI/RAG backend workflows
well.

---

# MVP Features

## Phase 1 — Core Retrieval

### Upload PDF

```text
POST /books/upload
```

Responsibilities:

- store PDF
- create book record
- trigger processing pipeline
- validate request/response payloads with FastAPI

---

## PDF Parsing

Extract:

- text
- pages
- headings
- chapter structure

Suggested library:

- PyMuPDF

---

## Chunking

Split book into semantic chunks.

Recommended initial strategy:

```text
~300–800 tokens
overlap: 50–100 tokens
```

Store:

- chunk text
- page range
- section path/title/level
- chunk order

---

## Embedding Generation

Generate embedding vectors for each chunk.

Recommended model:

- OpenAI text-embedding-3-small

Vector dimension:

```text
1536
```

---

## Vector Search

Store vectors in pgvector.

Semantic search flow:

```text
query
↓
query embedding
↓
vector similarity search
↓
retrieve top chunks
```

---

## Ask Question

```text
POST /books/:id/ask
```

Pipeline:

```text
user question
↓
embedding
↓
vector retrieval
↓
top-k chunks
↓
prompt assembly
↓
LLM answer
```

---

# Database Design

## books

```sql
CREATE TABLE books (
  id UUID PRIMARY KEY,
  title TEXT,
  file_path TEXT,
  created_at TIMESTAMP
);
```

---

## chunks

```sql
CREATE TABLE chunks (
  id UUID PRIMARY KEY,

  book_id UUID REFERENCES books(id),

  text TEXT,

  page_start INT,
  page_end INT,

  section_path TEXT[],
  section_title TEXT,
  section_level INT,

  chunk_index INT,

  token_count INT,

  created_at TIMESTAMP
);
```

---

## chunk_embeddings

```sql
CREATE TABLE chunk_embeddings (
  chunk_id UUID PRIMARY KEY REFERENCES chunks(id),

  embedding vector(1536),

  embedding_model TEXT
);
```

---

# pgvector Setup

Install extension:

```sql
CREATE EXTENSION vector;
```

Create ANN index:

```sql
CREATE INDEX chunk_embedding_idx
ON chunk_embeddings
USING hnsw (embedding vector_cosine_ops);
```

---

# Retrieval Query Example

```sql
SELECT
  c.id,
  c.text,
  c.page_start,
  c.section_title,
  c.section_path
FROM chunk_embeddings ce
JOIN chunks c
ON c.id = ce.chunk_id

ORDER BY ce.embedding <=> $1
LIMIT 5;
```

`<=>`:

```text
cosine distance
```

---

# Suggested Project Structure

```text
backend/
├── app.py        # FastAPI entrypoint

├── routes/
│   ├── books.py
│   └── chat.py

├── services/
│   ├── pdf_parser.py
│   ├── chunker.py
│   ├── embeddings.py
│   ├── retrieval.py
│   └── rag.py

├── models/
│   ├── book.py
│   ├── chunk.py
│   └── embedding.py

├── db/
│   └── connection.py

├── uploads/
│   └── *.pdf

└── requirements.txt
```

---

# Initial Processing Pipeline

```text
upload PDF
↓
extract text
↓
detect headings
↓
create chunks
↓
generate embeddings
↓
store metadata
↓
store vectors
```

---

# Retrieval Pipeline

```text
user query
↓
embed query
↓
vector search
↓
retrieve chunks
↓
assemble context
↓
LLM answer
↓
return citations/pages
```

---

# Recommended Initial Constraints

Keep the MVP simple.

Avoid adding:

```text
LangChain
LlamaIndex
Redis
Kafka
Celery
Microservices
Kubernetes
```

until the core retrieval quality works.

---

# Future Improvements

## Better Chunking

Current:

```text
fixed-size chunks
```

Future:

```text
heading-aware chunking
semantic chunking
hierarchical chunking
```

The MVP stores hierarchical section metadata so future heading-aware and
parent-child retrieval can build on the same chunk records.

---

## Hybrid Search

Combine:

```text
BM25
+
Semantic Search
```

---

## Reranking

Add reranker after retrieval:

```text
vector search
↓
top 20
↓
reranker
↓
top 5
```

---

## Parent-Child Retrieval

```text
small child chunks
↓
retrieve
↓
expand to larger parent section
```

Improves context coherence significantly.

---

# Initial Development Order

## Step 1

Set up:

- FastAPI
- Postgres
- pgvector

Verify:

```text
can store vectors
can run similarity search
```

---

## Step 2

Implement:

```text
PDF → text
```

---

## Step 3

Implement:

```text
text → chunks
```

---

## Step 4

Implement:

```text
chunks → embeddings
```

---

## Step 5

Implement:

```text
query → retrieval
```

---

## Step 6

Implement:

```text
retrieval → LLM answer
```

---

# Success Criteria for MVP

The MVP is successful if it can:

- upload a PDF
- answer questions about the book
- return semantically relevant passages
- cite correct page numbers
- maintain coherent retrieval context

That alone is already a legitimate modern RAG project.

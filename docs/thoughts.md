# 1. Datastructure about hierarchical retrieval

Archived: merged into `bookrag_mvp_architecture.md`.

## Not Good: Fixed section fields

Because maybe it won't fit other bookks

```
chapter
section
subsection
```

## Good: hierarchical design as MVP

Better metadata present, can be context expansion, esier for front-end display

```
section_path TEXT[],
section_title TEXT,
section_level INT

section_path   = 完整階層
section_title  = 目前 chunk 所屬最接近的標題
section_level  = 標題層級，例如 1, 2, 3, 4
```

# 2. Upload PDF destination

## Current

local filesystem for MVP

## Future

cloud services like S3 for production

# 3. Chunk strategy might change

## current

fixed-sized

## Future

Other strategies

## So it might store stretigies info in DB

for example: add ingestion_runs

```
CREATE TABLE ingestion_runs (
  id UUID PRIMARY KEY,
  book_id UUID REFERENCES books(id),

  parser_name TEXT NOT NULL,
  chunk_strategy TEXT NOT NULL,

  chunk_config JSONB,

  embedding_model TEXT NOT NULL,

  created_at TIMESTAMP DEFAULT NOW()
);
```

```
CREATE TABLE chunks (
  id UUID PRIMARY KEY,
  book_id UUID REFERENCES books(id),
  ingestion_run_id UUID REFERENCES ingestion_runs(id),

  text TEXT NOT NULL,

  page_start INT,
  page_end INT,

  section_path TEXT[],
  section_title TEXT,
  section_level INT,

  chunk_index INT,
  token_count INT,

  created_at TIMESTAMP DEFAULT NOW()
);
```

# Evaluation proccess

1. build evaluation set

2. goal:
   - Recall@k
   - Mean Reciprocal Rank (MRR)
   - Manual relevance score

```
CREATE TABLE retrieval_eval_cases (
  id UUID PRIMARY KEY,
  book_id UUID REFERENCES books(id),

  query TEXT NOT NULL,

  expected_section_path TEXT[],
  expected_page_start INT,
  expected_page_end INT,
  expected_keywords TEXT[],

  created_at TIMESTAMP DEFAULT NOW()
);
```

```
CREATE TABLE retrieval_eval_results (
  id UUID PRIMARY KEY,
  eval_case_id UUID REFERENCES retrieval_eval_cases(id),
  ingestion_run_id UUID REFERENCES ingestion_runs(id),

  top_k INT,
  retrieved_chunk_ids UUID[],

  hit BOOLEAN,
  first_hit_rank INT,

  created_at TIMESTAMP DEFAULT NOW()
);
```

# 4. Use Fast API instead

Archived: merged into `bookrag_mvp_architecture.md`.

FastAPI is recommended for the BookRAG MVP because its typed API design, built-in validation, automatic documentation, and async support make it a better fit for modern AI/RAG backend architectures than Flask.

# 5. Thinking Budget

Current -> 0

Evaluate retrieval before reasoning. Keep reasoning effort minimal during MVP development to expose retrieval weaknesses and obtain reliable Recall@K and MRR measurements. Increase reasoning only after retrieval performance is validated.

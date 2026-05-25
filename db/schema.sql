CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS books (
  id         UUID PRIMARY KEY,
  title      TEXT,
  file_path  TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chunks (
  id            UUID PRIMARY KEY,
  book_id       UUID REFERENCES books(id),
  text          TEXT NOT NULL,
  page_start    INT,
  page_end      INT,
  section_path  TEXT[],
  section_title TEXT,
  section_level INT,
  chunk_index   INT NOT NULL,
  token_count   INT,
  created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
  chunk_id        UUID PRIMARY KEY REFERENCES chunks(id),
  embedding       vector(1536) NOT NULL,
  embedding_model TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS chunk_embedding_idx
  ON chunk_embeddings USING hnsw (embedding vector_cosine_ops);


-- Enable pgvector for future document embeddings and similarity search.
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify that the extension is available.
SELECT
    extname,
    extversion
FROM pg_extension
WHERE extname = 'vector';

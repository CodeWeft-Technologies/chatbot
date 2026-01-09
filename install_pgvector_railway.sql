-- pgvector Installation Script for Railway PostgreSQL
-- This script should be run by a database administrator with system access

-- Note: pgvector must be installed at the system level first
-- Run these commands on the Railway PostgreSQL container:

/*
# SSH into Railway container (requires Railway CLI)
railway shell

# Install build dependencies
apt-get update
apt-get install -y git build-essential postgresql-server-dev-17

# Clone and build pgvector
cd /tmp
git clone --branch v0.7.0 https://github.com/pgvector/pgvector.git
cd pgvector
make
make install  # Requires root/sudo

# After installation, connect to database and run:
*/

-- Enable the extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify installation
SELECT * FROM pg_available_extensions WHERE name = 'vector';

-- Test vector operations
CREATE TABLE IF NOT EXISTS vector_test (
    id SERIAL PRIMARY KEY,
    embedding vector(1024)
);

-- If this works, pgvector is installed correctly
INSERT INTO vector_test (embedding) VALUES ('[0,0,0,0]');

-- Clean up test
DROP TABLE vector_test;

SELECT 'pgvector installation successful!' as status;

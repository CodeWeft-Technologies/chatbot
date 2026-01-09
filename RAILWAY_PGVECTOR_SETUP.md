# Railway pgvector Deployment Options

## Option 1: Use Railway pgvector Template (EASIEST)

1. Go to Railway Dashboard: https://railway.app/dashboard
2. Create a new project
3. Search for "PostgreSQL with pgvector" template
4. Deploy the template
5. Copy the new database connection string
6. Update your .env file with the new connection

## Option 2: Request pgvector Installation (Contact Support)

1. Open a ticket with Railway support
2. Request pgvector extension installation
3. Provide your database service ID
4. Wait for support to install the extension

## Option 3: Self-Install via Railway CLI (Advanced)

### Prerequisites:
- Railway CLI installed: `npm install -g @railway/cli`
- Railway account logged in: `railway login`

### Steps:

```bash
# Link to your Railway project
railway link

# Open a shell in your PostgreSQL container
railway run --service postgres bash

# Install dependencies (inside container)
apt-get update
apt-get install -y git build-essential postgresql-server-dev-17

# Clone and build pgvector
cd /tmp
git clone --branch v0.7.0 https://github.com/pgvector/pgvector.git
cd pgvector
make clean
make
make install

# Restart PostgreSQL service in Railway dashboard
# Then connect and create extension:
railway run --service postgres psql

# In psql:
CREATE EXTENSION vector;
\dx vector
\q
```

## Option 4: Deploy Custom Dockerfile (Full Control)

Create a custom Dockerfile for PostgreSQL with pgvector:

```dockerfile
FROM postgres:17

# Install build dependencies
RUN apt-get update && \
    apt-get install -y \
        git \
        build-essential \
        postgresql-server-dev-17 && \
    rm -rf /var/lib/apt/lists/*

# Install pgvector
RUN cd /tmp && \
    git clone --branch v0.7.0 https://github.com/pgvector/pgvector.git && \
    cd pgvector && \
    make clean && \
    make OPTFLAGS="" && \
    make install && \
    rm -rf /tmp/pgvector

# Cleanup
RUN apt-get remove -y git build-essential && \
    apt-get autoremove -y
```

Then deploy to Railway:

1. Create a new service in Railway
2. Connect your GitHub repo with this Dockerfile
3. Railway will build and deploy automatically
4. Get the connection string from Railway dashboard

## Verification

After installation, verify pgvector is working:

```sql
-- Connect to your database
CREATE EXTENSION IF NOT EXISTS vector;

-- Check extension is available
SELECT * FROM pg_available_extensions WHERE name = 'vector';

-- Test vector operations
CREATE TABLE test_vectors (id serial PRIMARY KEY, embedding vector(3));
INSERT INTO test_vectors (embedding) VALUES ('[1,2,3]'), ('[4,5,6]');
SELECT embedding <-> '[3,3,3]' AS distance FROM test_vectors ORDER BY distance;
DROP TABLE test_vectors;
```

## Need Help?

- Railway Discord: https://discord.gg/railway
- Railway Docs: https://docs.railway.app/
- pgvector GitHub: https://github.com/pgvector/pgvector

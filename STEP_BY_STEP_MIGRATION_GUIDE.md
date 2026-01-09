# 🚀 Railway Database Migration - Step-by-Step Guide

## 📋 Current Status

✅ **Completed:**
- Schema successfully dumped from Supabase (22 tables)
- Railway database connection verified
- Superuser access confirmed
- All migration scripts created

❌ **Remaining:**
- Install pgvector extension on Railway
- Apply schema to Railway database
- Update application configuration

---

## 🎯 Choose Your Migration Path

### Path 1: Full Migration with pgvector (RECOMMENDED)

**Best if:** You want full feature parity with Supabase

**Steps:** Follow Section A below

### Path 2: Quick Migration with Railway Template

**Best if:** You want the easiest setup

**Steps:** Follow Section B below

### Path 3: Hybrid Setup

**Best if:** You want to keep Supabase for vectors only

**Steps:** Follow Section C below

---

## 📦 Section A: Full Migration with pgvector

### Step 1: Install pgvector on Railway

#### Option 1a: Using Railway CLI (Best Control)

```powershell
# Install Railway CLI
npm install -g @railway/cli

# Login to Railway
railway login

# Link to your project
railway link

# Open shell in PostgreSQL service
railway shell

# Inside the container, run:
apt-get update
apt-get install -y git build-essential postgresql-server-dev-17

cd /tmp
git clone --branch v0.7.0 https://github.com/pgvector/pgvector.git
cd pgvector
make clean
make
make install

# Exit the shell
exit
```

#### Option 1b: Using Railway Dashboard

1. Go to Railway Dashboard
2. Select your PostgreSQL service
3. Click "Settings" → "Deploy"
4. Restart the service after pgvector installation

### Step 2: Enable pgvector Extension

```powershell
# Connect to Railway database
railway run psql $DATABASE_URL

# Or use your connection string directly
# psql "postgresql://postgres:kaokwlxkPfvmQcTaKSUQupXwSmpmuBrK@interchange.proxy.rlwy.net:13100/railway"
```

```sql
-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify installation
SELECT * FROM pg_available_extensions WHERE name = 'vector';

-- You should see vector listed

-- Exit
\q
```

### Step 3: Run Migration Script

```powershell
cd "C:\Users\welcome 2\Downloads\chatbot\backend"

# Run the complete migration
python dump_and_migrate_schema.py
```

This will:
- ✅ Dump latest schema from Supabase
- ✅ Apply all 22 tables to Railway
- ✅ Create all indexes and functions
- ✅ Backup your .env file
- ✅ Update .env to use Railway
- ✅ Verify everything works

### Step 4: Verify Migration

```powershell
# Check tables were created
python check_railway_extensions.py
```

Or manually:
```sql
-- Connect to Railway database
psql "postgresql://postgres:kaokwlxkPfvmQcTaKSUQupXwSmpmuBrK@interchange.proxy.rlwy.net:13100/railway"

-- List all tables
\dt

-- Check vector extension
\dx

-- Test vector functionality
SELECT embedding FROM rag_embeddings LIMIT 1;

\q
```

### Step 5: Test Your Application

```powershell
# Start your backend
cd "C:\Users\welcome 2\Downloads\chatbot\backend"
python -m uvicorn app.main:app --reload

# Test endpoints
# - Chat functionality
# - Booking system
# - RAG search
# - Forms
```

---

## 📦 Section B: Quick Migration with Railway Template

### Step 1: Deploy pgvector Template

1. Go to https://railway.app/dashboard
2. Click "New Project"
3. Select "Deploy a Template"
4. Search for "PostgreSQL pgvector" or "pgvector"
5. Click "Deploy" on the pgvector template
6. Wait for deployment to complete

### Step 2: Get New Connection String

1. Click on the new PostgreSQL service
2. Go to "Connect" tab
3. Copy the "Database URL"
4. It will look like: `postgresql://postgres:xxxxx@xxx.railway.app:5432/railway`

### Step 3: Update Your Environment

```powershell
cd "C:\Users\welcome 2\Downloads\chatbot\backend"
```

Edit `.env` file:
```env
# Replace this line
SUPABASE_DB_DSN=postgresql://postgres.cnzcujahzcgvdrivovgb:callagent123@aws-1-ap-south-1.pooler.supabase.com:6543/postgres

# With your new Railway connection string
SUPABASE_DB_DSN=postgresql://postgres:YOUR_NEW_PASSWORD@YOUR_NEW_HOST.railway.app:5432/railway
```

### Step 4: Run Migration

```powershell
# Update the RAILWAY_DB_URL in dump_and_migrate_schema.py first
# Then run:
python dump_and_migrate_schema.py
```

---

## 📦 Section C: Hybrid Setup (Supabase for Vectors + Railway for Data)

This approach keeps embeddings on Supabase and moves everything else to Railway.

### Step 1: Modify Schema for Railway

Create `railway_hybrid_schema.sql` without rag_embeddings table:

```powershell
cd "C:\Users\welcome 2\Downloads\chatbot\backend"
```

Edit the `railway_complete_schema.sql` and remove the `rag_embeddings` table section.

### Step 2: Apply Modified Schema

```sql
-- Connect to Railway
psql "postgresql://postgres:kaokwlxkPfvmQcTaKSUQupXwSmpmuBrK@interchange.proxy.rlwy.net:13100/railway"

-- Run the modified schema
\i railway_hybrid_schema.sql

\q
```

### Step 3: Configure Dual Database Connections

Edit `.env`:
```env
# Supabase for RAG embeddings ONLY
SUPABASE_DB_DSN=postgresql://postgres.cnzcujahzcgvdrivovgb:callagent123@aws-1-ap-south-1.pooler.supabase.com:6543/postgres

# Railway for everything else
RAILWAY_DB_DSN=postgresql://postgres:kaokwlxkPfvmQcTaKSUQupXwSmpmuBrK@interchange.proxy.rlwy.net:13100/railway
```

### Step 4: Modify Application Code

Update `app/db.py`:

```python
import os
from app.config import settings

# Connection for RAG operations (Supabase)
def get_rag_conn():
    return psycopg.connect(settings.SUPABASE_DB_DSN, autocommit=True)

# Connection for regular operations (Railway)
def get_conn():
    railway_dsn = os.getenv("RAILWAY_DB_DSN", settings.SUPABASE_DB_DSN)
    return psycopg.connect(railway_dsn, autocommit=True)
```

---

## 🔍 Verification Checklist

After completing migration:

### Database Verification
- [ ] pgvector extension installed and working
- [ ] All 22 tables created in Railway
- [ ] Sample data can be inserted
- [ ] Indexes are created
- [ ] Functions are working

### Application Verification
- [ ] Backend starts without errors
- [ ] RAG search returns results
- [ ] Chat functionality works
- [ ] Booking creation works
- [ ] Forms can be submitted
- [ ] Calendar integration works

### Connection Verification
```powershell
# Test Railway connection
python -c "import psycopg; conn = psycopg.connect('postgresql://postgres:kaokwlxkPfvmQcTaKSUQupXwSmpmuBrK@interchange.proxy.rlwy.net:13100/railway'); print('✓ Connected to Railway')"

# Test vector extension
python -c "import psycopg; conn = psycopg.connect('postgresql://postgres:kaokwlxkPfvmQcTaKSUQupXwSmpmuBrK@interchange.proxy.rlwy.net:13100/railway'); cur = conn.cursor(); cur.execute('SELECT extname FROM pg_extension WHERE extname = %s', ('vector',)); print('✓ Vector extension:', cur.fetchone())"
```

---

## 📁 Files Reference

### Created by Migration Tools
| File | Purpose |
|------|---------|
| `railway_complete_schema.sql` | Complete schema dump from Supabase |
| `dump_and_migrate_schema.py` | Main migration automation script |
| `check_railway_extensions.py` | Check available PostgreSQL extensions |
| `setup_pgvector_railway.py` | pgvector installation helper |
| `RAILWAY_PGVECTOR_SETUP.md` | Detailed pgvector installation guide |
| `install_pgvector_railway.sql` | SQL commands for pgvector setup |
| `railway_schema_without_vector.sql` | Alternative schema using JSONB |
| `.env.backup` | Backup of original configuration |

### Documentation
| File | Description |
|------|-------------|
| `MIGRATION_FINAL_SUMMARY.md` | Complete migration summary |
| `RAILWAY_MIGRATION_README.md` | Overview and options |
| This file | Step-by-step instructions |

---

## 🆘 Troubleshooting

### Issue: "extension 'vector' is not available"

**Solution:** pgvector is not installed. Follow Section A, Step 1.

### Issue: "permission denied to create extension"

**Solution:** You need superuser access. We verified you have it, so try:
```sql
-- Connect as postgres user (superuser)
CREATE EXTENSION vector;
```

### Issue: Migration script fails partway through

**Solution:** 
1. Check Railway database logs
2. Look for specific error in terminal output
3. You can apply schema manually:
```powershell
psql "postgresql://postgres:kaokwlxkPfvmQcTaKSUQupXwSmpmuBrK@interchange.proxy.rlwy.net:13100/railway" -f railway_complete_schema.sql
```

### Issue: Application can't connect after migration

**Solution:**
1. Verify .env has correct DATABASE_URL
2. Check that SUPABASE_DB_DSN points to Railway:
```env
SUPABASE_DB_DSN=postgresql://postgres:kaokwlxkPfvmQcTaKSUQupXwSmpmuBrK@interchange.proxy.rlwy.net:13100/railway
```
3. Restart your application

### Issue: RAG search doesn't work

**Solution:**
1. Verify vector extension is installed:
```sql
SELECT * FROM pg_extension WHERE extname = 'vector';
```
2. Check rag_embeddings table exists and has vector column:
```sql
\d rag_embeddings
```

---

## 📞 Support Resources

- **Railway Discord:** https://discord.gg/railway
- **pgvector GitHub:** https://github.com/pgvector/pgvector
- **Railway Docs:** https://docs.railway.app/
- **PostgreSQL Docs:** https://www.postgresql.org/docs/

---

## ⚡ Quick Command Reference

```powershell
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Link project
railway link

# Open database shell
railway run psql

# Run Python migration
python dump_and_migrate_schema.py

# Check extensions
python check_railway_extensions.py

# Start backend
cd backend
python -m uvicorn app.main:app --reload
```

---

## ✅ Success Criteria

Your migration is complete when:

1. ✅ Railway PostgreSQL has pgvector extension
2. ✅ All 22 tables are created in Railway
3. ✅ Application starts without database errors
4. ✅ Chat with RAG works (searches embeddings)
5. ✅ Bookings can be created
6. ✅ Forms can be submitted
7. ✅ No connection errors in logs

---

## 🎯 Recommended Next Step

**Start with Section A (Full Migration with pgvector)** 

This gives you:
- ✅ Complete feature parity with Supabase
- ✅ Best performance for vector search
- ✅ No code changes needed
- ✅ Single database to manage

Good luck with your migration! 🚀

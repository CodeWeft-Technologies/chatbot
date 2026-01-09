# 🎯 Railway Migration - Complete Guide

## 🚀 RECOMMENDED: Use Railway's pgvector Template

Railway provides an **official pgvector template** - this is the easiest and best approach!

---

## ⚡ Quick Start (5 Minutes)

### 1️⃣ Deploy pgvector Template

**Go to Railway Dashboard:**
👉 https://railway.app/dashboard

**Deploy pgvector:**
- Click **"+ New"** → **"Database"** → **"Add PostgreSQL"**
- Or search **"pgvector"** in templates
- Click **"Deploy"**

### 2️⃣ Get Connection String

- Click on PostgreSQL service
- Go to **"Connect"** tab
- Copy **"Postgres Connection URL"**

### 3️⃣ Update Migration Scripts

```powershell
cd "C:\Users\welcome 2\Downloads\chatbot\backend"
python update_railway_url.py
```

Paste your new connection string when prompted.

### 4️⃣ Run Migration

```powershell
python dump_and_migrate_schema.py
```

✅ Done! All 22 tables migrated with pgvector support.

---

## 📁 All Files Created for You

### 🎯 Start Here (Pick ONE)
1. **`EASIEST_MIGRATION_PATH.md`** ⭐ **RECOMMENDED** - Use Railway's template
2. `STEP_BY_STEP_MIGRATION_GUIDE.md` - Detailed manual installation guide

### 🛠️ Migration Tools
- `dump_and_migrate_schema.py` - Main migration script
- `update_railway_url.py` - Quick URL updater
- `railway_complete_schema.sql` - Full schema (22 tables)

### ✅ Verification Tools
- `check_railway_extensions.py` - Check available extensions
- `setup_pgvector_railway.py` - pgvector setup helper

### 📚 Reference Documentation
- `RAILWAY_MIGRATION_README.md` - Migration overview
- `MIGRATION_FINAL_SUMMARY.md` - What was accomplished
- `RAILWAY_PGVECTOR_SETUP.md` - Manual installation guide

### 🔧 Alternative Approaches
- `railway_schema_without_vector.sql` - JSONB-based schema
- `install_pgvector_railway.sql` - Manual installation SQL

---

## 📊 What Gets Migrated

### All 22 Tables:
✅ **Core Tables**
- organizations, users, app_users
- organization_users, chatbots

✅ **RAG & Embeddings** (requires pgvector)
- rag_embeddings (vector(1024))

✅ **Conversations**
- conversations, conversation_history

✅ **Dynamic Forms**
- form_configurations, form_fields
- form_templates

✅ **Booking System**
- bookings, booking_resources
- resource_schedules

✅ **Calendar Integration**
- bot_calendar_oauth
- bot_calendar_settings
- bot_appointments
- bot_booking_settings

✅ **Audit & Notifications**
- booking_audit_logs
- booking_notifications

✅ **Analytics & Sales**
- bot_usage_daily, leads

### Plus:
- ✅ All indexes optimized for performance
- ✅ All PostgreSQL functions
- ✅ Vector similarity search (cosine distance)
- ✅ Capacity checking functions
- ✅ Time slot availability functions

---

## 🔐 Your Database URLs

### Supabase (Source - Current)
```
postgresql://postgres.cnzcujahzcgvdrivovgb:callagent123@aws-1-ap-south-1.pooler.supabase.com:6543/postgres
```

### Railway (Target - Old Instance)
```
postgresql://postgres:kaokwlxkPfvmQcTaKSUQupXwSmpmuBrK@interchange.proxy.rlwy.net:13100/railway
```
⚠️ **This one does NOT have pgvector**

### Railway (Target - New pgvector Template)
```
You'll get this after deploying the pgvector template
Format: postgresql://postgres:xxxxx@xxxx.railway.app:5432/railway
```
✅ **This one HAS pgvector pre-installed**

---

## 🎯 Migration Paths Comparison

### Option 1: Railway pgvector Template (EASIEST) ⭐
- **Time:** 5 minutes
- **Complexity:** Very Easy
- **Steps:** 4
- **Pros:** 
  - ✅ pgvector pre-installed
  - ✅ No manual setup
  - ✅ Railway managed
  - ✅ Production ready
- **Best for:** Everyone

### Option 2: Manual pgvector Installation
- **Time:** 15-30 minutes  
- **Complexity:** Medium
- **Steps:** 8+
- **Pros:**
  - ✅ Full control
  - ✅ Use existing database
- **Best for:** Advanced users who need custom config

### Option 3: Alternative (No pgvector)
- **Time:** 10 minutes
- **Complexity:** Medium
- **Pros:**
  - ✅ Works immediately
  - ✅ No pgvector needed
- **Cons:**
  - ❌ Slower vector search
  - ❌ Application code changes required
- **Best for:** Testing or non-production

### Option 4: Hybrid (Supabase + Railway)
- **Time:** 10 minutes
- **Complexity:** Medium
- **Pros:**
  - ✅ Keep Supabase for embeddings
  - ✅ Use Railway for other data
- **Cons:**
  - ❌ Two databases to manage
  - ❌ Application code changes required
- **Best for:** Gradual migration

---

## ✅ Post-Migration Checklist

### Database Verification
```powershell
# Connect to Railway
psql "YOUR_NEW_RAILWAY_URL"

# Check tables
\dt

# Verify pgvector
SELECT * FROM pg_extension WHERE extname = 'vector';

# Check sample table
\d rag_embeddings

# Exit
\q
```

### Application Testing
```powershell
# Start backend
cd "C:\Users\welcome 2\Downloads\chatbot\backend"
python -m uvicorn app.main:app --reload

# Test endpoints:
# - Chat: http://localhost:8000/api/chat
# - Bookings: http://localhost:8000/api/bookings
# - Forms: http://localhost:8000/api/forms
```

### Functionality Checks
- [ ] Backend starts without errors
- [ ] RAG search returns results
- [ ] Embeddings table has vector type
- [ ] Chat responses work
- [ ] Booking creation works
- [ ] Form submissions work
- [ ] Calendar integration works
- [ ] No database errors in logs

---

## 🆘 Common Issues & Solutions

### Issue: "Can't find pgvector template"
**Solution:** In Railway dashboard, go to Templates → Search "pgvector"

### Issue: Migration fails on vector extension
**Solution:** Ensure you deployed the **pgvector template**, not regular PostgreSQL

### Issue: Application can't connect
**Solution:** 
1. Check .env has correct SUPABASE_DB_DSN
2. Verify Railway service is running
3. Test connection: `python check_railway_extensions.py`

### Issue: RAG search not working
**Solution:**
1. Verify vector extension: `SELECT extname FROM pg_extension;`
2. Check rag_embeddings table exists
3. Verify embedding column type: `\d rag_embeddings`

---

## 📞 Support & Resources

- **Railway Discord:** https://discord.gg/railway
- **Railway Docs:** https://docs.railway.app/databases/postgresql
- **pgvector GitHub:** https://github.com/pgvector/pgvector
- **Railway Templates:** https://railway.app/templates

---

## 🎊 You're All Set!

You now have:
- ✅ Complete schema dumped from Supabase
- ✅ Migration scripts ready to run
- ✅ Multiple migration options available
- ✅ Verification and testing tools
- ✅ Comprehensive documentation

**Next step:** Deploy the pgvector template and run the migration!

**Estimated total time:** 5-10 minutes 🚀

---

## 📋 Quick Command Reference

```powershell
# Update Railway URL after deploying pgvector template
python update_railway_url.py

# Run complete migration
python dump_and_migrate_schema.py

# Verify extensions
python check_railway_extensions.py

# Start application
python -m uvicorn app.main:app --reload

# Connect to Railway database
psql "YOUR_RAILWAY_URL"
```

---

**Ready? Start here:** 👉 `EASIEST_MIGRATION_PATH.md`

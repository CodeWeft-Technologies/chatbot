#!/usr/bin/env python3
from app.routes.ingest import router

print("Testing route registration...")
routes = [r.path for r in router.routes]
ingest_routes = [r for r in routes if 'ingest' in r]

print(f"\nIngest routes found: {len(ingest_routes)}")
for route in ingest_routes:
    print(f"  {route}")

status_route = [r for r in ingest_routes if 'status' in r]
if status_route:
    print(f"\n✅ Status endpoint found: {status_route}")
else:
    print(f"\n❌ Status endpoint NOT found!")
    print(f"\nAll routes: {routes}")

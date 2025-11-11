#!/usr/bin/env python3
"""
Quick diagnostic script to check BESH setup
"""
import os
import sys
from pathlib import Path

def check_env_file():
    """Check if .env file exists and has required values"""
    env_path = Path(".env")
    if not env_path.exists():
        print("❌ .env file NOT found!")
        print("   Create one with:")
        print("   BESH_API_BASE=https://api.nebius.ai/v1")
        print("   BESH_API_KEY=your_key")
        print("   BESH_DATABASE_URL=postgresql+psycopg://besh:besh_password@localhost:5432/batch")
        return False
    
    print("✅ .env file found")
    
    # Try to load it
    from dotenv import load_dotenv
    load_dotenv()
    
    required_vars = {
        "BESH_API_BASE": os.getenv("BESH_API_BASE"),
        "BESH_API_KEY": os.getenv("BESH_API_KEY"),
        "BESH_DATABASE_URL": os.getenv("BESH_DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI"),
    }
    
    all_good = True
    for var, value in required_vars.items():
        if value:
            # Mask sensitive values
            if "KEY" in var or "PASSWORD" in var:
                display = value[:10] + "..." if len(value) > 10 else "***"
            else:
                display = value
            print(f"✅ {var}={display}")
        else:
            print(f"❌ {var} not set!")
            all_good = False
    
    return all_good

def check_database():
    """Check if PostgreSQL is accessible"""
    print("\n🔍 Checking PostgreSQL connection...")
    
    db_url = os.getenv("BESH_DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI")
    if not db_url:
        print("❌ Database URL not set")
        return False
    
    try:
        import asyncpg
        import asyncio
        import urllib.parse
        
        parsed = urllib.parse.urlparse(db_url)
        
        async def test_conn():
            try:
                conn = await asyncpg.connect(
                    host=parsed.hostname,
                    port=parsed.port or 5432,
                    user=parsed.username,
                    password=parsed.password,
                    database=parsed.path.lstrip("/"),
                    timeout=5
                )
                await conn.close()
                return True
            except Exception as e:
                print(f"❌ Database connection failed: {e}")
                return False
        
        result = asyncio.run(test_conn())
        if result:
            print(f"✅ Database connection successful")
            print(f"   Host: {parsed.hostname}:{parsed.port or 5432}")
            print(f"   Database: {parsed.path.lstrip('/')}")
        return result
        
    except ImportError:
        print("⚠️  asyncpg not installed, skipping database check")
        return None
    except Exception as e:
        print(f"❌ Error checking database: {e}")
        return False

def check_redis():
    """Check if Redis is accessible"""
    print("\n🔍 Checking Redis connection...")
    
    redis_url = os.getenv("BESH_REDIS_URL") or os.getenv("REDIS_URL") or "redis://localhost:6379"
    
    try:
        import redis
        
        r = redis.from_url(redis_url, decode_responses=True)
        r.ping()
        print(f"✅ Redis connection successful")
        print(f"   URL: {redis_url}")
        return True
        
    except ImportError:
        print("⚠️  redis not installed, skipping Redis check")
        return None
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        print(f"   Make sure Redis is running: docker-compose -f docker-compose.infra.yml up -d redis")
        return False

def main():
    print("=" * 60)
    print("BESH Setup Diagnostic")
    print("=" * 60)
    
    # Load .env first
    from dotenv import load_dotenv
    load_dotenv()
    
    # Check .env file
    print("\n📋 Checking .env configuration...")
    env_ok = check_env_file()
    
    # Check database
    db_ok = check_database()
    
    # Check Redis
    redis_ok = check_redis()
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)
    
    if env_ok and db_ok and redis_ok:
        print("✅ All checks passed! You're ready to run:")
        print("   besh serve --host 0.0.0.0 --port 8080")
    else:
        print("❌ Some checks failed. Please fix the issues above.")
        
        if not db_ok:
            print("\n💡 To start PostgreSQL:")
            print("   docker-compose -f docker-compose.infra.yml up -d postgres")
        
        if not redis_ok:
            print("\n💡 To start Redis:")
            print("   docker-compose -f docker-compose.infra.yml up -d redis")
        
        sys.exit(1)

if __name__ == "__main__":
    main()


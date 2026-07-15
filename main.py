import os
import sys
from dotenv import load_dotenv
from app.logger import logger
from app.sync import run_sync

def main():
    # Force UTF-8 output encoding for compatibility with all consoles
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    # Load environment variables from .env file if it exists
    load_dotenv()

    # Read configuration
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    admin_secret_token = os.getenv("ADMIN_SECRET_TOKEN")
    
    default_m3u_url = "https://raw.githubusercontent.com/srhady/tapmad-bd/refs/heads/main/tapmad_bd.m3u"
    m3u_url = os.getenv("M3U_URL", default_m3u_url)
    category_id = os.getenv("CATEGORY_ID", "test-category")
    check_channels = os.getenv("CHECK_CHANNELS", "false").lower() in ("true", "1", "yes")

    # Validate required credentials
    has_errors = False
    if not supabase_url:
        logger.error("[error]Error: SUPABASE_URL environment variable is not set.[/error]")
        has_errors = True
    if not supabase_key:
        logger.error("[error]Error: SUPABASE_SERVICE_ROLE_KEY environment variable is not set.[/error]")
        has_errors = True
        
    if has_errors:
        logger.error("Please set the missing variables in your environment or a .env file.")
        sys.exit(1)

    logger.info("==================================================")
    logger.info("     Starting M3U to Supabase Sync Service        ")
    logger.info("==================================================")
    logger.info(f"Target Category: [sync]{category_id}[/sync]")
    if check_channels:
        logger.info("Channel Check Mode: [sync]ENABLED[/sync]")
    
    # Save the hash file in the same directory as main.py
    script_dir = os.path.dirname(os.path.abspath(__file__))
    hash_filename = os.getenv("HASH_FILE", "last_hash.txt")
    hash_file_path = os.path.join(script_dir, hash_filename)

    # Execute synchronization
    success = run_sync(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
        m3u_url=m3u_url,
        category_id=category_id,
        hash_file_path=hash_file_path,
        admin_secret_token=admin_secret_token,
        check_channels=check_channels
    )

    if success:
        logger.info("Sync execution finished successfully.")
        sys.exit(0)
    else:
        logger.error("Sync execution failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()

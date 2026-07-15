import os
import time
import requests
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log
from app.logger import logger, console
from app.parser import parse_m3u_playlist
from app.importer import SupabaseImporter
from app.utils import calculate_sha256, get_last_hash, save_last_hash

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=16),
    before_sleep=before_sleep_log(logger, 20),
    reraise=True
)
def download_playlist(url: str) -> str:
    """
    Downloads the M3U playlist content from the given URL.
    Retries up to 5 times on failure with exponential backoff.
    """
    logger.info(f"Downloading playlist from: [download]{url}[/download]...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    
    content = response.text
    if not content:
        raise ValueError("Downloaded playlist content is empty.")
    
    logger.info(f"[success]Successfully downloaded playlist[/success] ({len(content.encode('utf-8'))} bytes).")
    return content

def run_sync(
    supabase_url: str,
    supabase_key: str,
    m3u_url: str,
    category_id: str,
    hash_file_path: str = "last_hash.txt",
    admin_secret_token: Optional[str] = None,
    check_channels: bool = False
) -> bool:
    """
    Orchestrates the entire synchronization flow.
    Returns True if execution completes successfully, False otherwise.
    """
    start_time = time.time()
    
    try:
        # Step 1: Download M3U playlist
        try:
            m3u_content = download_playlist(m3u_url)
        except requests.exceptions.RequestException as e:
            logger.error(f"[error]Failed to download M3U playlist from GitHub:[/error] {e}")
            logger.error("Please verify the M3U_URL and check your internet connection.")
            return False
        except Exception as e:
            logger.error(f"[error]Unexpected error during M3U download:[/error] {e}")
            return False

        # Step 2: Hash Check
        current_hash = calculate_sha256(m3u_content)
        last_hash = get_last_hash(hash_file_path)
        
        logger.info(f"Current Playlist SHA256: [info]{current_hash[:8]}...[/info]")
        if last_hash:
            logger.info(f"Last Playlist SHA256:    [info]{last_hash[:8]}...[/info]")
        
        if last_hash == current_hash and not check_channels:
            logger.info("[success]Playlist hash is unchanged. Database is already in sync. Exiting early.[/success]")
            duration = time.time() - start_time
            logger.info(f"Sync duration: {duration:.2f} seconds.")
            return True
        elif last_hash == current_hash and check_channels:
            logger.info("[info]Playlist hash is unchanged, but CHECK_CHANNELS is active. Bypassing early exit to verify channel status.[/info]")
            
        # Step 3: Parse Channels
        try:
            local_channels = parse_m3u_playlist(m3u_content, default_category=category_id)
        except Exception as e:
            logger.error(f"[error]Failed to parse M3U playlist:[/error] {e}")
            return False
            
        if not local_channels:
            logger.warning("[warning]Parsed playlist did not yield any valid channels. Aborting database sync.[/warning]")
            return False

        # Step 3.5: Filter Working Channels if check_channels is enabled
        if check_channels:
            import asyncio
            from app.checker import filter_working_channels
            try:
                local_channels = asyncio.run(filter_working_channels(local_channels))
            except Exception as e:
                logger.error(f"[error]Failed running the channel availability checker:[/error] {e}")
                return False
                
            if not local_channels:
                logger.warning("[warning]No working channels found after checking. Aborting database sync to avoid clearing the database.[/warning]")
                return False

        # Step 4: Supabase sync
        try:
            importer = SupabaseImporter(
                supabase_url=supabase_url,
                supabase_key=supabase_key,
                category_id=category_id,
                admin_secret_token=admin_secret_token
            )
            
            # Step 4a: Verify/Create Category
            importer.verify_or_create_category()
            
            # Step 4b: Compare and Sync (Insert, Update, Delete)
            inserted, updated, deleted = importer.sync_channels(local_channels)
            
        except ValueError as e:
            logger.error(f"[error]Configuration Error:[/error] {e}")
            return False
        except Exception as e:
            logger.error(f"[error]Supabase Database Sync Error:[/error] {e}")
            logger.error("Please check your SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, and table definitions.")
            return False

        # Step 5: Save new hash
        save_last_hash(hash_file_path, current_hash)

        # Step 6: Log summary
        duration = time.time() - start_time
        logger.info("")
        console.print("[success]==================================================[/success]")
        console.print(f"[success]  Sync Completed Successfully!  [/success]")
        console.print(f"  - Inserted: [bold green]{inserted}[/bold green]")
        console.print(f"  - Updated:  [bold yellow]{updated}[/bold yellow]")
        console.print(f"  - Deleted:  [bold red]{deleted}[/bold red]")
        console.print(f"  - Duration: [bold cyan]{duration:.2f} seconds[/bold cyan]")
        console.print("[success]==================================================[/success]")
        
        return True

    except Exception as e:
        logger.error(f"[error]An unexpected global error occurred in sync service:[/error] {e}", exc_info=True)
        return False

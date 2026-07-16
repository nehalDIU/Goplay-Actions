import aiohttp
import asyncio
import m3u8
from typing import List, Optional
from app.models import Channel
from app.logger import logger

async def check_segment(session: aiohttp.ClientSession, segment_url: str, headers: dict) -> bool:
    """Checks if a segment is accessible (returns HTTP 200)."""
    try:
        async with session.get(segment_url, headers=headers, timeout=5) as response:
            if response.status == 200:
                return True
            else:
                logger.warning(f"Segment {segment_url} is not available. Status code: {response.status}")
                return False
    except Exception as e:
        logger.error(f"Error checking segment {segment_url}: {e}")
        return False

async def check_nested_playlist(session: aiohttp.ClientSession, playlist_url: str, headers: dict) -> bool:
    """Checks if a nested playlist is accessible (returns HTTP 200)."""
    try:
        async with session.get(playlist_url, headers=headers, timeout=5) as response:
            if response.status == 200:
                return True
            else:
                logger.warning(f"Nested playlist {playlist_url} is not available. Status code: {response.status}")
                return False
    except Exception as e:
        logger.error(f"Error checking nested playlist {playlist_url}: {e}")
        return False

async def check_channel_availability(
    session: aiohttp.ClientSession, 
    channel: Channel, 
    semaphore: asyncio.Semaphore
) -> Optional[Channel]:
    """
    Checks if an individual channel is working.
    Returns the channel object if working, or None if offline/broken.
    """
    async with semaphore:
        url = channel.stream_url
        headers = {
            "User-Agent": "IPTV"
        }
        try:
            # First check headers/connection
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    content_type = response.headers.get("Content-Type", "").lower()
                    is_playlist = (
                        "mpegurl" in content_type or 
                        "x-mpegurl" in content_type or 
                        url.split('?')[0].split('#')[0].endswith('.m3u8')
                    )

                    if is_playlist:
                        playlist_content = await response.text(errors='ignore')
                        try:
                            m3u_playlist = m3u8.loads(playlist_content, uri=url)
                        except Exception as parse_err:
                            logger.warning(f"Failed to parse M3U8 content for {channel.name} ({url}): {parse_err}")
                            # Fallback: assume it works since status is 200
                            return channel

                        if m3u_playlist.segments:
                            # If there are segments, check the first segment
                            segment_url = m3u_playlist.segments[0].absolute_uri
                            if await check_segment(session, segment_url, headers):
                                logger.info(f"Channel {channel.name} ({url}) is available with segments.")
                                return channel
                            else:
                                logger.warning(f"Channel {channel.name} ({url}) has no working segments.")
                                return None
                        elif m3u_playlist.playlists:
                            # If there are nested playlists, check them
                            for p in m3u_playlist.playlists:
                                nested_playlist_url = p.absolute_uri
                                if await check_nested_playlist(session, nested_playlist_url, headers):
                                    logger.info(f"Channel {channel.name} ({url}) is available with nested playlists.")
                                    return channel
                            logger.warning(f"Channel {channel.name} ({url}) has no working nested playlists.")
                            return None
                        else:
                            # Direct stream or empty playlist
                            logger.info(f"Channel {channel.name} ({url}) is a direct stream (M3U8 but no segments/nested).")
                            return channel
                    else:
                        # Direct stream (e.g. mp4, ts, etc.)
                        logger.info(f"Channel {channel.name} ({url}) is a direct stream (non-M3U8).")
                        return channel
                else:
                    logger.warning(f"Channel {channel.name} ({url}) is not available. Status code: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error checking channel {channel.name} ({url}): {e}")
            return None

async def filter_working_channels(channels: List[Channel], concurrency: int = 100) -> List[Channel]:
    """Runs concurrent checks on all channels and returns only the working ones."""
    logger.info(f"Checking availability of {len(channels)} channels with concurrency={concurrency}...")
    semaphore = asyncio.Semaphore(concurrency)
    
    connector = aiohttp.TCPConnector(limit=concurrency, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [check_channel_availability(session, channel, semaphore) for channel in channels]
        results = await asyncio.gather(*tasks)
        
    working_channels = [ch for ch in results if ch is not None]
    logger.info(f"Channel check completed: {len(working_channels)}/{len(channels)} channels are working.")
    return working_channels

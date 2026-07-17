import re
import base64
from urllib.parse import urlparse, parse_qs
from typing import List, Dict, Tuple, Optional
from app.models import Channel
from app.logger import logger

def decode_base64_url(url: str) -> str:
    """
    Decodes the 'stream' base64 query parameter if present.
    Returns the decoded URL if valid, otherwise the original URL.
    """
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        stream_param = qs.get("stream")
        if not stream_param:
            return url
        
        val = stream_param[0]
        # Add padding if needed
        missing_padding = len(val) % 4
        if missing_padding:
            val += '=' * (4 - missing_padding)
            
        decoded = base64.b64decode(val).decode('utf-8', errors='ignore')
        if decoded.startswith('http://') or decoded.startswith('https://') or decoded.startswith('rtmp://') or decoded.startswith('rtsp://'):
            return decoded
    except Exception:
        pass
    return url

# Regex to parse key="value" or key=value attributes
ATTRIB_PATTERN = re.compile(r'([a-zA-Z0-9_-]+)="([^"]*)"|([a-zA-Z0-9_-]+)=([^\s,]*)')

def split_extinf_line(line: str) -> Tuple[str, str]:
    """
    Splits the #EXTINF line into the attributes part and the channel name part.
    Accounts for commas that might appear within quoted attribute values.
    
    Example:
        #EXTINF:-1 tvg-id="123" tvg-logo="url",Channel Name
        returns:
        ('#EXTINF:-1 tvg-id="123" tvg-logo="url"', 'Channel Name')
    """
    in_quotes = False
    for i, char in enumerate(line):
        if char == '"':
            in_quotes = not in_quotes
        elif char == ',' and not in_quotes:
            return line[:i].strip(), line[i+1:].strip()
            
    # Fallback: split by the last comma if no comma is found outside quotes
    parts = line.rsplit(",", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return line.strip(), ""

def parse_attributes(attributes_part: str) -> Dict[str, str]:
    """
    Parses key=value attributes from the attributes part of a #EXTINF line.
    Handles both double-quoted and unquoted values.
    """
    attributes = {}
    matches = ATTRIB_PATTERN.findall(attributes_part)
    for match in matches:
        if match[0]:  # key="value" pattern
            attributes[match[0]] = match[1]
        elif match[2]:  # key=value pattern
            attributes[match[2]] = match[3]
    return attributes
def generate_id_from_url_and_title(stream_url: str, title: str, category: Optional[str] = None) -> str:
    """
    Generates a unique channel ID when tvg-id is missing.
    For the 'fancode' category (and as a fallback), it prioritizes slugifying the channel title
    first to ensure the ID remains stable even when stream URLs change.
    Otherwise, it extracts from the URL first, with a fallback to the title.
    """
    # 1. For fancode, prioritize the slugified title to ensure stability
    if category == "fancode":
        if title:
            clean_title = re.sub(r'[^a-zA-Z0-9\s-]', '', title).strip().lower()
            clean_title = re.sub(r'[-\s]+', '-', clean_title)
            if clean_title:
                return f"fancode-{clean_title}"

    # 2. Try to extract filename from URL
    try:
        path = stream_url.split('?')[0].split('#')[0]
        filename = path.split('/')[-1]
        if '.' in filename:
            name_part = '.'.join(filename.split('.')[:-1])
        else:
            name_part = filename
            
        clean_id = re.sub(r'[^a-zA-Z0-9_-]', '', name_part).strip().lower()
        # Ensure it's a reasonable ID and not too generic
        generic_names = {"master", "index", "playlist", "live", "stream", "chunklist", "play"}
        if clean_id and len(clean_id) > 2 and clean_id not in generic_names:
            return clean_id
    except Exception:
        pass
        
    # 3. Fallback: Slugify the title
    clean_title = re.sub(r'[^a-zA-Z0-9\s-]', '', title).strip().lower()
    clean_title = re.sub(r'[-\s]+', '-', clean_title)
    if not clean_title:
        import hashlib
        clean_title = f"channel-{hashlib.md5(title.encode('utf-8')).hexdigest()[:8]}"
    return clean_title

def parse_m3u_playlist(content: str, default_category: str = "test-category") -> List[Channel]:
    """
    Parses the M3U playlist content and returns a list of valid Channel models.
    Filters out comments, invalid lines, empty lines, and duplicate channel IDs.
    """
    lines = content.splitlines()
    channels: List[Channel] = []
    seen_ids = set()
    
    current_channel_info: Optional[Dict[str, any]] = None
    sort_order_counter = 1

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
            
        # If it's a comment or metadata line
        if line.startswith("#"):
            if line.startswith("#EXTINF:"):
                # Parse previous unfinished channel if any (missing URL)
                if current_channel_info:
                    logger.warning(
                        f"Line {line_num}: Found new #EXTINF before URL for channel "
                        f"'{current_channel_info.get('name')}'. Skipping invalid entry."
                    )
                    current_channel_info = None
                
                # Split attributes and title
                attrib_str, title = split_extinf_line(line)
                attrs = parse_attributes(attrib_str)
                
                tvg_id = attrs.get("tvg-id")
                tvg_logo = attrs.get("tvg-logo")
                
                if not title:
                    logger.warning(f"Line {line_num}: Missing channel title in #EXTINF. Skipping line: {line}")
                    continue
                
                current_channel_info = {
                    "id": tvg_id,
                    "name": title,
                    "logo": tvg_logo,
                    "line_num": line_num
                }
            else:
                # Other comment or metadata line, e.g. #EXTM3U, ignore
                continue
        else:
            # This is a stream URL line
            if current_channel_info:
                # Decode base64 stream URL if present
                resolved_url = decode_base64_url(line)
                channel_id = current_channel_info["id"]
                
                # Validate stream URL
                if not (resolved_url.startswith("http://") or resolved_url.startswith("https://") or resolved_url.startswith("rtmp://") or resolved_url.startswith("rtsp://")):
                    logger.warning(
                        f"Line {line_num}: Invalid stream URL '{resolved_url}' for channel "
                        f"'{current_channel_info['name']}'. Skipping."
                    )
                    current_channel_info = None
                    continue
                
                if not channel_id:
                    channel_id = generate_id_from_url_and_title(resolved_url, current_channel_info["name"], category=default_category)
                
                # Check for duplicate IDs and resolve by appending suffix if needed
                if channel_id in seen_ids:
                    base_id = channel_id
                    counter = 1
                    while f"{base_id}-{counter}" in seen_ids:
                        counter += 1
                    channel_id = f"{base_id}-{counter}"
                    logger.warning(
                        f"Line {line_num}: Duplicate 'tvg-id' '{base_id}' resolved as '{channel_id}' for channel '{current_channel_info['name']}'."
                    )
                
                # Create Channel object with defaults
                channel = Channel(
                    id=channel_id,
                    name=current_channel_info["name"],
                    logo=current_channel_info["logo"] if current_channel_info["logo"] else None,
                    category=default_category,
                    stream_url=resolved_url,
                    sort_order=sort_order_counter,
                    # All other fields defaults are populated from Channel dataclass defaults
                )
                
                channels.append(channel)
                seen_ids.add(channel_id)
                sort_order_counter += 1
                current_channel_info = None
            else:
                # Received URL without matching #EXTINF
                logger.warning(f"Line {line_num}: Found URL '{line}' without preceding #EXTINF. Skipping.")
    # Final check in case last #EXTINF did not have a URL
    if current_channel_info:
        logger.warning(
            f"End of file: Missing URL for channel "
            f"'{current_channel_info.get('name')}'. Skipping."
        )

    logger.info(f"Successfully parsed [parse]{len(channels)}[/parse] valid channels from M3U playlist.")
    return channels

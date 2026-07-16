import os
import sys
import base64
import requests
import argparse
from urllib.parse import urlparse, parse_qs

def decode_base64_url(url):
    """
    Decodes the 'stream' base64 query parameter if present.
    Returns the decoded URL if valid, otherwise None.
    """
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        stream_param = qs.get("stream")
        if not stream_param:
            return None
        
        val = stream_param[0]
        # Add padding if needed
        missing_padding = len(val) % 4
        if missing_padding:
            val += '=' * (4 - missing_padding)
            
        decoded = base64.b64decode(val).decode('utf-8', errors='ignore')
        if decoded.startswith('http://') or decoded.startswith('https://'):
            return decoded
    except Exception:
        pass
    return None

def resolve_redirect(url, headers):
    """
    Resolves the URL via a request to check for redirection.
    Returns the final redirected URL.
    """
    try:
        # We do not want to download the whole stream, so we check headers with allow_redirects=False
        r = requests.get(url, headers=headers, stream=True, allow_redirects=False, timeout=10)
        if r.status_code in (301, 302, 303, 307, 308) and 'Location' in r.headers:
            return r.headers['Location']
    except Exception as e:
        print(f"Warning: Failed to resolve redirect for {url}: {e}", file=sys.stderr)
    return url

def main():
    parser = argparse.ArgumentParser(description="Resolve protected and redirected M3U IPTV playlist links.")
    parser.add_argument("--url", required=True, help="URL of the protected M3U playlist.")
    parser.add_argument("--output", required=True, help="Output path for the clean resolved M3U playlist file.")
    parser.add_argument("--resolve-all", action="store_true", help="Attempt to make HTTP requests to resolve all non-base64 redirect links.")
    
    args = parser.parse_args()
    
    headers = {
        "User-Agent": "IPTV"
    }
    
    print(f"Fetching playlist from: {args.url}...")
    try:
        r = requests.get(args.url, headers=headers, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"Error: Failed to fetch playlist: {e}", file=sys.stderr)
        sys.exit(1)
        
    lines = r.text.splitlines()
    if not lines or not lines[0].startswith("#EXTM3U"):
        print("Error: The downloaded content does not appear to be a valid M3U playlist.", file=sys.stderr)
        print(f"Sample response:\n{r.text[:300]}", file=sys.stderr)
        sys.exit(1)
        
    resolved_lines = []
    total_resolved = 0
    total_channels = 0
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
            
        if line.startswith("#EXTM3U"):
            resolved_lines.append(line)
            i += 1
            continue
            
        if line.startswith("#EXTINF") or line.startswith("#EXTVLCOPT") or line.startswith("#"):
            resolved_lines.append(line)
            i += 1
            continue
            
        # It's a stream URL
        stream_url = line
        total_channels += 1
        decoded_url = decode_base64_url(stream_url)
        
        if decoded_url:
            print(f"Resolved base64 stream URL: {decoded_url}")
            resolved_lines.append(decoded_url)
            total_resolved += 1
        elif args.resolve_all:
            # Try to resolve HTTP redirects dynamically
            print(f"Resolving HTTP redirect for: {stream_url}...")
            resolved_url = resolve_redirect(stream_url, headers)
            if resolved_url != stream_url:
                print(f"  -> Redirected to: {resolved_url}")
                resolved_lines.append(resolved_url)
                total_resolved += 1
            else:
                resolved_lines.append(stream_url)
        else:
            resolved_lines.append(stream_url)
            
        i += 1
        
    print(f"Saving resolved playlist to: {args.output}...")
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(resolved_lines) + "\n")
        print(f"Successfully processed {total_channels} channels. Resolved {total_resolved} links.")
    except Exception as e:
        print(f"Error: Failed to save output file: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

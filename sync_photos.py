#!/usr/bin/env python3
"""
-----------------------------------------------------------------
sync_photos.py
Lightweight, zero-dependency photo indexer for the Family Command Center.
Scans a target directory, extracts dimensions/aspect-ratios in pure Python,
and outputs a metadata object array to 'photos.json'.
-----------------------------------------------------------------
"""
import os
import json
import sys
import struct
import argparse

def get_image_info(filepath):
    """
    Parses image binary headers to extract dimensions (width, height).
    Supports PNG, JPEG, GIF, and WebP formats without external dependencies.
    Returns: (width, height) or None if parsing fails.
    """
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        return None
        
    try:
        with open(filepath, 'rb') as f:
            head = f.read(32)
            
            # 1. PNG Parser
            if head[:8] == b'\x89PNG\r\n\x1a\n':
                w, h = struct.unpack('>II', head[16:24])
                return w, h
                
            # 2. GIF Parser
            elif head[:6] in (b'GIF87a', b'GIF89a'):
                w, h = struct.unpack('<HH', head[6:10])
                return w, h
                
            # 3. WebP Parser
            elif head[:4] == b'RIFF' and head[8:12] == b'WEBP':
                f.seek(12)
                chunk_type = f.read(4)
                if chunk_type == b'VP8 ':
                    # Lossy WebP
                    f.seek(23)
                    sig = f.read(3)
                    if sig == b'\x9d\x01\x2a':
                        w_h = f.read(4)
                        w, h = struct.unpack('<HH', w_h)
                        return w & 0x3fff, h & 0x3fff
                elif chunk_type == b'VP8L':
                    # Lossless WebP
                    f.seek(20)
                    b = f.read(5)
                    val = int.from_bytes(b, byteorder='little')
                    w = (val & 0x3fff) + 1
                    h = ((val >> 14) & 0x3fff) + 1
                    return w, h
                elif chunk_type == b'VP8X':
                    # Extended WebP
                    f.seek(24)
                    w_bytes = f.read(3)
                    h_bytes = f.read(3)
                    w = int.from_bytes(w_bytes, byteorder='little') + 1
                    h = int.from_bytes(h_bytes, byteorder='little') + 1
                    return w, h
                    
            # 4. JPEG Parser
            elif head[:2] == b'\xff\xd8':
                f.seek(2)
                while True:
                    marker_bytes = f.read(2)
                    if len(marker_bytes) < 2:
                        break
                    marker, = struct.unpack('>H', marker_bytes)
                    
                    if marker == 0xffd9 or marker == 0xffda: # EOI or SOS
                        break
                    
                    length_bytes = f.read(2)
                    if len(length_bytes) < 2:
                        break
                    length, = struct.unpack('>H', length_bytes)
                    
                    # SOF markers
                    if (0xffc0 <= marker <= 0xffc3 or 
                        0xffc5 <= marker <= 0xffc7 or 
                        0xffc9 <= marker <= 0xffcb or 
                        0xffcd <= marker <= 0xffcf):
                        f.read(1) # precision byte
                        h_w = f.read(4)
                        if len(h_w) == 4:
                            h, w = struct.unpack('>HH', h_w)
                            return w, h
                        break
                    else:
                        f.seek(length - 2, os.SEEK_CUR)
                        
    except Exception as e:
        print(f"    [!] Error parsing header of {filepath}: {e}")
        
    return None

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Argument parser for target directories
    parser = argparse.ArgumentParser(description="Aspect-Ratio & Photo Indexer")
    parser.add_argument('--source', '-s', type=str, default='photos', 
                        help="Relative directory to scan (e.g. photos or static/media/manual_uploads)")
    args = parser.parse_args()
    
    photos_dir = os.path.join(base_dir, args.source)
    output_file = os.path.join(base_dir, 'photos.json')

    # Automatically create the target directory if it does not exist
    if not os.path.exists(photos_dir):
        print(f"[*] Creating local target directory: {photos_dir}")
        os.makedirs(photos_dir, exist_ok=True)

    print(f"[*] Scanning for photos in: {photos_dir}")

    allowed_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
    found_photos = []

    # Walk directory recursively
    for root, _, files in os.walk(photos_dir):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in allowed_extensions:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, base_dir)
                
                # Replace Windows backslashes for URLs
                web_friendly_path = rel_path.replace('\\', '/')
                
                # For static/media/manual_uploads, strip the static/ prefix for web routing
                if web_friendly_path.startswith("static/"):
                    web_friendly_path = web_friendly_path[7:]
                
                if os.path.getsize(full_path) > 0:
                    dimensions = get_image_info(full_path)
                    
                    if dimensions:
                        w, h = dimensions
                        ratio = w / h
                        
                        # Determine orientation classification
                        orientation = 'square'
                        if ratio > 1.25:
                            orientation = 'landscape'
                        elif ratio < 0.8:
                            orientation = 'portrait'
                            
                        found_photos.append({
                            "src": web_friendly_path,
                            "ratio": round(ratio, 3),
                            "orientation": orientation
                        })
                        print(f"  + Added: {web_friendly_path} ({w}x{h}, {orientation}, ratio={round(ratio, 3)})")
                    else:
                        # Fallback for parsing failures: treat as standard square
                        found_photos.append({
                            "src": web_friendly_path,
                            "ratio": 1.0,
                            "orientation": "square"
                        })
                        print(f"  + Added (default aspect ratio): {web_friendly_path}")
                else:
                    print(f"  - Skipped (empty file): {web_friendly_path}")

    # Sort files alphabetically for stability
    found_photos.sort(key=lambda x: x["src"])

    # Save structured registry to photos.json
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(found_photos, f, indent=2, ensure_ascii=False)
        print(f"[+] Successfully wrote {len(found_photos)} photo paths with aspect-ratio tags to {output_file}")
    except Exception as e:
        print(f"[-] Error writing photos.json registry: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()

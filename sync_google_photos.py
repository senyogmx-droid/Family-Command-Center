#!/usr/bin/env python3
"""
========================================================================
GOOGLE PHOTOS SHARED ALBUM SYNCHRONIZER
========================================================================
A zero-dependency Python synchronization script for the Family Command
Center dashboard. Parses a public Google Photos Shared Album link, 
downloads images locally inside photos/ as cached items, prunes deleted 
photos, and updates the slideshow registry.
========================================================================
"""

import os
import sys
import re
import urllib.request
import hashlib
import subprocess

def sync_album(album_url):
    print(f"[*] Fetching shared album from Google Photos...")
    
    # 1. Fetch Shared Album HTML
    try:
        req = urllib.request.Request(
            album_url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8')
    except Exception as e:
        print(f"[!] Error fetching shared album link: {e}")
        print("[!] Please check your network connection and verify the sharing URL.")
        return False

    # 2. Extract Google Usercontent base URLs from script blocks
    # High-resolution photos in shared albums use a long ID key starting with lh3.googleusercontent.com
    # We match all googleusercontent subdomains and paths, then split on '=' to isolate the raw image key base.
    raw_urls = re.findall(r'(https://[A-Za-z0-9\-\.\/]+googleusercontent\.com/[A-Za-z0-9\-_\/\=]+)', html)
    
    unique_bases = []
    for url in raw_urls:
        base_part = url.split('=')[0]
        # Avatars and UI icons are short; actual photos have very long hashes (>100 characters)
        if len(base_part) > 100 and base_part not in unique_bases:
            unique_bases.append(base_part)
            
    print(f"[+] Found {len(unique_bases)} unique photos in remote album.")
    
    if not unique_bases:
        print("[!] No photos detected. Please check:")
        print("    1. Is the album link correct?")
        print("    2. Is the album set to 'Share' and accessible via link?")
        print("    3. Does the album have photos?")
        return False
        
    # Ensure photos directory exists
    photos_dir = "photos"
    os.makedirs(photos_dir, exist_ok=True)
    
    # Load deleted photos blacklist
    blacklist = []
    blacklist_path = "deleted_photos.json"
    if os.path.exists(blacklist_path):
        try:
            import json
            with open(blacklist_path, "r", encoding="utf-8") as f:
                blacklist = json.load(f)
                if not isinstance(blacklist, list):
                    blacklist = []
        except Exception as e:
            print(f"[!] Warning: Could not read deleted_photos.json: {e}")

    active_gphoto_files = []
    download_count = 0
    skip_count = 0
    ignored_count = 0
    
    # 3. Download & Cache New Images
    for index, base_url in enumerate(unique_bases):
        # Create a unique, persistent filename based on MD5 hash of the base URL
        url_hash = hashlib.md5(base_url.encode('utf-8')).hexdigest()
        filename = f"gphoto_{url_hash}.jpg"
        
        # Omit if blacklisted
        if filename in blacklist:
            ignored_count += 1
            continue
            
        filepath = os.path.join(photos_dir, filename)
        active_gphoto_files.append(filename)
        
        # Skip if already downloaded
        if os.path.exists(filepath):
            skip_count += 1
            continue
            
        # Request high-quality version (kiosk friendly 1080p width limit to save disk/RAM)
        hi_res_url = f"{base_url}=w1920-h1080"
        
        print(f"    [+] Downloading new image {index+1}/{len(unique_bases)}...")
        try:
            req = urllib.request.Request(
                hi_res_url,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req, timeout=15) as img_response:
                with open(filepath, 'wb') as f:
                    f.write(img_response.read())
            download_count += 1
        except Exception as e:
            print(f"    [!] Error downloading photo {index+1}: {e}")
            
    print(f"[+] Download phase completed. {download_count} downloaded, {skip_count} already cached, {ignored_count} blacklisted/ignored.")
    
    # 4. Pruning: Delete local images that have been removed from the Google Photos album
    pruned_count = 0
    if os.path.exists(photos_dir):
        for local_file in os.listdir(photos_dir):
            # Only prune files created by this synchronizer (prefixed with gphoto_)
            if local_file.startswith("gphoto_") and local_file.endswith(".jpg"):
                if local_file not in active_gphoto_files:
                    local_filepath = os.path.join(photos_dir, local_file)
                    print(f"    [-] Pruning deleted photo: {local_file}")
                    try:
                        os.remove(local_filepath)
                        pruned_count += 1
                    except Exception as e:
                        print(f"    [!] Error deleting {local_file}: {e}")
                        
    if pruned_count > 0:
        print(f"[+] Pruning phase completed. Removed {pruned_count} orphaned local photo(s).")
        
    # 5. Reindex Local Registry
    print("[*] Reindexing photos registry...")
    try:
        subprocess.run([sys.executable, "sync_photos.py"], check=True)
    except Exception as e:
        print(f"[!] Error running sync_photos.py: {e}")
        return False
        
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python sync_google_photos.py <GOOGLE_PHOTOS_SHARED_ALBUM_URL>")
        sys.exit(1)
        
    album_url = sys.argv[1]
    sync_album(album_url)

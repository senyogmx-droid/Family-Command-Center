#!/usr/bin/env python3
"""
-----------------------------------------------------------------
sync_calendar.py
Secure, zero-dependency iCal parsing system for the Family Command Center.
Fetches a public/private Google Calendar iCal stream and outputs a 
rolling 2-week schedule cache inside 'calendar.json'.
-----------------------------------------------------------------
"""
import os
import json
import sys
import re
import urllib.request
import datetime

def clean_value(val):
    """Unescapes standard iCal special character sequences."""
    val = val.replace('\\,', ',').replace('\\;', ';').replace('\\\\', '\\')
    val = val.replace('\\N', '\n').replace('\\n', '\n')
    return val.strip()

def parse_date(date_str):
    """
    Parses standard iCal DATETIME/DATE formats:
    - 20260520T100000Z (UTC)
    - 20260520T100000 (Local)
    - 20260520 (All Day)
    Returns standard ISO YYYY-MM-DDTHH:MM:SS format string.
    """
    # Clean any timezone params/etc if present
    date_str = date_str.split(':')[-1].strip()
    
    try:
        if 'T' in date_str:
            # Contains time element
            has_z = date_str.endswith('Z')
            clean_str = date_str[:-1] if has_z else date_str
            dt = datetime.datetime.strptime(clean_str, "%Y%m%dT%H%M%S")
            return dt.isoformat() + ('Z' if has_z else '')
        else:
            # All day date element
            dt = datetime.datetime.strptime(date_str[:8], "%Y%m%d")
            # Set to start of day
            return dt.isoformat()
    except Exception as e:
        print(f"  [!] Failed parsing date string '{date_str}': {e}", file=sys.stderr)
        return None

def fetch_and_parse_ical(url):
    print(f"[*] Requesting calendar stream from: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) FamilyCommandCenterSync/1.0'
    }
    req = urllib.request.Request(url, headers=headers)
    
    with urllib.request.urlopen(req, timeout=15) as response:
        raw_data = response.read().decode('utf-8', errors='ignore')
    
    # 1. Unfold multi-line calendar content (lines starting with whitespace are folds)
    lines = raw_data.splitlines()
    unfolded_lines = []
    for line in lines:
        if line.startswith(' ') or line.startswith('\t'):
            if unfolded_lines:
                unfolded_lines[-1] += line[1:]
        else:
            unfolded_lines.append(line)

    # 2. Extract Event Blocks
    events = []
    current_event = None
    in_vevent = False

    for line in unfolded_lines:
        line = line.strip()
        if not line:
            continue
        
        # Check event boundaries
        if line == 'BEGIN:VEVENT':
            current_event = {}
            in_vevent = True
            continue
        elif line == 'END:VEVENT':
            if in_vevent and current_event:
                events.append(current_event)
            in_vevent = False
            current_event = None
            continue
        
        if in_vevent and current_event is not None:
            # Parse property key and value
            # Keys can have params, e.g. DTSTART;TZID=America/New_York:...
            match = re.match(r'^([^:]+):(.*)$', line)
            if match:
                prop, val = match.groups()
                base_prop = prop.split(';')[0].upper()
                
                if base_prop == 'SUMMARY':
                    current_event['summary'] = clean_value(val)
                elif base_prop == 'DTSTART':
                    current_event['start'] = parse_date(val)
                elif base_prop == 'DTEND':
                    current_event['end'] = parse_date(val)
                elif base_prop == 'LOCATION':
                    current_event['location'] = clean_value(val)
                elif base_prop == 'DESCRIPTION':
                    current_event['description'] = clean_value(val)

    print(f"[+] Total raw events parsed from iCal stream: {len(events)}")
    return events

def filter_and_format_events(events):
    """Filters events within a rolling timeline window (-7 days to +30 days)."""
    now = datetime.datetime.now()
    start_bound = now - datetime.timedelta(days=7)
    end_bound = now + datetime.timedelta(days=30)
    
    filtered_events = []
    
    for event in events:
        # Check start date exists
        if not event.get('start'):
            continue
            
        try:
            event_start = datetime.datetime.fromisoformat(event['start'])
            
            # If end is missing, default to 1 hour after start
            if not event.get('end'):
                event_end = event_start + datetime.timedelta(hours=1)
                event['end'] = event_end.isoformat()
            else:
                event_end = datetime.datetime.fromisoformat(event['end'])

            # Timeline window check
            if start_bound <= event_start <= end_bound:
                # Add default placeholders if optional keys are missing
                event['location'] = event.get('location', '')
                event['description'] = event.get('description', '')
                filtered_events.append(event)
        except Exception as e:
            print(f"  [!] Skipped event filtering due to error: {e}", file=sys.stderr)
            
    # Sort chronologically by start date
    filtered_events.sort(key=lambda x: x['start'])
    print(f"[+] Filtered rolling window calendar events: {len(filtered_events)}")
    return filtered_events

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(base_dir, 'calendar.json')

    # Retrive URL from CLI argument, default env parameter, or print help instructions
    ical_url = None
    if len(sys.argv) > 1:
        ical_url = sys.argv[1]
    else:
        ical_url = os.environ.get('ICAL_URL')

    if not ical_url:
        print("[!] No iCal URL provided.")
        print("    Usage: python sync_calendar.py 'YOUR_GOOGLE_ICAL_URL'")
        print("    Alternatively: set the ICAL_URL environment variable.")
        print("[*] Terminating task without wiping the existing calendar cache.")
        sys.exit(0)

    try:
        raw_events = fetch_and_parse_ical(ical_url)
        processed_events = filter_and_format_events(raw_events)
        
        # Write clean data cache
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(processed_events, f, indent=2, ensure_ascii=False)
            
        print(f"[+] Local calendar cache successfully updated: {output_file}")
    except Exception as e:
        print(f"[-] Synchronization failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()

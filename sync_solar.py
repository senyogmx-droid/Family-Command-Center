import os
import json
import ssl
import urllib.request

# Configuration Parameters
ENVOY_IP = "envoy.local"  # If this host doesn't resolve, replace with your gateway's actual IP address

# Try loading dynamic token from a local text file to allow headless updates, falling back to default
token_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "solar_token.txt")
if os.path.exists(token_file):
    try:
        with open(token_file, "r", encoding="utf-8") as tf:
            ENVOY_TOKEN = tf.read().strip()
        print(f"[*] Loaded active Envoy token from: {token_file}")
    except Exception as token_err:
        print(f"[!] Error reading solar_token.txt: {token_err}. Using fallback token.")
        ENVOY_TOKEN = "eyJraWQiOiJtb2NrLWtpZCIsInR5cCI6IkpXVCIsImFsZyI6IkVTMjU2In0.eyJhdWQiOiIxMjM0NTY3ODkwMTIiLCJpc3MiOiJFbnRyZXoiLCJlbnBoYXNlVXNlciI6Imluc3RhbGxlciIsImV4cCI6OTk5OTk5OTk5OSwiaWF0IjoxNzAwMDAwMDAwLCJ1c2VybmFtZSI6InVzZXJAZXhhbXBsZS5jb20ifQ.bW9jay1zaWduYXR1cmUtZm9yLWR1bW15LXRva2VuLXNob3VsZC1iZS1zYWZlLWFuZC1ub24tcmVhbA"
else:
    ENVOY_TOKEN = "eyJraWQiOiJtb2NrLWtpZCIsInR5cCI6IkpXVCIsImFsZyI6IkVTMjU2In0.eyJhdWQiOiIxMjM0NTY3ODkwMTIiLCJpc3MiOiJFbnRyZXoiLCJlbnBoYXNlVXNlciI6Imluc3RhbGxlciIsImV4cCI6OTk5OTk5OTk5OSwiaWF0IjoxNzAwMDAwMDAwLCJ1c2VybmFtZSI6InVzZXJAZXhhbXBsZS5jb20ifQ.bW9jay1zaWduYXR1cmUtZm9yLWR1bW15LXRva2VuLXNob3VsZC1iZS1zYWZlLWFuZC1ub24tcmVhbA"

def fetch_local_solar_data():
    if "PASTE_YOUR" in ENVOY_TOKEN:
        print("[!] Error: Please paste your real Enphase token into the script!")
        return

    # Modern Envoy firmware uses self-signed SSL certificates.
    # We bypass strict verification to prevent local network handshake rejections.
    ctx = ssl._create_unverified_context()
    
    url = f"https://{ENVOY_IP}/production.json"
    headers = {
        "Authorization": f"Bearer {ENVOY_TOKEN}",
        "Accept": "application/json"
    }

    print(f"[*] Requesting live grid metrics from Envoy Gateway...")
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            raw_data = json.loads(response.read().decode('utf-8'))
            
        # Parse the nested arrays (Firmware 7.x standard data mapping)
        production_list = raw_data.get("production", [])
        consumption_list = raw_data.get("consumption", [])
        
        current_watts = 0
        today_watthours = 0
        
        for item in production_list:
            if item.get("type") == "eim" and item.get("measurementType") == "production":
                current_watts = item.get("wNow", 0)
                today_watthours = item.get("whToday", 0)
                break
            elif item.get("type") in ["eels", "inverters"]:
                if current_watts == 0:
                    current_watts = item.get("wNow", 0)
                if today_watthours == 0:
                    today_watthours = item.get("whToday", 0)
        
        consumption_watts = 0
        consumed_today_watthours = 0
        
        for item in consumption_list:
            if item.get("type") == "eim" and item.get("measurementType") == "total-consumption":
                consumption_watts = item.get("wNow", 0)
                consumed_today_watthours = item.get("whToday", 0)
                break
        
        # Format raw metrics to clean kW and kWh display values
        current_kw = round(current_watts / 1000.0, 1)
        today_kwh = round(today_watthours / 1000.0, 1)
        
        consumption_kw = round(consumption_watts / 1000.0, 1)
        consumed_today_kwh = round(consumed_today_watthours / 1000.0, 1)
        
        net_kw = round((current_watts - consumption_watts) / 1000.0, 1)
        net_today_kwh = round((today_watthours - consumed_today_watthours) / 1000.0, 1)
        
        solar_cache = {
            "current_power": f"{current_kw} kW",
            "produced_today": f"{today_kwh} kWh",
            "current_consumption": f"{consumption_kw} kW",
            "consumed_today": f"{consumed_today_kwh} kWh",
            "net_power": f"{net_kw} kW",
            "net_today": f"{net_today_kwh} kWh"
        }

        # Write data cleanly to solar.json cache file
        with open('solar.json', 'w', encoding='utf-8') as f:
            json.dump(solar_cache, f, indent=4)
            
        print(f"[+] Success! Solar cache generated:")
        print(f"    - Solar: {current_kw} kW | {today_kwh} kWh")
        print(f"    - Home:  {consumption_kw} kW | {consumed_today_kwh} kWh")
        print(f"    - Net:   {net_kw} kW | {net_today_kwh} kWh")

    except Exception as e:
        print(f"Failed to reach local Envoy gateway: {e}")
        print("   Tip: Make sure you're connected to the same home network lane as your solar panels!")

if __name__ == "__main__":
    fetch_local_solar_data()

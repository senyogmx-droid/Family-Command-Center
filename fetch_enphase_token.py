#!/usr/bin/env python3
"""
========================================================================
ENPHASE SOLAR GATEWAY TOKEN AUTOMATED HARVESTER
========================================================================
Uses Playwright with a persistent browser context to log in to the Enphase
Entrez portal, capture the 12-hour local Envoy JWT token, and transfer it
securely to the Fedora dashboard server via passwordless SCP.
========================================================================
"""

import os
import sys
import re
import subprocess
import time

def print_banner():
    print("=" * 72)
    print("  ENPHASE SOLAR GATEWAY - AUTOMATED TOKEN HARVESTER")
    print("=" * 72)

def check_playwright():
    """Verify playwright is installed, otherwise prompt to install it."""
    try:
        import playwright
    except ImportError:
        print("[!] Playwright is not installed in the active environment.")
        print("[*] Installing playwright and dependencies...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        except Exception as e:
            print(f"[!] Error installing dependencies: {e}")
            print("Please run manually: pip install playwright && playwright install chromium")
            sys.exit(1)

def decrypt_val(cipher_text, key="EnphaseDashboardSecretKey123"):
    if not cipher_text:
        return ""
    import base64
    try:
        decrypted_bytes = base64.b64decode(cipher_text.encode('utf-8')).decode('utf-8')
        decrypted_chars = []
        for i, c in enumerate(decrypted_bytes):
            key_c = key[i % len(key)]
            decrypted_chars.append(chr(ord(c) ^ ord(key_c)))
        return "".join(decrypted_chars)
    except Exception:
        return ""

def load_enphase_credentials():
    import sqlite3
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "database.db")
    
    # Fallback default values
    username = "user@example.com"
    password = "EnlightenPassword123!"
    system_name = "MySolarSystem"
    gateway_serial = "123456789012"
    
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            rows = cursor.execute("SELECT key, value FROM system_config WHERE key IN ('enphase_username', 'enphase_password', 'enphase_system_name', 'enphase_gateway_serial')").fetchall()
            configs = {r["key"]: r["value"] for r in rows}
            conn.close()
            
            if configs.get("enphase_username"):
                username = configs["enphase_username"]
            if configs.get("enphase_password"):
                password = decrypt_val(configs["enphase_password"])
            if configs.get("enphase_system_name"):
                system_name = configs["enphase_system_name"]
            if configs.get("enphase_gateway_serial"):
                gateway_serial = configs["enphase_gateway_serial"]
                
            print(f"[*] Dynamically loaded Enphase credentials from SQLite database.")
        except Exception as e:
            print(f"[!] Warning: Failed to load credentials from DB: {e}. Using fallback defaults.")
            
    return username, password, system_name, gateway_serial

def harvest_token():
    check_playwright()
    from playwright.sync_api import sync_playwright

    # Dynamic credentials loading
    username, password, system_name, gateway_serial = load_enphase_credentials()

    # Define persistent session context folder inside the project
    base_dir = os.path.dirname(os.path.abspath(__file__))
    session_dir = os.path.join(base_dir, "enphase_session")
    local_token_file = os.path.join(base_dir, "solar_token.txt")
    
    print(f"[*] Session cache directory: {session_dir}")
    print(f"[*] Local token file target: {local_token_file}")

    with sync_playwright() as p:
        print("[*] Launching Chromium browser with persistent session context...")
        
        # We launch headful (headless=False) so that:
        # 1. Any MFA prompt or CAPTCHA is easily visible and solvable by you.
        # 2. Session cookies are saved in enphase_session/ for zero-login automatic runs next time.
        context = p.chromium.launch_persistent_context(
            user_data_dir=session_dir,
            headless=False,
            viewport={"width": 1280, "height": 850}
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        print("[*] Navigating to Enphase Entrez portal...")
        page.goto("https://entrez.enphaseenergy.com/", timeout=60000)
        
        time.sleep(3)
        
        # 1. Dismiss OneTrust Cookie Consent if visible
        try:
            cookie_btn = page.query_selector('#accept-recommended-btn-handler, button:has-text("Allow All"), button:has-text("Accept All"), button:has-text("Accept")')
            if cookie_btn and cookie_btn.is_visible():
                print("[*] Cookie consent banner detected. Clicking 'Allow All'...")
                cookie_btn.click()
                time.sleep(2)
        except Exception as cookie_err:
            pass

        # 2. Check if there is a landing page login button first
        try:
            landing_login = page.query_selector('a:has-text("Login"), a:has-text("Log In"), button:has-text("Login"), button:has-text("Log In"), .orange-button')
            if landing_login and landing_login.is_visible():
                print("[*] Found 'Login' link on landing page. Clicking to redirect to login form...")
                landing_login.click()
                time.sleep(4)
        except Exception as landing_err:
            print(f"[*] Landing page check complete: {landing_err}")

        # 3. Check if we need to log in
        if "login" in page.url or page.query_selector('input[type="email"], input[name="username"], #username'):
            print("[*] Authentication required. Filling credentials...")
            try:
                # Fill Username
                username_field = page.wait_for_selector('input[type="email"], input[name="username"], #username, input[type="text"]', timeout=15000)
                username_field.fill(username)
                
                # Fill Password
                password_field = page.wait_for_selector('input[type="password"], input[name="password"], #password', timeout=15000)
                password_field.fill(password)
                
                # Click Login / Submit
                login_btn = page.query_selector('button[type="submit"], input[type="submit"], button:has-text("Sign In"), button:has-text("Log In"), button:has-text("Login")')
                if login_btn:
                    print("[*] Clicking Login button...")
                    login_btn.click()
                else:
                    print("[!] Login button not found. Please click it in the browser window.")
            except Exception as e:
                print(f"[!] Warning during credential autofill: {e}")
                print("[*] Please complete the login form manually in the browser window.")

        print("[*] Waiting for dashboard loading...")
        print("    (Note: If prompted to complete email/SMS Multi-Factor Authentication (MFA) or verify location, please do so in the browser window!)")

        # 4. Wait for dashboard elements to load (up to 3 minutes to allow for MFA completion)
        try:
            page.wait_for_selector('#selectSystem', timeout=180000)
            print("[+] Successfully authenticated and loaded Entrez portal dashboard!")
        except Exception as load_err:
            print(f"[ERROR] Entrez portal dashboard failed to load: {load_err}")
            context.close()
            sys.exit(1)

        time.sleep(3)

        # 5. Type and select the System (Autocomplete)
        print("[*] Selecting System autocomplete...")
        try:
            system_input = page.wait_for_selector('#selectSystem', timeout=15000)
            system_input.fill("")
            system_input.type(system_name, delay=100)
            print(f"[*] Typed '{system_name}' in system autocomplete. Waiting for suggestion dropdown...")
            
            # Wait for autocomplete suggestion items to appear
            page.wait_for_selector('ul.ui-autocomplete:visible li.ui-menu-item, .ui-menu-item:visible', timeout=15000)
            time.sleep(1)
            
            # Click the suggestion option
            menu_items = page.locator('ul.ui-autocomplete:visible li.ui-menu-item, .ui-menu-item:visible')
            count = menu_items.count()
            if count > 0:
                first_opt = menu_items.first
                text = first_opt.inner_text().strip()
                print(f"[+] Found autocomplete option: '{text}'. Clicking it...")
                first_opt.click()
            else:
                raise Exception("Autocomplete dropdown options were not found or not visible.")
                
            print("[+] Successfully completed System autocomplete selection!")
        except Exception as sys_err:
            print(f"[!] System selection warning/error: {sys_err}")
            print(f"[*] Please select '{system_name}' system manually in the browser window.")

        time.sleep(3) # Wait for AJAX populate on Gateway select

        # 6. Select Gateway
        print("[*] Locating Gateway selection dropdown...")
        try:
            gateway_select = page.wait_for_selector('#serialNum', timeout=15000)
            
            # Poll for gateway options to be populated with gateway_serial (up to 15 seconds)
            print(f"[*] Polling for Gateway '{gateway_serial}' to load...")
            start_poll = time.time()
            has_gw_val = False
            while time.time() - start_poll < 15:
                options = gateway_select.query_selector_all('option')
                for opt in options:
                    val = opt.get_attribute("value")
                    text = opt.inner_text().strip()
                    if val == gateway_serial or gateway_serial in text:
                        has_gw_val = True
                        break
                if has_gw_val:
                    break
                time.sleep(1)

            options = gateway_select.query_selector_all('option')
            target_gw_val = None
            for opt in options:
                val = opt.get_attribute("value")
                text = opt.inner_text().strip()
                if val == gateway_serial or gateway_serial in text:
                    target_gw_val = val
                    break
            
            if not target_gw_val:
                # Fallback to first non-empty option
                for opt in options:
                    val = opt.get_attribute("value")
                    if val and val != "" and val != "0":
                        target_gw_val = val
                        break
            
            if target_gw_val:
                gateway_select.select_option(value=target_gw_val)
                print(f"[+] Selected Gateway option: {target_gw_val}")
            else:
                print("[!] Could not auto-detect Gateway option. Please select it manually in the browser.")
        except Exception as gw_err:
            print(f"[!] Gateway selection warning: {gw_err}")
            print(f"[*] Please select Gateway '{gateway_serial}' manually in the browser window.")

        time.sleep(2)

        # 7. Click "Create Access Token" / "Create Token" button
        print("[*] Triggering token generation...")
        try:
            # Wait for button #submit to be enabled (not disabled)
            print("[*] Waiting for Create Access Token button to be enabled...")
            page.wait_for_selector('button#submit:not([disabled])', timeout=15000)
            create_btn = page.query_selector('button#submit')
            if create_btn:
                print("[*] Clicking 'Create Access Token' button...")
                create_btn.click()
            else:
                print("[!] Create button not found. Please click it manually in the browser window.")
        except Exception as btn_err:
            print(f"[!] Error clicking button: {btn_err}")
            print("[*] Please click the 'Create Access Token' button manually in the browser window.")

        # 6. Extract token from the next screen
        print("[*] Waiting for Token Screen...")
        time.sleep(5)
        
        token_found = False
        captured_token = None
        
        # Scan page content for the generated JWT token string
        content = page.content()
        match = re.search(r'(eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+)', content)
        
        if match:
            captured_token = match.group(1)
            token_found = True
            
            # Click "Copy and Close" button to cleanly exit page state
            try:
                copy_close_btn = page.query_selector('button:has-text("copy and close"), button:has-text("Copy and Close"), button:has-text("Close"), button:has-text("close")')
                if copy_close_btn:
                    print("[*] Found 'Copy and Close' button. Closing modal...")
                    copy_close_btn.click()
                    time.sleep(2)
            except Exception:
                pass
        
        context.close()
        
        if token_found and captured_token:
            print("\n" + "=" * 72)
            print("[SUCCESS] New Enphase Gateway Token captured successfully!")
            print("=" * 72 + "\n")
            
            # Save token locally
            with open(local_token_file, "w", encoding="utf-8") as f:
                f.write(captured_token)
            print(f"[+] Saved token locally to: {local_token_file}")
            
            # Transfer token to Fedora Server
            transfer_token_to_server(local_token_file)
        else:
            print("\n" + "=" * 72)
            print("[ERROR] Failed to extract Enphase JWT token from page.")
            print("Please run script again and ensure you navigate to the final screen presenting the token.")
            print("=" * 72 + "\n")

def transfer_token_to_server(local_file):
    server_ip = "192.168.1.211"
    ssh_user = "senyog"
    remote_path = "/home/senyog/family-dashboard/solar_token.txt"
    
    print(f"[*] Transferring token to Fedora server ({server_ip})...")
    
    # We execute native Windows scp command
    try:
        scp_cmd = ["scp", local_file, f"{ssh_user}@{server_ip}:{remote_path}"]
        result = subprocess.run(scp_cmd, capture_output=True, text=True, check=True)
        print(f"[SUCCESS] Token transferred securely to server: {remote_path}")
        print("[*] Solar telemetry daemon will auto-reload with the new token on its next 15s loop!")
    except subprocess.CalledProcessError as scp_err:
        print(f"[ERROR] Failed to transfer token over SCP: {scp_err.stderr}")
        print("Please check your passwordless SSH key configuration.")
    except Exception as e:
        print(f"[ERROR] An unexpected error occurred during transfer: {e}")

if __name__ == "__main__":
    print_banner()
    harvest_token()

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import csv
import os
from typing import Dict, List, Tuple
import time
import random
import pyautogui
import math
import json
from datetime import datetime, timedelta
import pickle

def bezier_curve(t: float, p0: Tuple[int, int], p1: Tuple[int, int], p2: Tuple[int, int]) -> Tuple[float, float]:
    """
    Calculate point on a quadratic Bezier curve at parameter t.
    
    Args:
        t (float): Parameter between 0 and 1
        p0 (tuple): Start point (x0, y0)
        p1 (tuple): Control point (x1, y1)
        p2 (tuple): End point (x2, y2)
        
    Returns:
        tuple: Point (x, y) on the curve
    """
    x = (1 - t)**2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0]
    y = (1 - t)**2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1]
    return (x, y)

def get_random_screen_position() -> Tuple[int, int]:
    """
    Get a random position on the screen, avoiding edges.
    
    Returns:
        tuple: Random (x, y) coordinates
    """
    screen_width, screen_height = pyautogui.size()
    # Add padding to avoid screen edges
    padding = 100
    x = random.randint(padding, screen_width - padding)
    y = random.randint(padding, screen_height - padding)
    return (x, y)

def natural_mouse_path(start_pos: Tuple[int, int], end_pos: Tuple[int, int], duration: float = 1.0):
    """
    Move mouse in a natural path using multiple control points.
    
    Args:
        start_pos (tuple): Starting position (x, y)
        end_pos (tuple): Ending position (x, y)
        duration (float): Duration of movement in seconds
    """
    # Calculate midpoint
    mid_x = (start_pos[0] + end_pos[0]) / 2
    mid_y = (start_pos[1] + end_pos[1]) / 2
    
    # Create multiple control points for more natural movement
    num_control_points = random.randint(2, 4)
    control_points = []
    
    for _ in range(num_control_points):
        # Random offset from midpoint
        offset_x = random.randint(-200, 200)
        offset_y = random.randint(-200, 200)
        control_points.append((mid_x + offset_x, mid_y + offset_y))
    
    # Generate points along the curve
    steps = int(duration * 60)  # 60 points per second
    for i in range(steps):
        t = i / steps
        
        # Use De Casteljau's algorithm for multiple control points
        points = [start_pos] + control_points + [end_pos]
        while len(points) > 1:
            new_points = []
            for j in range(len(points) - 1):
                x = points[j][0] * (1 - t) + points[j + 1][0] * t
                y = points[j][1] * (1 - t) + points[j + 1][1] * t
                new_points.append((x, y))
            points = new_points
        
        # Add slight random deviation for more natural movement
        x = points[0][0] + random.gauss(0, 1)
        y = points[0][1] + random.gauss(0, 1)
        
        # Add random micro-pauses
        if random.random() < 0.1:  # 10% chance of micro-pause
            time.sleep(random.uniform(0.001, 0.01))
            
        pyautogui.moveTo(x, y, duration/steps)

def get_search_link(paper_title: str, paper_journal: str) -> str:
    """
    Creates a JSTOR search URL for a given paper title and journal.
    
    Args:
        paper_title (str): The title of the paper (e.g., "(Almost) Model-Free Recovery")
        paper_journal (str): The name of the journal (e.g., "the journal of finance")
        
    Returns:
        str: Formatted JSTOR search URL
    """
    # Format paper title by replacing spaces with plus signs
    formatted_title = paper_title.replace(" ", "+")
    
    # Format journal name by replacing spaces with plus signs
    formatted_journal = paper_journal.replace(" ", "+")
    
    # Create the search URL
    base_url = "https://www.jstor.org/action/doBasicSearch"
    query_params = f'Query=ti%3A("{formatted_title}")+AND+pt%3A("{formatted_journal}")&so=rel'
    search_url = f"{base_url}?{query_params}"
    
    return search_url

def generate_cookie_timestamp() -> int:
    """Generate a plausible timestamp for cookies"""
    now = datetime.now()
    random_days_ago = random.randint(1, 30)
    past_date = now - timedelta(days=random_days_ago)
    return int(past_date.timestamp())

def get_common_cookies() -> List[Dict]:
    """
    Generate a list of common cookies that would be present in a regular browser.
    """
    base_timestamp = generate_cookie_timestamp()
    
    common_cookies = [
        # JSTOR related cookies
        {
            "name": "JSTOR_SESSION",
            "value": f"s{random.randint(100000, 999999)}",
            "domain": ".jstor.org",
            "path": "/",
            "expiry": base_timestamp + 86400 * 30,  # 30 days
        },
        {
            "name": "JSTOR_PREF",
            "value": json.dumps({
                "lang": "en",
                "view_type": "list",
                "items_per_page": "25",
                "sort": "relevance"
            }).replace(" ", ""),
            "domain": ".jstor.org",
            "path": "/",
        },
        # Common third-party cookies
        {
            "name": "_ga",
            "value": f"GA1.2.{random.randint(1000000000, 9999999999)}.{random.randint(1000000000, 9999999999)}",
            "domain": ".jstor.org",
            "path": "/",
        },
        {
            "name": "_gid",
            "value": f"GA1.2.{random.randint(100000000, 999999999)}",
            "domain": ".jstor.org",
            "path": "/",
        },
        {
            "name": "OptanonConsent",
            "value": f"isGpcEnabled=0&datestamp={datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}&version=6.10.0",
            "domain": ".jstor.org",
            "path": "/",
        },
        # Browser functionality cookies
        {
            "name": "timezone",
            "value": "America/New_York",
            "domain": ".jstor.org",
            "path": "/",
        },
        {
            "name": "browser_locale",
            "value": "en-US",
            "domain": ".jstor.org",
            "path": "/",
        }
    ]
    
    return common_cookies

def check_for_captcha(driver: webdriver.Chrome) -> bool:
    """
    Check if a captcha is present on the page.
    
    Args:
        driver: Chrome webdriver instance
        
    Returns:
        bool: True if captcha is detected, False otherwise
    """
    # Common captcha indicators
    captcha_indicators = [
        "//iframe[contains(@src, 'recaptcha')]",
        "//iframe[contains(@src, 'captcha')]",
        "//*[contains(text(), 'verify you are human')]",
        "//*[contains(text(), 'complete security check')]",
        "//form[contains(@action, 'captcha')]"
    ]
    
    for indicator in captcha_indicators:
        try:
            if driver.find_elements(By.XPATH, indicator):
                return True
        except:
            continue
    
    return False

def wait_for_captcha_completion(driver: webdriver.Chrome, timeout: int = 300) -> bool:
    """
    Wait for manual captcha completion.
    
    Args:
        driver: Chrome webdriver instance
        timeout: Maximum time to wait in seconds
        
    Returns:
        bool: True if captcha appears to be completed, False if timeout reached
    """
    print("\nCAPTCHA detected! Please complete it manually.")
    print(f"Waiting up to {timeout} seconds for completion...")
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        if not check_for_captcha(driver):
            print("CAPTCHA appears to be completed. Continuing...")
            return True
        time.sleep(2)
    
    print("Timeout reached waiting for CAPTCHA completion.")
    return False

def save_cookies(driver: webdriver.Chrome, cookie_file: str = "jstor_cookies.pkl"):
    """
    Save cookies from current browser session.
    
    Args:
        driver: Chrome webdriver instance
        cookie_file: File to save cookies to
    """
    cookies = driver.get_cookies()
    with open(cookie_file, 'wb') as f:
        pickle.dump(cookies, f)
    print(f"Saved {len(cookies)} cookies to {cookie_file}")

def load_cookies(driver: webdriver.Chrome, cookie_file: str = "jstor_cookies.pkl") -> bool:
    """
    Load cookies from file into browser session.
    
    Args:
        driver: Chrome webdriver instance
        cookie_file: File to load cookies from
        
    Returns:
        bool: True if cookies were loaded successfully
    """
    if not os.path.exists(cookie_file):
        return False
        
    try:
        with open(cookie_file, 'rb') as f:
            cookies = pickle.load(f)
        
        # Check if cookies are expired
        now = datetime.now().timestamp()
        valid_cookies = [c for c in cookies if 'expiry' not in c or c['expiry'] > now]
        
        if not valid_cookies:
            print("All saved cookies are expired")
            return False
            
        for cookie in valid_cookies:
            try:
                driver.add_cookie(cookie)
            except:
                continue
                
        print(f"Loaded {len(valid_cookies)} valid cookies")
        return True
    except Exception as e:
        print(f"Error loading cookies: {str(e)}")
        return False

def create_authenticated_session(cookie_file: str = "jstor_cookies.pkl") -> bool:
    """
    Create a new authenticated session by visiting key pages and saving cookies.
    This should be run manually when needed to refresh cookies.
    
    Args:
        cookie_file: File to save cookies to
        
    Returns:
        bool: True if session was created successfully
    """
    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36')
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        print("\nStarting manual authentication session...")
        print("Please complete any captchas or login processes when they appear.")
        print("This browser session will save cookies for future automated runs.")
        
        # Visit Google first (common referrer)
        driver.get("https://www.google.com/search?q=jstor+academic+papers")
        time.sleep(2)
        
        # Visit JSTOR main page
        driver.get("https://www.jstor.org")
        time.sleep(2)
        
        # Visit advanced search (common academic path)
        driver.get("https://www.jstor.org/action/showAdvancedSearch")
        
        input("\nPress Enter once you've completed any captchas/login processes...")
        
        # Save the cookies
        save_cookies(driver, cookie_file)
        print("\nSession cookies saved successfully!")
        return True
        
    except Exception as e:
        print(f"Error creating authenticated session: {str(e)}")
        return False
    finally:
        driver.quit()

def download_pdf(search_url: str) -> str:
    """
    Downloads PDF from JSTOR search result page.
    
    Args:
        search_url (str): JSTOR search URL from get_search_link
        
    Returns:
        str: Name of the downloaded PDF file
    """
    download_dir = os.path.abspath("downloaded_papers")
    os.makedirs(download_dir, exist_ok=True)
    
    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-extensions')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36')
    options.add_argument('--lang=en-US')
    options.add_argument('--platform=Windows')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,
        "download.directory_upgrade": True,
        "profile.default_content_settings.popups": 0,
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "plugins.plugins_list": [{"enabled": False, "name": "Chrome PDF Viewer"}],
        "profile.default_content_setting_values.notifications": 2
    }
    options.add_experimental_option("prefs", prefs)
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        # Set up browser properties
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            "platform": "Windows"
        })
        
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.execute_script("""
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32',
            });
        """)
        
        print("Navigating to search URL...")
        driver.get(search_url)
        time.sleep(random.uniform(2, 4))
        
        # Try to load saved cookies first
        if load_cookies(driver):
            # Refresh the page to apply cookies
            driver.refresh()
            time.sleep(random.uniform(2, 4))
        else:
            # Fall back to generated cookies if no saved ones exist
            cookies = get_common_cookies()
            for cookie in cookies:
                try:
                    driver.add_cookie(cookie)
                except Exception as e:
                    print(f"Error setting cookie {cookie['name']}: {str(e)}")
        
        # Check for captcha
        if check_for_captcha(driver):
            print("\nCaptcha detected. You have two options:")
            print("1. Complete the captcha manually in this window")
            print("2. Press Ctrl+C to exit, then run create_authenticated_session() to set up a new session with saved cookies")
            
            if not wait_for_captcha_completion(driver):
                raise Exception("Captcha completion timeout")
                
            # Save cookies after successful captcha completion
            save_cookies(driver)
        
        print("Looking for initial download button...")
        download_button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "mfe-download-pharos-button[data-qa='download-pdf']"))
        )
        time.sleep(random.uniform(0.3, 1))

        print("Looking for initial download button...")
        download_button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "mfe-download-pharos-button[data-qa='download-pdf']"))
        )
        time.sleep(random.uniform(0.3, 1))

        # Get button location and move mouse from random position
        button_location = download_button.location
        button_size = download_button.size
        button_center = (
            button_location['x'] + button_size['width'] // 2,
            button_location['y'] + button_size['height'] // 2
        )
        
        # Start from random position and move to download button
        start_pos = get_random_screen_position()
        natural_mouse_path(start_pos, button_center, duration=random.uniform(1.2, 2.0))
        
        # Add small random movement around button before clicking
        for _ in range(random.randint(1, 3)):
            offset_x = random.randint(-5, 5)
            offset_y = random.randint(-5, 5)
            pyautogui.moveRel(offset_x, offset_y, duration=random.uniform(0.1, 0.2))
            time.sleep(random.uniform(0.1, 0.2))

        print("Found initial download button. Clicking...")
        download_button.click()
        time.sleep(random.uniform(0.8, 1.5))  # Longer wait after click

        print("Looking for 'Accept and download' button...")
        accept_button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "mfe-download-pharos-button[data-qa='accept-terms-and-conditions-button']"))
        )
        time.sleep(random.uniform(0.3, 1))

        # Move from download button to accept button
        button_location = accept_button.location
        button_size = accept_button.size
        accept_button_center = (
            button_location['x'] + button_size['width'] // 2,
            button_location['y'] + button_size['height'] // 2
        )
        
        # Create path from current position to accept button
        natural_mouse_path(button_center, accept_button_center, duration=random.uniform(0.8, 1.5))
        
        # Add small random movement around accept button before clicking
        for _ in range(random.randint(1, 3)):
            offset_x = random.randint(-5, 5)
            offset_y = random.randint(-5, 5)
            pyautogui.moveRel(offset_x, offset_y, duration=random.uniform(0.1, 0.2))
            time.sleep(random.uniform(0.1, 0.2))

        print("Found 'Accept and download' button. Clicking...")
        accept_button.click()
        time.sleep(random.uniform(0.8, 1.5))  # Longer wait after click
        
        print("Waiting for download to complete...")
        time.sleep(10)
        
        files = [f for f in os.listdir(download_dir) if f.endswith('.pdf')]
        if not files:
            raise Exception("No PDF file was downloaded")
            
        downloaded_file = max([os.path.join(download_dir, f) for f in files], key=os.path.getctime)
        filename = os.path.basename(downloaded_file)
        print(f"Downloaded file: {filename}")
        
        return filename
        
    except Exception as e:
        print(f"Error during execution: {str(e)}")
        print(f"Current page URL: {driver.current_url}")
        print("Current page source:")
        print(driver.page_source[:1000])
        raise
    finally:
        driver.quit()

if __name__ == "__main__":
    paper_title = "(Almost) Model-Free Recovery"
    journal = "the journal of finance"
    
    print(f"Searching for paper: {paper_title}")
    print(f"In journal: {journal}")
    
    search_url = get_search_link(paper_title, journal)
    print(f"\nGenerated search URL: {search_url}")
    
    print("\nAttempting to download PDF...")
    try:
        filename = download_pdf(search_url)
        print(f"\nSuccessfully downloaded: {filename}")
    except Exception as e:
        print(f"\nError occurred: {str(e)}")
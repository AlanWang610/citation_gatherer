from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from typing import Tuple, List, Dict, Optional
import os
import time
import json
import random
import difflib
import urllib.parse
import csv
import requests
from selenium.webdriver import ActionChains
import hashlib

def random_delay(min_seconds=2, max_seconds=5):
    """Add random delay between actions with more natural distribution"""
    # Use a truncated normal distribution for more natural timing
    mean = (min_seconds + max_seconds) / 2
    std = (max_seconds - min_seconds) / 4
    delay = random.normalvariate(mean, std)
    delay = max(min_seconds, min(max_seconds, delay))  # Clamp to range
    
    # Add micro-delays
    if random.random() < 0.2:  # 20% chance of additional micro-pause
        delay += random.uniform(0.1, 0.3)
    
    time.sleep(delay)

def get_search_link(title: str, doi: str = None) -> str:
    """Get the search URL for a paper."""
    if doi:
        return f"https://onlinelibrary.wiley.com/doi/{doi}"
    return None

def create_driver():
    """Create and configure a Chrome WebDriver instance with enhanced anti-detection measures"""
    options = webdriver.ChromeOptions()
    
    # Basic configuration
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--start-maximized')
    
    # Randomize window size slightly
    width = 1920 + random.randint(-50, 50)
    height = 1080 + random.randint(-30, 30)
    options.add_argument(f'--window-size={width},{height}')
    
    # Add random user agent from a pool of recent ones
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edge/120.0.0.0'
    ]
    options.add_argument(f'--user-agent={random.choice(user_agents)}')
    
    # Disable automation flags
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    
    # Enable cookies and storage
    options.add_argument('--enable-cookies')
    options.add_argument('--disable-web-security')
    
    # Add language and timezone preferences
    options.add_argument('--lang=en-US,en;q=0.9')
    options.add_argument('--disable-features=IsolateOrigins,site-per-process')
    
    # Add common plugins to appear more like a regular browser
    options.add_argument('--enable-plugins')
    options.add_argument('--enable-popup-blocking')
    
    # Create service with specific ChromeDriver
    service = Service(ChromeDriverManager().install())
    
    # Create the driver
    driver = webdriver.Chrome(service=service, options=options)
    
    # Additional CDP commands to modify browser fingerprint
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        "userAgent": random.choice(user_agents),
        "platform": "Windows",
        "acceptLanguage": "en-US,en;q=0.9"
    })
    
    # Modify navigator properties to avoid detection
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {
                        0: {type: "application/x-google-chrome-pdf"},
                        description: "Portable Document Format",
                        filename: "internal-pdf-viewer",
                        length: 1,
                        name: "Chrome PDF Plugin"
                    }
                ]
            });
        """
    })
    
    return driver

def add_random_scroll(driver, target_element=None):
    """Simulate natural scrolling behavior"""
    if target_element:
        # Scroll target into view with slight overshooting
        driver.execute_script("""
            arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});
            // Add slight random overshoot
            window.scrollBy(0, arguments[1]);
        """, target_element, random.randint(50, 150))
        random_delay(0.5, 1)
        
        # 30% chance of small adjustment
        if random.random() < 0.3:
            driver.execute_script(f"window.scrollBy(0, {random.randint(-30, 30)})")
            random_delay(0.3, 0.5)
    else:
        # Get page height
        page_height = driver.execute_script("return document.body.scrollHeight")
        viewport_height = driver.execute_script("return window.innerHeight")
        
        # Scroll about 75% down with slight randomness
        scroll_target = int(page_height * (0.7 + random.random() * 0.1))
        driver.execute_script(f"""
            window.scrollTo({{
                top: {scroll_target},
                behavior: 'smooth'
            }});
        """)
        random_delay(0.5, 1)

def add_random_mouse_movement(driver):
    """Simulate natural mouse movement"""
    viewport_width = driver.execute_script("return window.innerWidth")
    viewport_height = driver.execute_script("return window.innerHeight")
    
    # Create a natural-looking curve using multiple points
    points = []
    num_points = random.randint(3, 6)
    for _ in range(num_points):
        x = random.randint(0, viewport_width)
        y = random.randint(0, viewport_height)
        points.append((x, y))
    
    # Move mouse through points with smooth transitions
    for i in range(len(points) - 1):
        start = points[i]
        end = points[i + 1]
        steps = random.randint(10, 20)
        
        for step in range(steps):
            t = step / steps
            # Smooth easing function
            t = t * t * (3 - 2 * t)
            x = start[0] + (end[0] - start[0]) * t
            y = start[1] + (end[1] - start[1]) * t
            
            driver.execute_script(f"document.elementFromPoint({x}, {y});")
            time.sleep(random.uniform(0.01, 0.03))

def add_scholar_cookies(driver):
    """Add cookies to make the browser look like it has finance research history"""
    # First visit Google Scholar to set domain
    driver.get("https://scholar.google.com")
    random_delay(1, 2)
    
    # Recent finance paper searches
    searches = [
        "financial economics recent papers",
        "journal of finance latest articles"
    ]
    
    # Add search history cookies
    for i, search in enumerate(searches):
        timestamp = int(time.time()) - (i * 3600)  # Space searches 1 hour apart
        driver.add_cookie({
            'name': f'GSP_{i}',
            'value': urllib.parse.quote(search),
            'domain': '.google.com',
            'path': '/scholar'
        })
    
    # Add preference cookies
    driver.add_cookie({
        'name': 'GSP',
        'value': 'CF=4:CFQ=2:LM=1704067200:S=x_vBzLHYqS8',  # Finance-related preferences
        'domain': '.google.com',
        'path': '/scholar'
    })
    
    # Add session cookies
    driver.add_cookie({
        'name': 'SCHOLAR_PREF',
        'value': 'hl=en:lang=en:scis=yes:scisf=4:num=20:scisbd=1',  # English, show abstracts
        'domain': '.google.com',
        'path': '/'
    })

def get_random_financial_searches(num_searches: int = 2) -> List[str]:
    """
    Generate random financial search terms
    Args:
        num_searches: Number of search terms to generate
    Returns:
        List of search terms
    """
    search_terms = [
        "financial economics papers",
        "journal of finance articles",
        "asset pricing theory",
        "corporate finance research",
        "market efficiency studies",
        "portfolio optimization",
        "capital structure theory",
        "risk management finance",
        "behavioral finance research",
        "financial derivatives pricing",
        "market microstructure",
        "empirical asset pricing",
        "financial intermediation",
        "banking regulation papers",
        "corporate governance studies",
        "investment theory finance",
        "market liquidity research",
        "financial crisis papers",
        "monetary policy effects",
        "stock market volatility"
    ]
    return random.sample(search_terms, min(num_searches, len(search_terms)))

def save_wiley_page_content(driver, title: str) -> str:
    """
    Save the HTML content of a Wiley page using Selenium's page source.
    Args:
        driver: Selenium WebDriver instance
        title: Paper title (used for filename)
    Returns:
        Path to saved HTML file
    """
    try:
        # Create output directory if it doesn't exist
        output_dir = "downloaded_html"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Create SHA-256 hash of the original title
        title_hash = hashlib.sha256(title.encode('utf-8')).hexdigest()
        filename = os.path.join(output_dir, f"{title_hash}.html")
        
        # Get the page source and save it
        html_content = driver.page_source
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        print(f"Saved Wiley page content to: {filename}")
        return filename
        
    except Exception as e:
        print(f"Error saving Wiley page: {str(e)}")
        return None

def is_cloudflare_captcha(driver) -> bool:
    """
    Check if we're on a Cloudflare captcha page
    Args:
        driver: Selenium WebDriver instance
    Returns:
        True if on captcha page, False otherwise
    """
    try:
        # Look for common Cloudflare elements
        cloudflare_elements = [
            "cf-browser-verification",  # div id
            "cf-challenge-running",     # div id
            "cf_captcha_kind",         # input name
            "challenge-form",          # form id
            "cf-please-wait"          # text content
        ]
        
        # Check page source for any of these elements
        page_source = driver.page_source.lower()
        return any(element.lower() in page_source for element in cloudflare_elements)
    except:
        return False

def is_valid_wiley_page(driver) -> bool:
    """
    Check if we're on a valid Wiley paper page
    Args:
        driver: Selenium WebDriver instance
    Returns:
        True if on valid paper page, False otherwise
    """
    try:
        # Look for common elements that should be on a valid Wiley paper page
        required_elements = [
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, "article-header"))
            ),
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, "article-content"))
            )
        ]
        return all(element.is_displayed() for element in required_elements)
    except:
        return False

def get_doi_from_google_scholar(driver, title: str, journal: str = None) -> Tuple[str, str]:
    """
    Use Google Scholar to find DOI for a paper by clicking the first result.
    Args:
        driver: Selenium WebDriver instance
        title: Paper title to search for
        journal: Optional journal name to refine search
    Returns:
        Tuple of (DOI string if found or None, path to saved HTML file or None)
    """
    try:
        # Add finance research cookies
        add_scholar_cookies(driver)
        
        # Do a few background searches first to look more natural
        background_searches = get_random_financial_searches(2)
        for search in background_searches:
            driver.get(f"https://scholar.google.com/scholar?q={urllib.parse.quote(search)}")
            random_delay(2, 3)
            add_random_scroll(driver)
        
        # Now do our actual search
        search_query = f'"{title}"'
        if journal:
            search_query += f' source:"{journal}"'
        
        encoded_query = urllib.parse.quote(search_query)
        url = f"https://scholar.google.com/scholar?q={encoded_query}"
        print(f"\nSearching Google Scholar for: {search_query}")
        
        driver.get(url)
        random_delay(2, 3)
        add_random_scroll(driver)
        
        # Look for the first title link
        title_link = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h3.gs_rt a"))
        )
        
        # Get the href before clicking
        href = title_link.get_attribute('href')
        print(f"Found link: {href}")
        
        # Extract DOI and clean it up
        doi = None
        html_file = None
        if 'wiley.com' in href and 'doi' in href:
            doi = href.split('doi/')[-1].split('?')[0].split('#')[0]
            if 'abs/' in doi:  # Remove 'abs/' prefix if present
                doi = doi.replace('abs/', '')
            if 'full/' in doi:  # Remove 'full/' prefix if present
                doi = doi.replace('full/', '')
            print(f"Found DOI: {doi}")
            
            # Navigate to the full article page
            full_article_url = f"https://onlinelibrary.wiley.com/doi/full/{doi}"
            print(f"\nNavigating to: {full_article_url}")
            driver.get(full_article_url)
            
            # Wait for page to load
            random_delay(3, 4)
            
            # Check for Cloudflare captcha
            if is_cloudflare_captcha(driver):
                print("Encountered Cloudflare captcha, skipping...")
                return None, None
                
            # Verify we're on a valid Wiley page
            if not is_valid_wiley_page(driver):
                print("Not on a valid Wiley paper page, skipping...")
                return None, None
            
            # Save the page content
            html_file = save_wiley_page_content(driver, title)
        
        return doi, html_file
            
    except Exception as e:
        print(f"Error searching Google Scholar: {str(e)}")
        return None, None

def process_papers_from_csv(csv_path: str = "data/JF.csv", journal: str = "the journal of finance"):
    """
    Process papers from a CSV file, downloading HTML content for each paper.
    The CSV should have columns: title, hash.html, doi
    Will only process papers that don't have a hash.html value yet.
    
    Args:
        csv_path: Path to the CSV file
        journal: Journal name to use in searches
    """
    try:
        # Read the CSV file
        papers = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            papers = list(reader)
        
        if not papers:
            print(f"No papers found in {csv_path}")
            return
            
        # Find first paper without hash.html
        start_index = 0
        for i, paper in enumerate(papers):
            if not paper.get('hash.html'):
                start_index = i
                break
        else:
            print("All papers have already been processed")
            return
            
        print(f"Starting from paper {start_index + 1} of {len(papers)}")
        
        # Process each remaining paper
        for i, paper in enumerate(papers[start_index:], start=start_index):
            title = paper['title']
            if not title:
                continue
                
            print(f"\nProcessing paper {i + 1} of {len(papers)}: {title}")
            
            # Create a new browser instance for each paper
            driver = create_driver()
            try:
                # Get DOI and save HTML
                doi, html_file = get_doi_from_google_scholar(driver, title, journal)
                
                if html_file:
                    # Extract just the filename from the full path
                    html_filename = os.path.basename(html_file)
                    paper['hash.html'] = html_filename
                    
                    # Add the DOI if found
                    if doi:
                        paper['doi'] = doi
                    
                    # Write updated data back to CSV
                    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.DictWriter(f, fieldnames=['title', 'hash.html', 'doi'])
                        writer.writeheader()
                        writer.writerows(papers)
                        
                    print(f"Updated CSV with hash: {html_filename}")
                    print(f"Updated CSV with DOI: {doi if doi else 'Not found'}")
                else:
                    print(f"Failed to get metadata for paper: {title}")
            finally:
                # Always close the browser after each paper
                try:
                    driver.quit()
                except:
                    pass
            
            # Add a delay between papers
            if i < len(papers) - 1:
                delay = random.uniform(5, 10)
                print(f"\nWaiting {delay:.1f} seconds before next paper...")
                time.sleep(delay)
                
    except Exception as e:
        print(f"Error processing papers: {str(e)}")

if __name__ == "__main__":
    process_papers_from_csv()
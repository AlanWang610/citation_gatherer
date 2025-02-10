from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from typing import Tuple, List, Dict
import time
import random
import csv
import os
import urllib.parse

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

def get_search_link(paper_title: str, paper_doi: str = None) -> str:
    """
    Generate a Wiley URL for a given paper title or DOI.
    If DOI is provided, it will be used directly. Otherwise, a search URL will be constructed.
    """
    if paper_doi:
        return f"https://onlinelibrary.wiley.com/doi/{paper_doi}"
    else:
        # URL encode the title properly
        encoded_title = urllib.parse.quote(paper_title)
        
        # Construct the search URL
        base_url = "https://onlinelibrary.wiley.com/action/doSearch"
        params = {
            'field1': 'Title',
            'text1': encoded_title,
            'publication[]': '15406261',  # The Journal of Finance
            'AllField': encoded_title,
            'content': 'articlesChapters',
            'target': 'default'
        }
        query_string = urllib.parse.urlencode(params, safe='[]')
        return f"{base_url}?{query_string}"

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

def get_paper_metadata(url: str, max_retries: int = 3) -> Dict:
    """
    Navigate to the Wiley paper URL and extract metadata with enhanced anti-detection measures.
    Returns: Dictionary containing paper metadata including:
        - url: Original URL
        - current_url: Final URL after redirects
        - title: Paper title
        - authors: List of authors
        - journal: Journal name
        - year: Publication year
        - doi: DOI string
        - doi_url: Full DOI URL
        - references: List of references
    """
    retry_count = 0
    last_exception = None
    
    while retry_count < max_retries:
        driver = None
        try:
            driver = create_driver()
            
            # Randomize initial behavior with Google Scholar focus
            initial_urls = [
                "https://scholar.google.com",
                "https://scholar.google.com/scholar?q=finance+research",
                "https://scholar.google.com/scholar?q=economics+papers",
                "https://scholar.google.com/citations"
            ]
            
            # Visit 1-2 random Google Scholar pages first
            num_initial_visits = random.randint(1, 2)
            for _ in range(num_initial_visits):
                initial_url = random.choice(initial_urls)
                print(f"\nVisiting initial site: {initial_url}")
                driver.get(initial_url)
                random_delay(1, 3)
                
                # Add some natural browsing behavior
                add_random_scroll(driver)
                add_random_mouse_movement(driver)
                
                # Sometimes perform a search
                if random.random() < 0.3:
                    try:
                        search_box = driver.find_element(By.NAME, "q")
                        search_terms = ["finance", "economics", "market analysis", "asset pricing"]
                        search_box.send_keys(random.choice(search_terms))
                        random_delay(0.5, 1)
                        search_box.submit()
                        random_delay(1, 2)
                        add_random_scroll(driver)
                    except:
                        pass
            
            # Now navigate to the paper URL
            print(f"\nNavigating to target URL: {url}")
            driver.get(url)
            random_delay(2, 4)
            
            # Get the final URL after any redirects
            current_url = driver.current_url
            print(f"Current URL after navigation: {current_url}")
            
            # Add some initial random scrolling and mouse movement
            add_random_scroll(driver)
            add_random_mouse_movement(driver)
            
            # Check if we need to log in
            login_buttons = driver.find_elements(By.CSS_SELECTOR, "[data-qa='login-button']")
            if login_buttons:
                print("Wiley login required. Please log in to your Wiley account first.")
                return None
            
            # Extract metadata with natural delays and movements between actions
            print("\nExtracting metadata...")
            metadata = {}
            
            # Title
            print("Getting title...")
            title_elem = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1.citation__title"))
            )
            metadata['title'] = title_elem.text.strip()
            random_delay(1, 2)
            
            # Authors - Updated selector
            print("Getting authors...")
            add_random_mouse_movement(driver)
            # First try the desktop authors
            author_elems = driver.find_elements(By.CSS_SELECTOR, "div.loa-wrapper.loa-authors.hidden-xs.desktop-authors div.accordion-tabbed a.author-name span")
            if not author_elems:
                # Fallback to mobile authors if desktop not found
                author_elems = driver.find_elements(By.CSS_SELECTOR, "div.loa-wrapper div.accordion-tabbed a.author-name span")
            
            metadata['authors'] = [author.text.strip() for author in author_elems if author.text.strip()]
            print(f"Found {len(metadata['authors'])} authors: {', '.join(metadata['authors'])}")
            random_delay(0.5, 1.5)
            
            # Journal name
            metadata['journal'] = "The Journal of Finance"
            
            # Publication year
            print("Getting publication date...")
            add_random_mouse_movement(driver)
            date_elem = driver.find_element(By.CSS_SELECTOR, "span.epub-date")
            metadata['year'] = date_elem.text.split()[-1]
            random_delay(0.5, 1.5)
            
            # Get DOI
            print("Getting DOI...")
            add_random_mouse_movement(driver)
            doi_elem = driver.find_element(By.CSS_SELECTOR, "a.epub-doi")
            metadata['doi'] = doi_elem.text.strip().replace("https://doi.org/", "")
            metadata['doi_url'] = f"https://doi.org/{metadata['doi']}"
            random_delay(1, 2)
            
            # Click to expand references section with natural movement
            print("\nExpanding references section...")
            refs_button = driver.find_element(By.CSS_SELECTOR, "div.accordion__control[role='button']")
            add_random_scroll(driver, refs_button)
            add_random_mouse_movement(driver)
            driver.execute_script("arguments[0].click();", refs_button)
            random_delay(1.5, 2)
            
            # Extract references
            print("Getting references...")
            ref_elems = driver.find_elements(By.CSS_SELECTOR, "ul.rlist.separator li")
            metadata['references'] = []
            
            for ref in ref_elems:
                ref_text = ""
                
                # Get authors
                authors = ref.find_elements(By.CSS_SELECTOR, "span.author")
                if authors:
                    ref_text += ", ".join([author.text.strip() for author in authors])
                
                # Get year
                year = ref.find_elements(By.CSS_SELECTOR, "span.pubYear")
                if year:
                    ref_text += f" ({year[0].text.strip()})"
                
                # Get title
                title = ref.find_elements(By.CSS_SELECTOR, "span.articleTitle, span.chapterTitle, span.otherTitle")
                if title:
                    ref_text += f", {title[0].text.strip()}"
                
                # Get journal/book
                journal = ref.find_elements(By.CSS_SELECTOR, "i")
                if journal:
                    ref_text += f", {journal[0].text.strip()}"
                
                # Get volume and pages
                vol = ref.find_elements(By.CSS_SELECTOR, "span.vol")
                pages_first = ref.find_elements(By.CSS_SELECTOR, "span.pageFirst")
                pages_last = ref.find_elements(By.CSS_SELECTOR, "span.pageLast")
                
                if vol:
                    ref_text += f" {vol[0].text.strip()}"
                if pages_first and pages_last:
                    ref_text += f", {pages_first[0].text.strip()}–{pages_last[0].text.strip()}"
                
                # Get DOI if available
                doi_elem = ref.find_elements(By.CSS_SELECTOR, "span.data-doi")
                if doi_elem:
                    ref_text += f" DOI: {doi_elem[0].text.strip()}"
                
                if ref_text:
                    metadata['references'].append(ref_text)
            
            print(f"Found {len(metadata['references'])} references")
            
            # Store original and current URLs
            metadata['url'] = url
            metadata['current_url'] = current_url
            
            return metadata
            
        except Exception as e:
            last_exception = e
            retry_count += 1
            print(f"\nError during attempt {retry_count}/{max_retries}: {str(e)}")
            if driver and driver.current_url != url:
                print(f"Current page URL: {driver.current_url}")
            if retry_count < max_retries:
                print(f"Retrying in {retry_count * 2} seconds...")
                time.sleep(retry_count * 2)
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
    
    print("\nAll retry attempts failed. Last error:")
    print(str(last_exception))
    return None

# Example usage
if __name__ == "__main__":
    paper_title = "(Almost) Model-Free Recovery"
    paper_doi = "10.1111/jofi.12737"  # DOI for the example paper
    
    # Try with DOI first
    url = get_search_link(paper_title, paper_doi)
    metadata = get_paper_metadata(url)
    
    if metadata:
        print("\nSuccessfully retrieved metadata:")
        for key, value in metadata.items():
            if key != 'references':  # Don't print all references
                print(f"{key}: {value}")
        print(f"Number of references: {len(metadata['references'])}")
    else:
        print("\nFailed to retrieve metadata")
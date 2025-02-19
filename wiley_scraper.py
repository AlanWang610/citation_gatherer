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
from math import comb
import traceback
import pyautogui
import numpy as np
import pandas as pd

# List of realistic user agents
USER_AGENTS = [
    # Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    # Edge Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    # Chrome macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    # Firefox Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]

# List of realistic background searches
BACKGROUND_SEARCHES = [
    # General finance topics
    "financial derivatives pricing models",
    "market risk premium calculation",
    "portfolio optimization strategies",
    "quantitative trading algorithms",
    "asset pricing theory",
    "efficient market hypothesis evidence",
    "behavioral finance research",
    "stock market volatility analysis",
    "capital structure theory",
    "corporate finance fundamentals",
    # Academic paper related
    "recent finance papers methodology",
    "finance research developments",
    "journal of finance latest articles",
    "financial economics papers",
    "empirical finance studies",
    # Specific topics
    "machine learning in finance",
    "cryptocurrency market efficiency",
    "ESG investing performance",
    "high frequency trading impact",
    "market microstructure theory",
    # Author searches
    "Eugene Fama efficient markets",
    "Robert Shiller behavioral finance",
    "Stephen Ross arbitrage pricing",
    "Robert Merton option pricing",
    "Kenneth French factor models"
]

def get_random_background_search():
    """Get a random background search with some variations"""
    base_search = random.choice(BACKGROUND_SEARCHES)
    
    # Sometimes add year
    if random.random() < 0.3:
        year = random.randint(2020, 2024)
        base_search += f" {year}"
    
    # Sometimes add specific terms
    if random.random() < 0.2:
        terms = ["review", "survey", "analysis", "study", "research", "paper", "evidence"]
        base_search += f" {random.choice(terms)}"
    
    # Sometimes add methodology terms
    if random.random() < 0.15:
        methods = ["empirical", "theoretical", "quantitative", "qualitative", "experimental"]
        base_search = f"{random.choice(methods)} {base_search}"
    
    return base_search

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

def get_search_link(title: str, doi: str = None, source: str = 'wiley') -> str:
    """
    Get the search URL for a paper.
    Args:
        title: Paper title
        doi: DOI if available
        source: Source platform ('wiley' or 'jstor')
    Returns:
        Direct URL to the paper if possible, None otherwise
    """
    if doi:
        if source.lower() == 'wiley':
            return f"https://onlinelibrary.wiley.com/doi/{doi}"
        elif source.lower() == 'jstor':
            return f"https://www.jstor.org/stable/{doi}"
    return None

def init_driver():
    """Create and configure a Chrome WebDriver instance with enhanced anti-detection measures"""
    options = webdriver.ChromeOptions()
    
    # Use a more specific and realistic user agent
    user_agent = random.choice(USER_AGENTS)
    options.add_argument(f'user-agent={user_agent}')
    
    # Add common browser extensions to look more legitimate
    options.add_argument('--disable-blink-features=AutomationControlled')
    
    # Add common browser preferences
    options.add_experimental_option("prefs", {
        "profile.default_content_settings.popups": 0,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.cookie_controls_mode": 0,
        "profile.block_third_party_cookies": False,
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "profile.default_content_setting_values.notifications": 2,
        "profile.managed_default_content_settings.images": 1,
        "profile.default_content_setting_values.cookies": 1
    })
    
    # Add common Chrome arguments
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--ignore-certificate-errors')
    options.add_argument('--ignore-ssl-errors')
    options.add_argument('--start-maximized')
    
    # Create WebDriver with enhanced options
    driver = webdriver.Chrome(options=options)
    
    # Add additional JavaScript patches to avoid detection
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        "userAgent": user_agent,  # Use the same user agent we set in options
        "platform": "Windows",
        "acceptLanguage": "en-US,en;q=0.9"
    })
    
    # Add common browser properties to make fingerprint more realistic
    driver.execute_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                {
                    0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format"},
                    description: "Portable Document Format",
                    filename: "internal-pdf-viewer",
                    name: "Chrome PDF Plugin"
                }
            ]
        });
    """)
    
    return driver

def add_random_scroll(driver, target_element=None):
    """Simulate natural scrolling behavior"""
    try:
        # Get page height
        page_height = driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
        viewport_height = driver.execute_script("return window.innerHeight")
        current_position = 0
        
        # Number of scroll steps (more steps = smoother scrolling)
        num_steps = random.randint(5, 10)
        
        if target_element:
            # If we have a target element, scroll to it gradually
            target_position = target_element.location['y']
            for step in range(num_steps):
                next_position = int(current_position + (target_position - current_position) * (step + 1) / num_steps)
                driver.execute_script(f"window.scrollTo(0, {next_position})")
                random_delay(0.1, 0.3)  # Shorter delays between scroll steps
        else:
            # Random scrolling pattern
            scroll_points = []
            
            # Generate 2-3 random scroll points between viewport height and max scroll position
            num_points = random.randint(2, 3)
            max_scroll = page_height - viewport_height
            
            for _ in range(num_points):
                point = random.randint(viewport_height//2, max_scroll)
                scroll_points.append(point)
            
            # Sort points to scroll in order
            scroll_points.sort()
            
            # Scroll to each point with natural easing
            for point in scroll_points:
                driver.execute_script(f"window.scrollTo(0, {point})")
                random_delay(0.2, 0.5)
                
                # Occasionally pause at interesting points
                if random.random() < 0.2:  # 20% chance to pause
                    random_delay(0.5, 1.5)
        
        # Sometimes scroll back to top
        if random.random() < 0.3:  # 30% chance
            for position in sorted(scroll_points, reverse=True):
                driver.execute_script(f"window.scrollTo(0, {position})")
                random_delay(0.1, 0.3)
    except Exception as e:
        print(f"Error during scrolling: {str(e)}")

def move_to_element_realistic(driver, element):
    """Move to element with realistic mouse movement"""
    try:
        # Get element location and size
        location = element.location_once_scrolled_into_view
        size = element.size
        
        # Calculate a random point within the element
        x = location['x'] + size['width'] * random.uniform(0.2, 0.8)
        y = location['y'] + size['height'] * random.uniform(0.2, 0.8)
        
        # Add offset for window position and scrolling
        window_x = driver.execute_script('return window.screenX')
        window_y = driver.execute_script('return window.screenY')
        scroll_y = driver.execute_script('return window.pageYOffset')
        
        # Calculate final coordinates
        # Add window offset and account for Chrome's header bar (~80px)
        final_x = x + window_x
        final_y = y + window_y + 80
        
        # Move mouse with natural motion
        smooth_move_mouse(final_x, final_y, duration=random.uniform(0.5, 1.0))
        
        # Small pause after reaching the element
        random_delay(0.1, 0.3)
        
        return True
    except Exception as e:
        print(f"Error moving mouse: {str(e)}")
        return False

def smooth_move_mouse(x, y, duration=1):
    """Move mouse in a human-like curved motion"""
    # Get current position
    start_x, start_y = pyautogui.position()
    
    # Generate a smooth curve between points
    # Number of intermediate points
    steps = 50
    
    # Generate control points for Bezier curve
    control_x1 = start_x + (x - start_x) * random.uniform(0.2, 0.4)
    control_y1 = start_y + (y - start_y) * random.uniform(0.2, 0.4)
    control_x2 = start_x + (x - start_x) * random.uniform(0.6, 0.8)
    control_y2 = start_y + (y - start_y) * random.uniform(0.6, 0.8)
    
    def bezier(t):
        # Cubic Bezier curve
        return (
            (1-t)**3 * start_x + 3*(1-t)**2 * t * control_x1 + 
            3*(1-t) * t**2 * control_x2 + t**3 * x,
            (1-t)**3 * start_y + 3*(1-t)**2 * t * control_y1 + 
            3*(1-t) * t**2 * control_y2 + t**3 * y
        )
    
    # Move mouse along curve
    for i in range(steps):
        t = i / steps
        next_x, next_y = bezier(t)
        
        # Add slight random variation
        next_x += random.gauss(0, 2)
        next_y += random.gauss(0, 2)
        
        # Calculate time for this step with slight random variation
        step_duration = duration / steps * random.uniform(0.8, 1.2)
        
        pyautogui.moveTo(next_x, next_y, step_duration)
    
    # Final move to exact destination
    pyautogui.moveTo(x, y, duration/steps)

def add_natural_page_interaction(driver):
    """Add natural mouse movements and scrolling to make the browsing look more human-like"""
    try:
        # Get page height
        height = driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
        viewport_height = driver.execute_script("return window.innerHeight")
        
        # Find some interactive elements to hover over
        interactive_elements = driver.find_elements(By.CSS_SELECTOR, 
            'a, button, .article-content p, .article-header, .pdf-download, .article-section, h1, h2, .abstract')
        
        if interactive_elements:
            # Pick 2-3 random elements to interact with
            elements_to_interact = random.sample(interactive_elements, 
                min(random.randint(2, 3), len(interactive_elements)))
            
            for element in elements_to_interact:
                try:
                    # Scroll element into view with natural easing
                    driver.execute_script("""
                        element = arguments[0];
                        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    """, element)
                    random_delay(0.5, 1)
                    
                    # Try to move mouse to the element
                    if move_to_element_realistic(driver, element):
                        random_delay(0.3, 0.7)
                except:
                    pass
        
        # Only do scrolling if page is taller than viewport
        if height > viewport_height:
            # Natural scroll behavior
            current_scroll = 0
            scroll_points = []
            
            # Generate 2-3 random scroll points between viewport height and max scroll position
            num_points = random.randint(2, 3)
            max_scroll = height - viewport_height
            
            for _ in range(num_points):
                point = random.randint(viewport_height//2, max_scroll)
                scroll_points.append(point)
            
            # Sort points to scroll in order
            scroll_points.sort()
            
            # Scroll to each point with natural easing
            for point in scroll_points:
                driver.execute_script("""
                    window.scrollTo({
                        top: arguments[0],
                        behavior: 'smooth'
                    });
                """, point)
                random_delay(0.5, 1)
            
            # Scroll back to top smoothly
            driver.execute_script("""
                window.scrollTo({
                    top: 0,
                    behavior: 'smooth'
                });
            """)
            random_delay(0.5, 1)
        
    except Exception as e:
        print(f"Error during natural page interaction: {str(e)}")
        # Don't raise the error - this is just supplementary behavior

def try_source(driver, source_site: str, title: str, journal: str = None) -> Tuple[str, str]:
    try:
        # Set referrer policy to look more legitimate
        driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {
            'headers': {
                'Referer': 'https://scholar.google.com/',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'DNT': '1',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'cross-site',
                'Sec-Fetch-User': '?1'
            }
        })
        
        # Now do our actual search with site restriction
        search_query = f'"{title}" site:{source_site}'
        if journal:
            search_query += f' source:"{journal}"'
        
        encoded_query = urllib.parse.quote(search_query)
        url = f"https://scholar.google.com/scholar?q={encoded_query}"
        print(f"\nSearching Google Scholar for: {search_query}")
        
        # Load main search
        print("Loading search results...")
        driver.get(url)
        random_delay(2, 3)  # Longer wait for main search
        
        # Check for captcha on main search
        if is_cloudflare_captcha(driver):
            print("Hit Cloudflare captcha on main search")
            return "CAPTCHA", None
        
        # Look for the first title link with reduced timeout
        timeout = 5 if source_site == 'wiley.com' else 10
        try:
            print("Looking for search result link...")
            link = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".gs_rt a"))
            )
            
            print(f"Found link: {link.get_attribute('href')}")
            print("Moving to and clicking link...")
            
            # More natural mouse movement and clicking
            if move_to_element_realistic(driver, link):
                random_delay(1, 1.5)  # Pause before clicking
                link.click()
            else:
                # Fallback to JavaScript click if mouse movement fails
                driver.execute_script("arguments[0].click();", link)
            
            random_delay(3, 4)  # Longer wait after clicking
            
            # Add natural browsing behavior on publisher page
            add_natural_page_interaction(driver)
            
            # Validate page and handle accordingly
            if source_site == 'wiley.com':
                if is_valid_wiley_page(driver):
                    print("Valid Wiley page found, extracting DOI...")
                    # Save content and extract DOI
                    html_file = save_page_content(driver, title)
                    try:
                        doi_meta = driver.find_element(By.CSS_SELECTOR, "meta[name='citation_doi']")
                        doi = doi_meta.get_attribute("content")
                        if doi:
                            return doi, html_file
                    except:
                        print("Could not extract DOI from Wiley page")
                else:
                    print("Invalid Wiley page")
            else:  # JSTOR
                if is_valid_jstor_page(driver):
                    print("Valid JSTOR page found, extracting DOI...")
                    # Save content and extract DOI
                    html_file = save_page_content(driver, title)
                    doi = extract_doi_from_jstor(driver)
                    if doi:
                        return doi, html_file
                    print("Could not extract DOI from JSTOR page")
                else:
                    print("Invalid JSTOR page")
            
        except TimeoutException:
            print(f"No results found on {source_site}")
            
    except Exception as e:
        print(f"Error searching {source_site}: {str(e)}")
        traceback.print_exc()
    
    return None, None

def get_random_financial_searches(num_searches: int = 2) -> List[str]:
    """
    Generate random financial search terms
    Args:
        num_searches: Number of search terms to generate
    Returns:
        List of search terms
    """
    terms = [
        "stock market volatility",
        "financial derivatives pricing",
        "market risk premium",
        "asset pricing models",
        "option pricing theory",
        "financial market efficiency",
        "portfolio optimization",
        "risk management finance",
        "market microstructure",
        "quantitative trading strategies"
    ]
    return random.sample(terms, min(len(terms), num_searches))

def process_papers_from_csv(csv_path: str = "data/JF.csv", journal: str = "the journal of finance"):
    """
    Process papers from a CSV file, downloading HTML content for each paper.
    Args:
        csv_path: Path to CSV file containing paper titles
        journal: Journal name for search filtering
    """
    # Read CSV file
    df = pd.read_csv(csv_path, header=None, names=['Title', 'HTML', 'DOI', 'Source'])
    
    # Initialize driver
    driver = init_driver()
    
    try:
        # Warm up the browser first
        print("\nWarming up browser...")
        driver.get("https://scholar.google.com")
        random_delay(2, 3)
        
        # Do 2-3 background searches
        num_searches = random.randint(2, 3)
        searches = get_random_financial_searches(num_searches)
        
        for search in searches:
            print(f"\nDoing background search: {search}")
            driver.get(f"https://scholar.google.com/scholar?q={urllib.parse.quote(search)}")
            random_delay(1, 2)
            
            # Check for captcha
            if is_cloudflare_captcha(driver):
                print("Hit Cloudflare captcha during warmup")
                driver.quit()
                return
            
            # Add natural scrolling and hovering
            add_random_scroll(driver)
            random_delay(1, 1.5)
            
            # Try to click a random result
            citations = driver.find_elements(By.CSS_SELECTOR, ".gs_r, .gs_rt a")
            if citations:
                citation = random.choice(citations)
                try:
                    if move_to_element_realistic(driver, citation):
                        random_delay(1, 1.5)
                except:
                    pass
        
        # Process each paper
        papers_processed = 0
        for idx, row in df.iterrows():
            title = row['Title']
            html = row['HTML']
            doi = row['DOI']
            source = row['Source']
            
            # Skip if we already have this paper
            if pd.notna(html) and pd.notna(doi) and pd.notna(source):
                print(f"\nSkipping already processed paper: {title}")
                continue
            
            print(f"\nProcessing paper {papers_processed + 1}: {title}")
            
            # Try to get DOI from Google Scholar
            try:
                new_doi, html_file = get_doi_from_google_scholar(driver, title, journal)
                
                if new_doi == "CAPTCHA":
                    print("Hit CAPTCHA - stopping for now")
                    break
                
                if new_doi:
                    # Update dataframe with new information
                    df.at[idx, 'DOI'] = new_doi
                    df.at[idx, 'HTML'] = html_file
                    df.at[idx, 'Source'] = 'wiley' if 'wiley' in new_doi else 'jstor'
                    
                    # Save progress after each successful paper
                    df.to_csv(csv_path, index=False, header=False)
                    print(f"Saved paper info: DOI={new_doi}")
                    papers_processed += 1
                    
                else:
                    print(f"Paper not found - marking as NA: {title}")
                    df.at[idx, 'DOI'] = 'NA'
                    df.at[idx, 'HTML'] = 'NA'
                    df.at[idx, 'Source'] = 'NA'
                    df.to_csv(csv_path, index=False, header=False)
                
                # Random delay between papers
                random_delay(2, 4)
                
            except Exception as e:
                print(f"Error processing paper: {str(e)}")
                traceback.print_exc()
                continue
            
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        traceback.print_exc()
    
    finally:
        # Save final state
        df.to_csv(csv_path, index=False, header=False)
        driver.quit()

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
        print("\nChecking if page is valid Wiley article...")
        
        # First check for Wiley domain
        current_url = driver.current_url
        if not any(domain in current_url.lower() for domain in ['wiley.com', 'onlinelibrary.wiley.com']):
            print("Not a Wiley domain")
            return False
            
        # Look for common elements that should be on a valid Wiley paper page
        # Multiple possible selectors for redundancy
        selectors = [
            # Main article selectors
            "meta[name='citation_title']",
            "meta[name='citation_doi']",
            "meta[name='citation_journal_title']",
            
            # Alternative content selectors
            ".article__header",
            ".article__content",
            "#article__content",
            ".article-header__meta-info",
            ".citation__title"
        ]
        
        found_elements = []
        for selector in selectors:
            try:
                element = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                if element.is_displayed():
                    found_elements.append(selector)
            except:
                continue
                
        # We need at least 3 elements to consider it a valid page
        is_valid = len(found_elements) >= 3
        
        print(f"Found {len(found_elements)} valid elements: {', '.join(found_elements)}")
        print(f"Page validation result: {'Valid' if is_valid else 'Invalid'} Wiley article page")
        
        return is_valid
        
    except Exception as e:
        print(f"Error validating Wiley page: {str(e)}")
        return False

def is_valid_jstor_page(driver) -> bool:
    """
    Check if we're on a valid JSTOR paper page
    Args:
        driver: Selenium WebDriver instance
    Returns:
        True if on valid paper page, False otherwise
    """
    try:
        print("\nChecking if page is valid JSTOR article...")
        
        # First check for JSTOR domain
        current_url = driver.current_url
        if not any(domain in current_url.lower() for domain in ['jstor.org']):
            print("Not a JSTOR domain")
            return False
        
        # Check for essential page structure elements that should be present on every valid article
        essential_selectors = [
            # Content viewer container - present on all article pages
            "#content-viewer-container",
            
            # Article metadata section
            ".tombstone-metadata",
            
            # Title and author section
            ".item-title-heading",
            ".item-authors",
            
            # Journal info
            ".header-metadata__source-info",
            
            # Stable URL/DOI section
            ".header-metadata__urls"
        ]
        
        found_elements = []
        for selector in essential_selectors:
            try:
                element = WebDriverWait(driver, 2).until(  # Short timeout
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                if element.is_displayed():
                    found_elements.append(selector)
            except:
                continue
        
        # Need at least 4 of the 6 essential elements to consider it valid
        is_valid = len(found_elements) >= 4
        
        print(f"Found {len(found_elements)} essential elements: {', '.join(found_elements)}")
        print(f"Page validation result: {'Valid' if is_valid else 'Invalid'} JSTOR article page")
        
        return is_valid
        
    except Exception as e:
        print(f"Error validating JSTOR page: {str(e)}")
        return False

def extract_doi_from_jstor(driver) -> str:
    """
    Extract DOI from a JSTOR page using multiple methods
    Args:
        driver: Selenium WebDriver instance
    Returns:
        DOI string if found, None otherwise
    """
    try:
        # First try meta tag
        try:
            doi_meta = driver.find_element(By.CSS_SELECTOR, "meta[name='citation_doi']")
            doi = doi_meta.get_attribute("content")
            if doi:
                print(f"Found DOI from meta tag: {doi}")
                return doi
        except:
            pass

        # Try getting DOI from stable URL button
        try:
            stable_url_btn = driver.find_element(By.CSS_SELECTOR, ".copy-stable-url")
            stable_url = stable_url_btn.text
            if stable_url and "jstor.org/stable/" in stable_url:
                jstor_id = stable_url.split("/stable/")[-1].split("?")[0].strip()
                doi = f"10.2307/{jstor_id}"
                print(f"Generated DOI from stable URL: {doi}")
                return doi
        except:
            pass

        # Try getting DOI from current URL as last resort
        try:
            current_url = driver.current_url
            if "jstor.org/stable/" in current_url:
                jstor_id = current_url.split("/stable/")[-1].split("?")[0].strip()
                doi = f"10.2307/{jstor_id}"
                print(f"Generated DOI from current URL: {doi}")
                return doi
        except:
            pass

        print("Could not find DOI using any method")
        return None

    except Exception as e:
        print(f"Error extracting DOI: {str(e)}")
        return None

def get_doi_from_google_scholar(driver, title: str, journal: str = None) -> Tuple[str, str]:
    """Get DOI from Google Scholar search results by trying Wiley then JSTOR."""
    # Try Wiley first, then JSTOR if Wiley fails
    for source_site in ['wiley.com', 'jstor.org']:  
        result = try_source(driver, source_site, title, journal)
        if result[0] == "CAPTCHA":  # If we hit a captcha, stop immediately
            return result
        if result[0] or result[1]:  # If we found either a DOI or HTML file
            return result
        print(f"No results found on {source_site}, trying next source...")
        random_delay(2, 3)  # Add delay between source attempts
    
    # If we get here, neither source worked
    return None, None

def save_page_content(driver, title: str) -> str:
    """
    Save the HTML content of a page using Selenium's page source.
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
            
        print(f"Saved page content to: {filename}")
        return filename
        
    except Exception as e:
        print(f"Error saving page: {str(e)}")
        return None

if __name__ == "__main__":
    process_papers_from_csv(csv_path="data/JF.csv", journal="the journal of finance")
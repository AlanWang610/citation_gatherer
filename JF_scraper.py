import requests
from bs4 import BeautifulSoup
import re
import csv
import os
import random
import urllib.parse
import time
import math
import pyautogui
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from scraper import (
    get_random_background_search,
    random_delay,
    is_cloudflare_captcha,
    USER_AGENTS
)

# Load environment variables
# dotenv.load_dotenv()

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
    
    # Remove automation flags
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
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
        "userAgent": user_agent,
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

def add_gentle_mouse_movement(driver):
    """
    Move mouse in gentle circles near the center of the screen.
    """
    try:
        # Get window size
        window_size = driver.get_window_size()
        center_x = window_size['width'] // 2
        center_y = window_size['height'] // 2
        
        # Create a gentle circular pattern
        radius = 100  # pixels
        num_points = random.randint(5, 10)
        
        for i in range(num_points):
            # Add some randomness to the circle
            angle = (i / num_points) * 2 * math.pi
            rand_radius = radius + random.randint(-20, 20)
            x = center_x + int(rand_radius * math.cos(angle))
            y = center_y + int(rand_radius * math.sin(angle))
            
            # Ensure coordinates are within screen bounds
            x = max(0, min(x, window_size['width'] - 100))
            y = max(0, min(y, window_size['height'] - 100))
            
            # Move mouse smoothly
            pyautogui.moveTo(x, y, duration=0.5)
            random_delay(0.1, 0.3)
            
    except Exception as e:
        print(f"Error during mouse movement: {str(e)}")

def volume_scraper(url, output_file='volume_links.csv'):
    """
    Scrapes all links from a given URL that match the pattern 'https://afajof.org/issue/volume-{volume}-issue-{issue}/'
    and writes the results to a CSV file.
    
    Args:
        url (str): The URL to scrape from
        output_file (str): The name of the CSV file to write results to
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.find_all('a', href=True)
        
        pattern = r'https://afajof\.org/issue/volume-(\d+)-issue-(\d+)/'
        
        with open(output_file, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Volume', 'Issue', 'URL'])
            
            for link in links:
                href = link['href']
                match = re.match(pattern, href)
                if match:
                    volume = int(match.group(1))
                    issue = int(match.group(2))
                    writer.writerow([volume, issue, href])
        
        print(f"Results written to {output_file}")
        
    except requests.RequestException as e:
        print(f"Error fetching URL: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

def doi_scraper(url, output_file='doi_links.csv'):
    """
    Scrapes DOIs from a given URL that match the pattern 'integer.integer/jofi.integer'
    and appends the results to a CSV file.
    
    Args:
        url (str): The URL to scrape from
        output_file (str): The name of the CSV file to append results to
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Pattern to match DOIs in the format integer.integer/jofi.integer
        pattern = r'DOI:\s*(\d+\.\d+/jofi\.\d+)'
        
        # Find all text in the HTML
        text = soup.get_text()
        
        # Find all DOI matches
        matches = re.finditer(pattern, text)
        
        # Open file in append mode
        with open(output_file, 'a', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write header if file is empty
            if csvfile.tell() == 0:
                writer.writerow(['DOI', 'Source URL'])
            
            # Write each DOI found
            for match in matches:
                doi = match.group(1)
                writer.writerow([doi, url])
        
        print(f"DOIs appended to {output_file}")
        
    except requests.RequestException as e:
        print(f"Error fetching URL: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

def metadata_scraper(doi, driver=None):
    """
    Scrapes metadata from a JF article page using the DOI.
    Downloads the HTML content if not already present in downloaded_html.
    
    Args:
        doi (str): The DOI of the article
        driver (webdriver.Chrome, optional): Existing Chrome WebDriver instance
    """
    # Create downloaded_html directory if it doesn't exist
    os.makedirs('downloaded_html', exist_ok=True)
    
    # Replace '/' with '-' in DOI for filename
    filename = f"downloaded_html/{doi.replace('/', '-')}.html"
    
    # Skip if file already exists
    if os.path.exists(filename):
        print(f"File already exists for DOI: {doi}")
        return
    
    # Initialize driver if not provided
    should_quit = False
    if driver is None:
        driver = init_driver()
        should_quit = True
    
    try:
        # Construct and visit the JF article URL
        url = f"https://afajof.org/viewarticle.php?url=full/{doi}"
        driver.get(url)
        random_delay(2, 3)  # Shorter delay after page load
        
        # Check for Cloudflare captcha
        if is_cloudflare_captcha(driver):
            print(f"Captcha detected for DOI: {doi}")
            return
        
        # Add gentle mouse movement
        add_gentle_mouse_movement(driver)
        
        # Save the page content
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print(f"Successfully downloaded HTML for DOI: {doi}")
        
    except Exception as e:
        print(f"Error processing DOI {doi}: {str(e)}")
    finally:
        if should_quit:
            driver.quit()

def process_dois_from_csv(csv_path='dois.csv', max_papers=None):
    """
    Process DOIs from a CSV file and download their HTML content.
    
    Args:
        csv_path (str): Path to CSV file containing DOIs
        max_papers (int, optional): Maximum number of papers to process
    """
    driver = init_driver()
    try:
        # Navigate to login page and wait for manual login
        driver.get("https://afajof.org/member-login/")
        print("Please log in manually. You have 10 seconds...")
        time.sleep(10)
        print("Continuing with scraping...")
        
        # Do two decoy Google Scholar searches at the start
        for _ in range(2):
            search_term = get_random_background_search()
            driver.get(f"https://scholar.google.com/scholar?q={urllib.parse.quote(search_term)}")
            random_delay(2, 4)  # Shorter delay for decoy searches
            add_gentle_mouse_movement(driver)
            random_delay(1, 2)
        
        with open(csv_path, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            for i, row in enumerate(reader):
                if max_papers and i >= max_papers:
                    break
                    
                doi = row['DOI']
                print(f"Processing DOI {i+1}: {doi}")
                metadata_scraper(doi, driver=driver)
                
                # Add consistent delay between papers (10-15 seconds)
                delay = random.uniform(10, 15)
                print(f"Waiting {delay:.1f} seconds before next DOI...")
                time.sleep(delay)
                
    finally:
        driver.quit()

# volume_scraper("https://afajof.org/issue-archive/", output_file='issue_links.csv')
# with open('issue_links.csv', 'r') as csvfile:
#     reader = csv.DictReader(csvfile)
#     for row in reader:
#         issue_url = row['URL']
#         doi_scraper(issue_url, output_file='dois.csv')

process_dois_from_csv('dois.csv')

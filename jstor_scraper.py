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

def download_pdf_and_metadata(search_url: str) -> Tuple[str, str, List[str], str, str, List[str], str]:
    """
    Downloads PDF from JSTOR search result and extracts metadata.
    
    Args:
        search_url (str): JSTOR search URL from get_search_link
        
    Returns:
        Tuple containing:
        - url (str): Page URL where PDF was downloaded
        - paper_title (str): Title of the paper
        - authors (List[str]): List of author names
        - journal (str): Journal name
        - year (str): Publication year
        - references (List[str]): List of reference strings
        - filename (str): Name of the downloaded PDF file
    """
    # Create downloads directory if it doesn't exist
    download_dir = os.path.abspath("downloaded_papers")
    os.makedirs(download_dir, exist_ok=True)
    
    # Initialize Chrome with more realistic browser settings
    options = webdriver.ChromeOptions()
    # options.add_argument('--headless=new')  # Commented out headless mode for debugging
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-extensions')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,
        "download.directory_upgrade": True,
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False
    }
    options.add_experimental_option("prefs", prefs)
    
    # Initialize Chrome with proper service
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        # Set window size
        driver.set_window_size(1920, 1080)
        
        # Override navigator.webdriver
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Add random delays to mimic human behavior
        def random_delay():
            time.sleep(random.uniform(2, 4))
        
        # Navigate to search URL
        print("Navigating to search URL...")
        driver.get(search_url)
        random_delay()
        
        # Check if we need to log in
        login_buttons = driver.find_elements(By.CSS_SELECTOR, "[data-qa='login-button']")
        if login_buttons:
            print("JSTOR login required. Please log in to your JSTOR account first.")
            return None, None, None, None, None, None, None
        
        # Wait for and click first search result
        print("Looking for search result...")
        first_result = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-qa='search-result-title-heading']"))
        )
        print(f"Found result: {first_result.text}")
        first_result.click()
        random_delay()
        
        # Get current URL
        url = driver.current_url
        print(f"Navigated to: {url}")
        
        # Extract metadata
        print("Extracting metadata...")
        paper_title = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1.heading"))
        ).text
        print(f"Title: {paper_title}")
        
        # Extract authors
        authors_elements = driver.find_elements(By.CSS_SELECTOR, "div.item-authors mfe-content-details-pharos-link")
        authors = [author.text for author in authors_elements]
        print(f"Authors: {authors}")
        
        # Extract journal
        journal_element = driver.find_element(By.CSS_SELECTOR, "mfe-content-details-pharos-link cite")
        journal = journal_element.text
        print(f"Journal: {journal}")
        
        # Extract year from publication info
        pub_info = driver.find_element(By.CSS_SELECTOR, "span.src").text
        year = ""
        if "(" in pub_info and ")" in pub_info:
            year = pub_info.split("(")[1].split(")")[0].split()[1]
        print(f"Year: {year}")
        
        # Extract references
        references = []
        ref_elements = driver.find_elements(By.CSS_SELECTOR, "ul.reference-list li div.reference-contains div")
        for ref in ref_elements:
            references.append(ref.text)
        print(f"Found {len(references)} references")
        
        print("Attempting to download PDF...")
        # Click download button
        download_button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-qa='download-pdf-button']"))
        )
        download_button.click()
        
        # Wait for download to complete (approximate)
        time.sleep(10)
        
        # Get the downloaded filename (last file in download directory)
        files = [f for f in os.listdir(download_dir) if f.endswith('.pdf')]
        if not files:
            raise Exception("No PDF file was downloaded")
            
        downloaded_file = max([os.path.join(download_dir, f) for f in files], 
                            key=os.path.getctime)
        filename = os.path.basename(downloaded_file)
        print(f"Downloaded file: {filename}")
        
        # Update paper_tracker.csv
        tracker_file = os.path.join(download_dir, "paper_tracker.csv")
        if not os.path.exists(tracker_file):
            with open(tracker_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['URL', 'Paper Title', 'Filename'])
        
        with open(tracker_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([url, paper_title, filename])
        
        return url, paper_title, authors, journal, year, references, filename
        
    except Exception as e:
        print(f"Error during execution: {str(e)}")
        if driver.current_url != search_url:
            print(f"Current page URL: {driver.current_url}")
        print("Current page source:")
        print(driver.page_source[:1000])
        raise
    finally:
        driver.quit()

if __name__ == "__main__":
    # Test parameters
    paper_title = "(Almost) Model-Free Recovery"
    journal = "the journal of finance"
    
    print(f"Searching for paper: {paper_title}")
    print(f"In journal: {journal}")
    
    # Get the search URL
    search_url = get_search_link(paper_title, journal)
    print(f"\nGenerated search URL: {search_url}")
    
    # Download the paper and get metadata
    print("\nDownloading paper and extracting metadata...")
    try:
        url, title, authors, journal, year, references, filename = download_pdf_and_metadata(search_url)
        
        if url is None:
            print("\nFailed to download paper. JSTOR login required.")
        else:
            # Print results
            print("\nResults:")
            print(f"Paper URL: {url}")
            print(f"Title: {title}")
            print(f"Authors: {', '.join(authors)}")
            print(f"Journal: {journal}")
            print(f"Year: {year}")
            print(f"Downloaded file: {filename}")
            print(f"\nNumber of references: {len(references)}")
            print("\nFirst 3 references:")
            for ref in references[:3]:
                print(f"- {ref}")
            
    except Exception as e:
        print(f"\nError occurred: {str(e)}")
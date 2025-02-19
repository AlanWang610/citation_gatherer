import requests
from bs4 import BeautifulSoup
from typing import List
import re

def article_link_collector(url: str) -> List[str]:
    """
    Collects article links from OUP archive pages.
    
    Args:
        url (str): URL of the form "https://academic.oup.com/rfs/issue-archive/*"
        
    Returns:
        List[str]: List of article URLs
    """
    article_links = set()
    
    try:
        # Get the archive page
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find all issue links
        issue_pattern = r'https://academic\.oup\.com/rfs/issue/\d+/\d+'
        issue_links = {a.get('href') for a in soup.find_all('a', href=True)
                      if re.match(issue_pattern, a.get('href'))}
        
        # Visit each issue page and collect article links
        for issue_link in issue_links:
            try:
                issue_response = requests.get(issue_link)
                issue_response.raise_for_status()
                issue_soup = BeautifulSoup(issue_response.text, 'html.parser')
                
                # Find article links
                article_pattern = r'https://academic\.oup\.com/rfs/article/\d+/\d+/\d+/\d+'
                article_links.update(
                    a.get('href') for a in issue_soup.find_all('a', href=True)
                    if re.match(article_pattern, a.get('href'))
                )
            except requests.RequestException as e:
                print(f"Error accessing issue page {issue_link}: {e}")
                continue
                
        return list(article_links)
        
    except requests.RequestException as e:
        print(f"Error accessing archive page {url}: {e}")
        return []

if __name__ == "__main__":
    url = "https://academic.oup.com/rfs/issue-archive/2025"
    print(f"Collecting article links from {url}...")
    article_links = article_link_collector(url)
    print(f"\nFound {len(article_links)} articles:")
    for link in article_links:
        print(link)
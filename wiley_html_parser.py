from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Optional, Tuple
from enum import Enum
import re

class ReferenceType(Enum):
    ARTICLE = "article"
    WORKING_PAPER = "working_paper"
    BOOK = "book"

    def __str__(self):
        return self.value

@dataclass
class Reference:
    authors: List[str]
    year: Optional[str]
    title: Optional[str]
    journal: Optional[str]
    volume: Optional[str]
    page_first: Optional[str]
    page_last: Optional[str]
    doi: Optional[str]
    ref_type: ReferenceType = ReferenceType.ARTICLE
    working_paper_institution: Optional[str] = None
    book_title: Optional[str] = None
    chapter_title: Optional[str] = None

def clean_text(text: str) -> str:
    """Clean text by removing extra whitespace and special characters"""
    if not text:
        return ""
        
    # First remove any DOI-like patterns and following text
    text = re.sub(r'10\.\d{4,}.*$', '', text)
    
    # Remove citation links and other common noise
    text = re.sub(r'Web of Science®|Google Scholar|CrossRef|PubMed|Scopus', '', text)
    
    # Remove any text after a page number pattern
    text = re.sub(r'\d+[-–]\d+.*$', '', text)
    text = re.sub(r'\d+\s+[A-Za-z].*$', '', text)
    
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[\r\n\t]', '', text)
    
    # Remove any trailing parentheticals
    text = re.sub(r'\s*\([^)]*\)\s*$', '', text)
    
    # Remove any text after a year pattern
    text = re.sub(r'\s*(19|20)\d{2}.*$', '', text)
    
    return text.strip()

def clean_journal(text: str) -> str:
    """Clean journal title by removing any mixed content"""
    if not text:
        return ""
        
    # First clean with standard function
    text = clean_text(text)
    
    # Remove any text after author names
    text = re.sub(r',\s*[A-Z][a-z]+.*$', '', text)
    text = re.sub(r'\s*[A-Z][a-z]+\s+[A-Z][a-z]+.*$', '', text)
    
    # Remove any text after common journal words if they appear twice
    journal_words = ['Journal', 'Proceedings', 'Conference', 'Transactions']
    for word in journal_words:
        matches = list(re.finditer(word, text))
        if len(matches) > 1:
            text = text[:matches[1].start()].strip()
            
    # If the text starts with a bracket, it's probably not a journal
    if text.startswith('['):
        return ""
        
    # Remove any text after numbers
    text = re.sub(r'\s*\d+.*$', '', text)
    
    # Remove any text after common words that indicate mixed content
    text = re.sub(r'\s*using\s+.*$', '', text)
    text = re.sub(r'\s*with\s+.*$', '', text)
    text = re.sub(r'\s*based\s+on\s+.*$', '', text)
    text = re.sub(r'\s*for\s+.*$', '', text)
    text = re.sub(r'\s*in\s+.*$', '', text)
    
    return text.strip()

def clean_authors(text: str) -> str:
    """Clean author text by removing any mixed content"""
    if not text:
        return ""
        
    # First clean with standard function
    text = clean_text(text)
    
    # Remove any text after a year pattern
    text = re.sub(r'\s*\d{4}.*$', '', text)
    
    # Remove any text after common journal words
    text = re.sub(r'\s*Journal\s+.*$', '', text)
    text = re.sub(r'\s*Proceedings\s+.*$', '', text)
    text = re.sub(r'\s*Conference\s+.*$', '', text)
    
    # Remove any text after common words that indicate mixed content
    text = re.sub(r'\s*using\s+.*$', '', text)
    text = re.sub(r'\s*with\s+.*$', '', text)
    text = re.sub(r'\s*based\s+on\s+.*$', '', text)
    text = re.sub(r'\s*for\s+.*$', '', text)
    text = re.sub(r'\s*in\s+.*$', '', text)
    
    return text.strip()

def extract_year(text: str) -> str:
    """Extract a valid year from text"""
    if not text:
        return ""
    match = re.search(r'(19|20)\d{2}', text)
    if match:
        return match.group(0)
    return ""

def clean_pages(text: str) -> str:
    """Clean page numbers by removing any mixed content"""
    if not text:
        return ""
    # Extract just the first set of numbers, ignoring anything after
    match = re.search(r'\d+', text)
    if match:
        return match.group(0)
    return ""

def clean_volume(text: str) -> str:
    """Clean volume number by removing any mixed content"""
    if not text:
        return ""
    # Extract just the first set of numbers
    match = re.search(r'\d+', text)
    if match:
        return match.group(0)
    return ""

def split_name(name: str) -> str:
    """Split and clean an author name"""
    # Remove any numbers, brackets and extra punctuation
    name = re.sub(r'[\d\[\]\(\)]', '', name)
    # Remove any single letters (likely initials without dots)
    name = re.sub(r'\s+[A-Z]\s+', ' ', name)
    return clean_text(name)

def parse_reference(ref_elem) -> Reference:
    """
    Parse a reference from its HTML element using specific class names
    Args:
        ref_elem: BeautifulSoup element containing the reference
    Returns:
        Reference object containing parsed components
    """
    ref = Reference(
        authors=[], year=None, title=None, journal=None,
        volume=None, page_first=None, page_last=None, doi=None,
        ref_type=ReferenceType.ARTICLE
    )
    
    try:
        # Extract authors from class='author'
        author_elems = ref_elem.find_all(class_='author')
        authors = []
        for author in author_elems:
            author_text = clean_authors(author.get_text())
            if author_text and len(author_text) > 2:  # Ignore very short author names
                # Remove any leading/trailing commas
                author_text = author_text.strip(',')
                if author_text:
                    authors.append(author_text)
        ref.authors = authors
        
        # Extract year from class='pubYear'
        year_elem = ref_elem.find(class_='pubYear')
        if year_elem:
            ref.year = extract_year(year_elem.get_text())
        
        # Determine reference type and extract appropriate title fields
        chapter_elem = ref_elem.find(class_='chapterTitle')
        book_elem = ref_elem.find(class_='bookTitle')
        article_elem = ref_elem.find(class_='articleTitle')
        other_elem = ref_elem.find(class_='otherTitle')
        
        # Check for book first
        if chapter_elem or book_elem:
            ref.ref_type = ReferenceType.BOOK
            if chapter_elem:
                ref.chapter_title = clean_text(chapter_elem.get_text())
            if book_elem:
                ref.book_title = clean_text(book_elem.get_text())
        
        # Check for article title
        elif article_elem:
            ref.ref_type = ReferenceType.ARTICLE
            ref.title = clean_text(article_elem.get_text())
        
        # Check other title if no article title
        elif other_elem:
            ref.title = clean_text(other_elem.get_text())
            # Type will be determined later based on working paper check
            
        # If title contains journal info (happens in some cases), split it out
        if ref.title and ' Journal of ' in ref.title:
            parts = ref.title.split(' Journal of ')
            ref.title = clean_text(parts[0])
            if not ref.journal:  # Only set journal if not already set
                ref.journal = 'Journal of ' + clean_text(parts[1])
        
        # Extract journal from <i> tags or look for working paper
        journal_elem = ref_elem.find('i')
        if journal_elem:
            text = journal_elem.get_text().strip()
            # Check if it's a working paper
            working_paper_match = re.search(r'[Ww]orking\s+[Pp]aper,?\s*(.*?)(?:\s*\d{4}|\s*$|[,.])', text)
            if working_paper_match:
                ref.ref_type = ReferenceType.WORKING_PAPER
                institution = working_paper_match.group(1).strip('., ')
                if institution:
                    ref.working_paper_institution = institution
            else:
                ref.journal = clean_journal(text)
        else:
            # Also check full text for working paper mentions if no <i> tag found
            full_text = ref_elem.get_text()
            working_paper_match = re.search(r'[Ww]orking\s+[Pp]aper,?\s*(.*?)(?:\s*\d{4}|\s*$|[,.])', full_text)
            if working_paper_match:
                ref.ref_type = ReferenceType.WORKING_PAPER
                institution = working_paper_match.group(1).strip('., ')
                if institution:
                    ref.working_paper_institution = institution
        
        # Extract volume from class='vol'
        vol_elem = ref_elem.find(class_='vol')
        if vol_elem:
            ref.volume = clean_volume(vol_elem.get_text())
            
        # Extract pages from class='pageFirst' and 'pageLast'
        page_first_elem = ref_elem.find(class_='pageFirst')
        if page_first_elem:
            ref.page_first = clean_pages(page_first_elem.get_text())
            
        page_last_elem = ref_elem.find(class_='pageLast')
        if page_last_elem:
            ref.page_last = clean_pages(page_last_elem.get_text())
        
        # Extract DOI using multiple methods
        # 1. Try data-doi attribute first
        data_doi_elem = ref_elem.find(attrs={'data-doi': True})
        if data_doi_elem:
            ref.doi = data_doi_elem['data-doi']
        
        # 2. Try hidden DOI elements
        if not ref.doi:
            hidden_doi = ref_elem.find(class_='hidden', text=re.compile(r'10\.\d{4,}/'))
            if hidden_doi:
                doi_match = re.search(r'(10\.\d{4,}/[-._;()/:\w]+)', hidden_doi.get_text())
                if doi_match:
                    ref.doi = doi_match.group(1)
        
        # 3. Try accessionId links
        if not ref.doi:
            doi_elem = ref_elem.find('a', class_='accessionId')
            if doi_elem and doi_elem.get('href'):
                doi_url = doi_elem['href']
                if 'doi.org' in doi_url:
                    ref.doi = doi_url.split('doi.org/')[-1]
        
        # 4. Try extracting DOI from any text content as last resort
        if not ref.doi:
            text = ref_elem.get_text()
            doi_match = re.search(r'(?:doi:?\s*|https?://doi\.org/)(10\.\d{4,}/[-._;()/:\w]+)', text)
            if doi_match:
                ref.doi = doi_match.group(1)
        
        # Clean up any extracted DOI
        if ref.doi:
            # Remove any trailing punctuation or whitespace
            ref.doi = ref.doi.strip('.,; ')
            # Ensure it's a valid DOI pattern
            if not re.match(r'^10\.\d{4,}/[-._;()/:\w]+$', ref.doi):
                ref.doi = None
        
        # Handle forthcoming papers without page numbers
        if ref.journal and 'forthcoming' in ref.journal.lower():
            ref.journal = ref.journal.replace(', forthcoming', '').replace('forthcoming', '')
            ref.page_first = 'forthcoming'
            ref.page_last = 'forthcoming'
        
    except Exception as e:
        print(f"Error parsing reference: {str(e)}")
    
    return ref

def parse_wiley_html(file_path: str) -> Tuple[str, List[str], str, List[Reference]]:
    """
    Parse a Wiley HTML file to extract paper metadata
    Args:
        file_path: Path to the HTML file
    Returns:
        Tuple of (title, authors, date, references)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')
        
        # Extract title
        title_elem = soup.find('h1', class_='citation__title')
        title = clean_text(title_elem.text) if title_elem else None
        
        # Extract authors (using set to remove duplicates)
        authors = []
        seen_authors = set()
        
        # Try finding authors in accordion tabs
        author_elems = soup.find_all('a', class_='author-name')
        if not author_elems:  # Try alternative author elements
            author_elems = soup.find_all('div', class_='author-info')
        
        for author_elem in author_elems:
            name = None
            # Try different ways to get author name
            if author_elem.find('span'):
                name = author_elem.find('span').text
            elif author_elem.get('title'):
                name = author_elem['title']
            else:
                name = author_elem.text
                
            if name:
                name = clean_text(name)
                if name not in seen_authors:
                    authors.append(name)
                    seen_authors.add(name)
        
        # Extract date
        date_elem = soup.find('span', class_='epub-date')
        date = clean_text(date_elem.text) if date_elem else None
        
        # Extract references
        references = []
        ref_list = soup.find('ul', class_='rlist separator')
        if ref_list:
            for ref_item in ref_list.find_all('li'):
                # Remove any citation links or web elements before parsing
                for elem in ref_item.find_all(['a', 'button']):
                    if not (elem.get('href') and 'doi.org' in elem['href']):
                        elem.decompose()
                
                ref = parse_reference(ref_item)
                if ref.authors:  # Only add if we found at least one author
                    references.append(ref)
        
        return title, authors, date, references
        
    except Exception as e:
        print(f"Error parsing HTML file: {str(e)}")
        return None, [], None, []

if __name__ == "__main__":
    # Example usage
    import sys
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        title, authors, date, references = parse_wiley_html(file_path)
        print(f"Title: {title}")
        print(f"Authors: {authors}")
        print(f"Date: {date}")
        print("\nReferences:")
        for i, ref in enumerate(references, 1):
            print(f"\n{i}. Authors: {ref.authors}")
            print(f"   Year: {ref.year}")
            print(f"   Title: {ref.title}")
            print(f"   Journal: {ref.journal}")
            print(f"   Volume: {ref.volume}")
            print(f"   Pages: {ref.page_first}-{ref.page_last}")
            print(f"   DOI: {ref.doi}")
            print(f"   Reference Type: {ref.ref_type}")
            print(f"   Working Paper Institution: {ref.working_paper_institution}")
            print(f"   Book Title: {ref.book_title}")
            print(f"   Chapter Title: {ref.chapter_title}")
    else:
        print("Please provide an HTML file path as argument")

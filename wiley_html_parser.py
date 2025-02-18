from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Optional, Tuple
from enum import Enum
import re
from datetime import datetime
import os
import json
import csv
from dataclasses import asdict
from pathlib import Path
import pandas as pd

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

@dataclass
class ArticleMetadata:
    title: Optional[str]
    authors: List[str]
    published_date: Optional[str]
    volume: Optional[str]
    issue: Optional[str]
    page_first: Optional[str]
    page_last: Optional[str]
    citations: Optional[int]
    doi: Optional[str]
    references: List[Reference]

def clean_text(text: str) -> str:
    """Clean text by removing extra whitespace and normalizing characters."""
    if not text:
        return ""
    # Replace any weird whitespace characters with a single space
    text = re.sub(r'\s+', ' ', text)
    # Remove any trailing punctuation except for closing parentheses
    text = re.sub(r'[.,;:\s]+$', '', text)
    # Remove any leading whitespace or punctuation
    text = re.sub(r'^[.,;:\s]+', '', text)
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
        return match.group(1)
    return ""

def split_name(name: str) -> str:
    """Split and clean an author name"""
    # Remove any numbers, brackets and extra punctuation
    name = re.sub(r'[\d\[\]\(\)]', '', name)
    # Remove any single letters (likely initials without dots)
    name = re.sub(r'\s+[A-Z]\s+', ' ', name)
    return clean_text(name)

def parse_date(date_str: str) -> Optional[str]:
    """Convert date from '07 November 2003' format to datetime string"""
    if not date_str:
        return None
    try:
        from datetime import datetime
        # Parse the date string
        date_obj = datetime.strptime(date_str.strip(), "%d %B %Y")
        # Convert to ISO format
        return date_obj.strftime("%Y-%m-%d")
    except Exception:
        return None

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
        
        # Determine reference type
        full_text = ref_elem.get_text()
        
        # 1. Check for working paper
        if re.search(r'working\s+paper', full_text, re.IGNORECASE):
            ref.ref_type = ReferenceType.WORKING_PAPER
            
            # Extract title for working paper - it's between the year and "Working paper"
            year_elem = ref_elem.find(class_='pubYear')
            if year_elem:
                # Get text after the year up to "Working paper"
                after_year = full_text[full_text.find(year_elem.get_text()) + len(year_elem.get_text()):]
                title_match = re.search(r',\s*([^,]*?(?:\([^)]*\)[^,]*?)*)(?:\s*,\s*Working\s+paper)', after_year, re.IGNORECASE)
                if title_match:
                    ref.title = clean_text(title_match.group(1))
            
            # Extract working paper institution
            # Look for text after "Working paper" or "Working Paper"
            match = re.search(r'working\s+paper\s*,\s*([^.]+?)(?:\.|$)', full_text, re.IGNORECASE)
            if match:
                ref.working_paper_institution = match.group(1).strip()
        
        # 2. Check for journal (has italicized title)
        elif ref_elem.find('i'):
            ref.ref_type = ReferenceType.ARTICLE
            # Extract title from articleTitle class for journal articles
            article_elem = ref_elem.find(class_='articleTitle')
            if article_elem:
                ref.title = clean_text(article_elem.get_text())
            
            # Extract journal name from italicized text
            italic_elems = ref_elem.find_all(['i', 'em'])
            if italic_elems:
                # Get the text from all italic elements
                journal_text = ' '.join(clean_text(elem.get_text()) for elem in italic_elems if elem.get_text().strip())
                if journal_text:
                    ref.journal = journal_text
        
        # 3. Otherwise it's a book
        else:
            ref.ref_type = ReferenceType.BOOK
            # Extract title from bookTitle class for books
            book_elem = ref_elem.find(class_='bookTitle')
            if book_elem:
                ref.title = clean_text(book_elem.get_text())

        # Extract title
        chapter_elem = ref_elem.find(class_='chapterTitle')
        book_elem = ref_elem.find(class_='bookTitle')
        other_elem = ref_elem.find(class_='otherTitle')
        
        # Check for book first
        if chapter_elem or book_elem:
            if chapter_elem:
                ref.chapter_title = clean_text(chapter_elem.get_text())
            if book_elem:
                ref.book_title = clean_text(book_elem.get_text())
        
        # Check for other title
        elif other_elem:
            ref.title = clean_text(other_elem.get_text())
            # Check if this might be a working paper
            text_lower = ref.title.lower()
            if 'working paper' in text_lower or 'discussion paper' in text_lower:
                ref.ref_type = ReferenceType.WORKING_PAPER
                # Try to extract institution
                inst_match = re.search(r'([^,]+(?:University|Institute|College|School)[^,]*)', ref.title)
                if inst_match:
                    ref.working_paper_institution = inst_match.group(1).strip()
        
        # Extract volume and pages if it's a journal article
        if ref.ref_type == ReferenceType.ARTICLE:
            # Get the full text of the reference
            full_text = ref_elem.get_text()
            
            # Find the journal in the full text and look at what comes after
            journal_idx = full_text.find(ref.journal)
            if journal_idx != -1:
                after_journal = full_text[journal_idx + len(ref.journal):].strip()
                
                # Try different patterns for volume and pages
                # Pattern 1: "Vol. X" or "Volume X" followed by pages
                vol_match = re.search(r'(?:Vol\.|Volume)\s*(\d+)', after_journal)
                if vol_match:
                    ref.volume = vol_match.group(1)
                    # Look for pages after the volume
                    page_text = after_journal[vol_match.end():]
                else:
                    # Pattern 2: Just a number followed by comma and pages
                    vol_match = re.search(r'(\d+)\s*[,.]', after_journal)
                    if vol_match:
                        ref.volume = vol_match.group(1)
                        page_text = after_journal[vol_match.end():]
                    else:
                        page_text = after_journal
                
                # Look for page numbers in various formats
                # Format 1: pp. 123-145 or p. 123-145
                page_match = re.search(r'(?:pp?\.\s*)?(\d+)\s*[-–]\s*(\d+)', page_text)
                if page_match:
                    ref.page_first = page_match.group(1)
                    ref.page_last = page_match.group(2)
                else:
                    # Format 2: Just numbers separated by hyphen
                    page_match = re.search(r'(\d+)\s*[-–]\s*(\d+)', page_text)
                    if page_match:
                        ref.page_first = page_match.group(1)
                        ref.page_last = page_match.group(2)
                
                if ref.volume or ref.page_first:
                    pass
        
        # Extract DOI if present
        # First try to find DOI in hidden span with data-doi class
        doi_container = ref_elem.find('div', class_='extra-links getFTR')
        if doi_container:
            doi_span = doi_container.find('span', class_='hidden data-doi')
            if doi_span:
                # Get the text directly from the span's first text node
                for text in doi_span.stripped_strings:
                    if text.startswith('10.'):
                        ref.doi = text
                        break
        
        # Fallback to looking for DOI in href if not found in span
        if not ref.doi:
            doi_elem = ref_elem.find('a', href=re.compile(r'doi.org'))
            if doi_elem:
                doi_href = doi_elem['href']
                if doi_href.startswith('https://doi.org/'):
                    ref.doi = doi_href[len('https://doi.org/'):]
                else:
                    ref.doi = doi_href
        
        if ref.doi:
            pass
        
        return ref
        
    except Exception as e:
        print(f"Error parsing reference: {str(e)}")
        return ref

def parse_wiley_html(file_path: str) -> ArticleMetadata:
    """
    Parse a Wiley HTML file to extract paper metadata
    Args:
        file_path: Path to the HTML file
    Returns:
        ArticleMetadata object containing the paper's metadata and references
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')
        
        # Extract title
        title = None
        title_elem = soup.find('h1', class_='citation__title')
        if title_elem:
            title = title_elem.get_text().strip()
        
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
        
        # Extract volume and issue from volume-issue class
        volume = None
        issue = None
        volume_issue_elem = soup.find('a', class_='volume-issue')
        if volume_issue_elem:
            volume_text = volume_issue_elem.text
            # Match "Volume X, Issue Y" format
            match = re.match(r'Volume\s+(\d+),\s*Issue\s+(\d+)', volume_text)
            if match:
                volume = match.group(1)
                issue = match.group(2)
        
        # Extract page numbers from citation__page-range class
        page_first = None
        page_last = None
        pages_elem = soup.find('span', class_='citation__page-range')
        if pages_elem:
            pages_text = pages_elem.text
            # Match "p. X-Y" format
            match = re.search(r'p\.\s*(\d+)-(\d+)', pages_text)
            if match:
                page_first = match.group(1)
                page_last = match.group(2)
        
        # Extract publication date
        date_elem = soup.find('span', class_='epub-date')
        if date_elem:
            try:
                # Parse date text like "First published: 03 December 2003"
                date_text = date_elem.get_text().strip()
                if 'First published:' in date_text:
                    date_text = date_text.split('First published:')[1].strip()
                published_date = datetime.strptime(date_text, '%d %B %Y').date()
            except (ValueError, AttributeError):
                published_date = None
        else:
            published_date = None
        
        # Extract citation count from citedby-section link
        citations = None
        citations_elem = soup.find('a', href='#citedby-section')
        if citations_elem:
            citations_text = citations_elem.text
            citations_match = re.search(r'(\d+)', citations_text)
            if citations_match:
                citations = int(citations_match.group(1))
        
        # Extract DOI from epub-doi class
        doi = None
        doi_elem = soup.find('a', class_='epub-doi')
        if doi_elem:
            doi_href = doi_elem.get('href')
            if doi_href and doi_href.startswith('https://doi.org/'):
                doi = doi_href[len('https://doi.org/'):]
        
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
        
        return ArticleMetadata(
            title=title,
            authors=authors,
            published_date=published_date,
            volume=volume,
            issue=issue,
            page_first=page_first,
            page_last=page_last,
            citations=citations,
            doi=doi,
            references=references
        )
        
    except Exception as e:
        print(f"Error parsing HTML file: {str(e)}")
        return ArticleMetadata(
            title=None,
            authors=[],
            published_date=None,
            volume=None,
            issue=None,
            page_first=None,
            page_last=None,
            citations=None,
            doi=None,
            references=[]
        )

def process_html_files(html_dir: str, output_file_json: str, output_file_csv: str) -> List[dict]:
    """
    Process all HTML files in the specified directory and save metadata to JSON and CSV files.
    
    Args:
        html_dir: Path to directory containing HTML files
        output_file_json: Path to save the output JSON file
        output_file_csv: Path to save the output CSV file
    
    Returns:
        List of dictionaries containing metadata for each article
    """
    html_files = list(Path(html_dir).glob('*.html'))
    all_metadata = []
    csv_data = []
    
    for html_file in html_files:
        print(f"Processing {html_file}...")
        try:
            metadata = parse_wiley_html(str(html_file))
            
            # Base article metadata
            article_metadata = {
                'article.title': metadata.title,
                'article.authors': ';'.join(metadata.authors),
                'article.published_date': metadata.published_date.isoformat() if metadata.published_date else None,
                'article.volume': metadata.volume,
                'article.issue': metadata.issue,
                'article.page_first': metadata.page_first,
                'article.page_last': metadata.page_last,
                'article.citations': metadata.citations,
                'article.doi': metadata.doi,
            }
            
            # Create a row for each reference
            for ref in metadata.references:
                ref_dict = {
                    'reference.ref_type': ref.ref_type.value if ref.ref_type else None,
                    'reference.authors': ';'.join(ref.authors),
                    'reference.year': ref.year,
                    'reference.title': ref.title,
                    'reference.journal': ref.journal,
                    'reference.volume': ref.volume,
                    'reference.page_first': ref.page_first,
                    'reference.page_last': ref.page_last,
                    'reference.doi': ref.doi,
                    'reference.working_paper_institution': ref.working_paper_institution,
                    'reference.book_title': ref.book_title,
                    'reference.chapter_title': ref.chapter_title
                }
                
                # Combine article metadata with reference data
                row = {**article_metadata, **ref_dict}
                csv_data.append(row)
            
            # Store complete metadata for JSON
            metadata_dict = {**article_metadata, 'references': [
                {
                    'ref_type': ref.ref_type.value if ref.ref_type else None,
                    'authors': ref.authors,
                    'year': ref.year,
                    'title': ref.title,
                    'journal': ref.journal,
                    'volume': ref.volume,
                    'page_first': ref.page_first,
                    'page_last': ref.page_last,
                    'doi': ref.doi,
                    'working_paper_institution': ref.working_paper_institution,
                    'book_title': ref.book_title,
                    'chapter_title': ref.chapter_title
                } for ref in metadata.references
            ]}
            all_metadata.append(metadata_dict)
            print(f"Successfully processed {metadata_dict['article.title']}")
        except Exception as e:
            print(f"Error processing {html_file}: {e}")
    
    # Save JSON
    with open(output_file_json, 'w', encoding='utf-8') as f:
        json.dump(all_metadata, f, ensure_ascii=False, indent=2)
    
    # Save CSV efficiently using pandas
    if csv_data:
        df = pd.DataFrame(csv_data)
        df.to_csv(output_file_csv, index=False, encoding='utf-8')
    
    print(f"\nProcessed {len(all_metadata)} articles")
    print(f"JSON data saved to {output_file_json}")
    print(f"CSV data saved to {output_file_csv}")
    
    return all_metadata

def test_single_file(file_path: str) -> None:
    """
    Test parsing of a single HTML file and print the results.
    
    Args:
        file_path: Path to the HTML file to parse
    """
    metadata = parse_wiley_html(file_path)
    print(f"Title: {metadata.title}")
    print(f"Authors: {metadata.authors}")
    print(f"Published Date: {metadata.published_date}")
    print(f"Volume: {metadata.volume}")
    print(f"Issue: {metadata.issue}")
    print(f"Pages: {metadata.page_first}-{metadata.page_last}")
    print(f"Citations: {metadata.citations}")
    print(f"DOI: {metadata.doi}")
    print("\nReferences:")
    for i, ref in enumerate(metadata.references, 1):
        print(f"\n{i}. Reference Type: {ref.ref_type.value if ref.ref_type else None}")
        print(f"   Authors: {ref.authors}")
        print(f"   Year: {ref.year}")
        print(f"   Title: {ref.title}")
        if ref.ref_type == ReferenceType.ARTICLE:
            print(f"   Journal: {ref.journal}")
            print(f"   Volume: {ref.volume}")
            print(f"   Pages: {ref.page_first}-{ref.page_last}")
        elif ref.ref_type == ReferenceType.WORKING_PAPER:
            print(f"   Working Paper Institution: {ref.working_paper_institution}")
        elif ref.ref_type == ReferenceType.BOOK:
            print(f"   Book Title: {ref.book_title}")
            if ref.chapter_title:
                print(f"   Chapter Title: {ref.chapter_title}")
        print(f"   DOI: {ref.doi}")

if __name__ == "__main__":
    # Process files in downloaded_html directory and save to JF_articles.json
    process_html_files("downloaded_html", "JF_articles.json", "JF_articles.csv")

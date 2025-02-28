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
from multiprocessing import Pool
from functools import partial

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
    # Remove extra quotation marks at start and end
    text = re.sub(r'^["\']+|["\']+$', '', text)
    # Replace multiple quotes with single quotes
    text = re.sub(r'"{2,}', '"', text)
    text = re.sub(r"'{2,}", "'", text)
    return text.strip()

def clean_journal(text: str) -> str:
    """Clean journal title by removing any mixed content"""
    if not text:
        return ""
        
    # First clean with standard function
    text = clean_text(text)
    
    # Remove any text after author names (but preserve & and common joining words)
    text = re.sub(r',\s*[A-Z][a-z]+(?!\s+(&|and|of|the|in|on))', '', text)
    
    # Remove any text after common journal words if they appear twice
    journal_words = ['Journal', 'Proceedings', 'Conference', 'Transactions']
    for word in journal_words:
        matches = list(re.finditer(word, text))
        if len(matches) > 1:
            text = text[:matches[1].start()].strip()
    
    # If the text starts with a bracket, it's probably not a journal
    if text.startswith('['):
        return ""
    
    # Remove any text after numbers that aren't part of the journal name
    text = re.sub(r'\s+\d+(?!\w)', '', text)
    
    # Remove any text after these words only if they're not part of the journal name
    stop_patterns = [
        r'\s+using\s+.*$',
        r'\s+with\s+.*$',
        r'\s+based\s+on\s+.*$',
        r'\s+for\s+.*$',
        r'\s+in\s+(?!.*Journal).*$'  # Only remove 'in' if not followed by 'Journal'
    ]
    
    for pattern in stop_patterns:
        text = re.sub(pattern, '', text)
    
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
        # Extract authors from class='name'
        authors = []
        name_divs = ref_elem.find_all(class_='name')
        
        for name_div in name_divs:
            surname = name_div.find(class_='surname')
            given_names = name_div.find(class_='given-names')
            
            if surname and given_names:
                surname_text = clean_text(surname.get_text())
                given_names_text = clean_text(given_names.get_text())
                
                if surname_text and given_names_text:
                    full_name = f"{surname_text} {given_names_text}"
                    if len(full_name.strip()) > 2:  # Ignore very short names
                        authors.append(full_name)
                elif surname_text and len(surname_text.strip()) > 2:
                    # If we only have a surname but it's substantial
                    authors.append(surname_text)
        
        ref.authors = authors
        
        # Extract year from class='year'
        year_elem = ref_elem.find(class_='year')
        if year_elem:
            ref.year = extract_year(year_elem.get_text())
            
        # Extract source information
        source_elem = ref_elem.find(class_='source')
        
        # Determine reference type and extract appropriate fields
        text_lower = ref_elem.get_text().lower()
        if 'working paper' in text_lower or 'discussion paper' in text_lower:
            ref.ref_type = ReferenceType.WORKING_PAPER
            # First try article-title, then fall back to source for title
            title_elem = ref_elem.find(class_='article-title')
            if title_elem:
                ref.title = clean_text(title_elem.get_text())
            elif source_elem:
                ref.title = clean_text(source_elem.get_text())
            
            # Handle publisher name and location
            publisher_parts = []
            publisher_elem = ref_elem.find(class_='publisher-name')
            if publisher_elem:
                publisher_parts.append(clean_text(publisher_elem.get_text()))
            
            publisher_loc = ref_elem.find(class_='publisher-loc')
            if publisher_loc:
                publisher_parts.append(clean_text(publisher_loc.get_text()))
            
            if publisher_parts:
                ref.working_paper_institution = ', '.join(publisher_parts)
                
        elif ref_elem.find(class_='article-title'):
            ref.ref_type = ReferenceType.ARTICLE
            title_elem = ref_elem.find(class_='article-title')
            if title_elem:
                ref.title = clean_text(title_elem.get_text())
            if source_elem:
                ref.journal = clean_journal(source_elem.get_text())
            
            # Extract volume - simplified
            volume_elem = ref_elem.find(class_='volume')
            if volume_elem:
                vol_text = volume_elem.get_text().strip()
                if vol_text.isdigit():
                    ref.volume = vol_text
            
            # Extract page numbers - simplified
            fpage = ref_elem.find(class_='fpage')
            lpage = ref_elem.find(class_='lpage')
            if fpage:
                fpage_text = fpage.get_text().strip()
                if fpage_text.isdigit():
                    ref.page_first = fpage_text
            if lpage:
                lpage_text = lpage.get_text().strip()
                if lpage_text.isdigit():
                    ref.page_last = lpage_text
                
        else:
            ref.ref_type = ReferenceType.BOOK
            source_elem = ref_elem.find(class_='source')
            if source_elem:
                ref.book_title = clean_text(source_elem.get_text())
            chapter_elem = ref_elem.find(class_='chapter-title')
            if chapter_elem:
                ref.chapter_title = clean_text(chapter_elem.get_text())

        # Extract DOI if present - check both direct doi.org links and crossref links
        doi = None
        doi_elem = ref_elem.find('a', href=re.compile(r'doi.org'))
        if doi_elem and 'href' in doi_elem.attrs:
            doi_href = doi_elem['href']
            if doi_href.startswith('https://doi.org/'):
                doi = doi_href[len('https://doi.org/'):]
            elif doi_href.startswith('http://dx.doi.org/'):
                doi = doi_href[len('http://dx.doi.org/'):]
        
        # If no DOI found yet, check for crossref link
        if not doi:
            crossref_div = ref_elem.find(class_='crossref-doi')
            if crossref_div:
                crossref_link = crossref_div.find('a', href=re.compile(r'doi.org'))
                if crossref_link and 'href' in crossref_link.attrs:
                    doi_href = crossref_link['href']
                    if doi_href.startswith('https://doi.org/'):
                        doi = doi_href[len('https://doi.org/'):]
                    elif doi_href.startswith('http://dx.doi.org/'):
                        doi = doi_href[len('http://dx.doi.org/'):]
        
        ref.doi = doi
        
        return ref
        
    except Exception as e:
        print(f"Error parsing reference: {str(e)}")
        return ref

def parse_oup_html(file_path: str) -> ArticleMetadata:
    """
    Parse a OUP HTML file to extract paper metadata
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
        title_elem = soup.find('h1', class_='wi-article-title article-title-main accessible-content-title at-articleTitle')
        if title_elem:
            title = title_elem.get_text().strip()
        
        # Extract authors (using set to remove duplicates)
        authors = []
        seen_authors = set()
        
        # Try finding authors in accordion tabs
        author_elems = soup.find_all('a', class_='info-card-name')
        if not author_elems:  # Try alternative author elements
            author_elems = soup.find_all('div', class_='info-card-name')
        
        for author_elem in author_elems:
            name = None
            # Try different ways to get author name
            if author_elem.find('span', class_='info-card-footnote'):
                name = author_elem.contents[0].strip()
            elif author_elem.find('span'):
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
        
        # Extract volume and issue from ww-citation-primary class
        volume = None
        issue = None
        citation_primary = soup.find('div', class_='ww-citation-primary')
        if citation_primary:
            citation_text = citation_primary.get_text()
            volume_match = re.search(r'Volume\s+(\d+)', citation_text)
            issue_match = re.search(r'Issue\s+(\d+)', citation_text)
            if volume_match:
                volume = volume_match.group(1)
            if issue_match:
                issue = issue_match.group(1)
        
        # Extract page numbers from ww-citation-primary class
        page_first = None
        page_last = None
        citation_primary = soup.find('div', class_='ww-citation-primary')
        if citation_primary:
            citation_text = citation_primary.get_text()
            # Match "Pages X–Y" format
            match = re.search(r'Pages\s+(\d+)[–-](\d+)', citation_text)
            if match:
                page_first = match.group(1)
                page_last = match.group(2)
        
        # Extract publication date
        date_elem = soup.find('span', class_='citation-date')
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
        
        # Set citation count to None
        citations = None
        
        # Extract DOI from ww-citation-primary class
        doi = None
        citation_primary = soup.find('div', class_='ww-citation-primary')
        if citation_primary:
            doi_elem = citation_primary.find('a', href=re.compile(r'doi.org'))
            if doi_elem:
                doi_href = doi_elem['href']
            if doi_href.startswith('https://doi.org/'):
                doi = doi_href[len('https://doi.org/'):]
        
        # Extract references
        references = []
        ref_list = soup.find('div', class_='ref-list js-splitview-ref-list')
        if ref_list:
            ref_items = ref_list.find_all('div', class_='ref-content')
            for ref_item in ref_items:
                # Remove any citation links or web elements before parsing
                for elem in ref_item.find_all(['button']):
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

def process_single_file(file_path: str) -> Optional[dict]:
    """Process a single HTML file and return its metadata as a dictionary"""
    try:
        print(f"Processing {file_path}...")
        metadata = parse_oup_html(str(file_path))
        
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
            'references': [
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
            ]
        }
        print(f"Successfully processed {article_metadata['article.title']}")
        return article_metadata
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None

def process_html_files(html_dir: str, output_file_json: str, output_file_csv: str) -> List[dict]:
    """
    Process all HTML files in the specified directory and save metadata to JSON and CSV files.
    Uses parallel processing to speed up the operation.
    
    Args:
        html_dir: Path to directory containing HTML files
        output_file_json: Path to save the output JSON file
        output_file_csv: Path to save the output CSV file
    
    Returns:
        List of dictionaries containing metadata for each article
    """
    html_files = list(Path(html_dir).glob('*.html'))
    
    # Process files in parallel using 4 cores
    with Pool(processes=4) as pool:
        all_metadata = list(filter(None, pool.map(process_single_file, html_files)))
    
    # Prepare CSV data
    csv_data = []
    for metadata in all_metadata:
        article_base = {k: v for k, v in metadata.items() if k != 'references'}
        for ref in metadata['references']:
            row = {**article_base, **{f'reference.{k}': v for k, v in ref.items()}}
            csv_data.append(row)
    
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
    metadata = parse_oup_html(file_path)
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
    # Process all RFS articles
    input_dir = "downloaded_html/RFS"
    output_json = "RFS_articles.json"
    output_csv = "RFS_articles.csv"
    
    print(f"Processing HTML files from {input_dir}...")
    articles = process_html_files(input_dir, output_json, output_csv)
    print(f"\nProcessed {len(articles)} articles")
    print(f"Results saved to:")
    print(f"- {output_json}")
    print(f"- {output_csv}")

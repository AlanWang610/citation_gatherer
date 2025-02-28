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
from dotenv import load_dotenv
from openai import OpenAI
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Add at the top with other globals
llm_call_counter = 0

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

async def llm_backup(text: str, ref_type: ReferenceType) -> dict:
    """Async backup function that uses LLM to parse reference text when regular parsing fails"""
    global llm_call_counter
    
    # Load environment variables and configure OpenAI only when needed
    load_dotenv()
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    # Increment counter
    llm_call_counter += 1
    
    # Define system prompts based on reference type
    if ref_type == ReferenceType.ARTICLE:
        system_prompt = """Please take this input, which is in the form {article: string} and identify the title, journal, year of publication, volume, and first and last page numbers. Respond with a JSON object containing these fields: "title", "journal", "year", "volume", "page_start", "page_end"."""
        input_text = f"{{article: {text}}}"
    elif ref_type == ReferenceType.WORKING_PAPER:
        system_prompt = """Please take this input, which is in the form {working_paper: string} and identify the title, working_paper_institution, and year. Respond with a JSON object containing these fields: "title", "working_paper_institution", "year"."""
        input_text = f"{{working_paper: {text}}}"
    else:  # ReferenceType.BOOK
        system_prompt = """Please take this input, which is in the form {book: string} and identify the book title, chapter title, and year of publication. Respond with a JSON object containing these fields: "book_title", "chapter_title", "year"."""
        input_text = f"{{book: {text}}}"

    max_retries = 3
    retry_delay = 30  # seconds

    for attempt in range(max_retries):
        try:
            # Run OpenAI call in a thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as pool:
                response = await loop.run_in_executor(
                    pool,
                    lambda: client.chat.completions.create(
                        model="gpt-4o-mini-2024-07-18",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": input_text}
                        ],
                        temperature=0,
                        response_format={"type": "json_object"}
                    )
                )

            result = json.loads(response.choices[0].message.content)
            return map_result_to_output(result, ref_type)

        except Exception as e:
            error_msg = str(e).lower()
            if attempt < max_retries - 1 and ("rate" in error_msg or "429" in error_msg):
                print(f"Rate limit hit, waiting {retry_delay} seconds before retry...")
                await asyncio.sleep(retry_delay)
                continue
            else:
                print(f"Error in LLM backup: {str(e)}")
                return {}

def map_result_to_output(result: dict, ref_type: ReferenceType) -> dict:
    """Map LLM response to output format based on reference type"""
    if ref_type == ReferenceType.ARTICLE:
        return {
            "title": result.get("title"),
            "journal": result.get("journal"),
            "year": result.get("year"),
            "volume": result.get("volume"),
            "page_first": result.get("page_start"),
            "page_last": result.get("page_end")
        }
    elif ref_type == ReferenceType.WORKING_PAPER:
        return {
            "title": result.get("title"),
            "institution": result.get("working_paper_institution"),
            "year": result.get("year")
        }
    else:  # ReferenceType.BOOK
        return {
            "book_title": result.get("book_title"),
            "chapter_title": result.get("chapter_title"),
            "year": result.get("year")
        }

def format_author_name(author: str) -> str:
    """
    Format author name, handling cases like "Palepu, K." -> "K. Palepu"
    Returns empty string if the input doesn't match expected patterns
    """
    author = clean_text(author)
    if not author:
        return ""
        
    # Case 1: "Lastname, F." or "Lastname, F" format
    initial_match = re.match(r'([^,]+),\s*([A-Z]\.?)\s*$', author)
    if initial_match:
        lastname = initial_match.group(1).strip()
        initial = initial_match.group(2).strip()
        if not initial.endswith('.'):
            initial += '.'
        return f"{initial} {lastname}"
    
    # Case 2: Already in "F. Lastname" format
    if re.match(r'^[A-Z]\.\s+\w+$', author):
        return author
        
    # Case 3: Just a name without initials
    if re.match(r'^[A-Z][a-z]+$', author):
        return author
        
    return author

def parse_authors(authors_text: str) -> List[str]:
    """Parse and format a list of authors"""
    if not authors_text:
        return []
    
    # Split on commas, but keep comma-separated initial groups together
    authors = []
    current_author = ""
    
    parts = authors_text.split(',')
    for i, part in enumerate(parts):
        part = part.strip()
        
        # If this part looks like an initial (single letter)
        if re.match(r'^[A-Z]\.?\s*$', part):
            current_author += f", {part}"
        else:
            # If we have a pending author, format and add it
            if current_author:
                authors.append(format_author_name(current_author))
            current_author = part
    
    # Add the last author if any
    if current_author:
        authors.append(format_author_name(current_author))
    
    return [a for a in authors if a]  # Remove any empty strings

async def parse_reference(ref_elem) -> Reference:
    """Parse a reference from its HTML element using specific class names"""
    ref = Reference(
        authors=[], year=None, title=None, journal=None,
        volume=None, page_first=None, page_last=None, doi=None,
        ref_type=ReferenceType.ARTICLE
    )
    
    try:
        # First check if it's a working paper by looking at both contribution and host divs
        contribution = ref_elem.find('div', class_='contribution')
        host_div = ref_elem.find('div', class_='host u-font-sans')
        other_ref = ref_elem.find('div', class_='other-ref')
        
        is_working_paper = False
        working_paper_text = ""
        
        # Check for working paper or dissertation in various locations (case-insensitive)
        working_paper_terms = [
            'working paper', 
            'dissertation',
            'research paper',
            'discussion paper',
            'brookings paper',
            'nber paper',
            'unpublished paper',
            'mimeo',
            'manuscript',
            'work in progress'
        ]
        
        if contribution:
            title_div = contribution.find('div', class_='title text-m')
            if title_div and any(term in title_div.get_text().lower() for term in working_paper_terms):
                is_working_paper = True
                working_paper_text = title_div.get_text()
        
        if host_div and any(term in host_div.get_text().lower() for term in working_paper_terms):
            is_working_paper = True
            working_paper_text = host_div.get_text().strip()
        
        if other_ref and any(term in other_ref.get_text().lower() for term in working_paper_terms):
            is_working_paper = True
            working_paper_text = other_ref.get_text().strip()
        
        if is_working_paper:
            ref.ref_type = ReferenceType.WORKING_PAPER
            
            # Try to extract authors and year from the beginning of text
            if working_paper_text:
                # Look for pattern: Author1, Author2, year.
                author_year_match = re.match(r'([^,]+(?:,\s*[^,]+)*),\s*(\d{4})', working_paper_text)
                if author_year_match:
                    authors_text = author_year_match.group(1)
                    ref.authors = parse_authors(authors_text)
                    ref.year = author_year_match.group(2)
                    
                    # Try to extract title after year and before "Working paper"
                    title_match = re.search(r'\d{4}\.\s*(.*?)\s*(?:[Ww]orking paper|[Dd]issertation|Ph\.D\.|PhD)', working_paper_text)
                    if title_match:
                        ref.title = clean_text(title_match.group(1))
                
                # Try to find institution after "Working paper" or similar terms
                institution_match = None
                if 'Working paper' in working_paper_text or 'working paper' in working_paper_text:
                    institution_match = re.search(r'[Ww]orking paper,\s*(.*?)(?:[.,]|$)', working_paper_text)
                elif any(term in working_paper_text for term in ['Dissertation', 'dissertation', 'Ph.D.', 'PhD']):
                    institution_match = re.search(r'(?:Dissertation|Ph\.D\.|PhD),\s*(.*?)(?:[.,]|$)', working_paper_text)
                
                if institution_match:
                    ref.working_paper_institution = clean_text(institution_match.group(1))
                
                # If no authors found, try contribution div
                if not ref.authors and contribution:
                    authors_div = contribution.find('div', class_='authors u-font-sans')
                    if authors_div:
                        authors_text = authors_div.get_text()
                        ref.authors = parse_authors(authors_text)
            
            # Only use LLM if we're missing the institution
            if not ref.working_paper_institution:
                backup_result = await llm_backup(ref_elem.get_text(), ReferenceType.WORKING_PAPER)
                ref.title = backup_result.get('title') or ref.title
                ref.working_paper_institution = backup_result.get('institution') or ref.working_paper_institution
                ref.year = backup_result.get('year') or ref.year
            return ref
        
        # If not a working paper, continue with normal parsing...
        # Extract title and authors from contribution div first (this is consistent across formats)
        if contribution:
            # Extract authors
            authors_div = contribution.find('div', class_='authors u-font-sans')
            if authors_div:
                authors_text = authors_div.get_text()
                ref.authors = parse_authors(authors_text)
            
            # Extract title
            title_div = contribution.find('div', class_='title text-m')
            if title_div:
                ref.title = clean_text(title_div.get_text())
        
        # Try to parse the host div
        host_div = ref_elem.find('div', class_='host u-font-sans')
        if host_div:
            host_text = host_div.get_text().strip()
            
            # Check if it's a book by looking for editors, publishers, or common publishing locations
            book_indicators = [
                '(Eds.)', '(Ed.)',  # Editors
                'Elsevier', 'Press', 'Publisher',  # Publishers
                'Amsterdam', 'London', 'New York', 'Boston', 'Oxford',  # Common publishing locations
                'Cambridge', 'Chicago', 'MIT'  # Academic publishers
            ]
            
            if any(indicator in host_text for indicator in book_indicators):
                ref.ref_type = ReferenceType.BOOK
                backup_result = await llm_backup(host_text, ReferenceType.BOOK)
                ref.book_title = backup_result.get('book_title')
                ref.chapter_title = backup_result.get('chapter_title')
                ref.year = backup_result.get('year')
                return ref
            
            # First try to match the standard journal format exactly
            standard_journal_match = re.search(r'^([^,]+),\s*(\d+)\s*\((\d{4})\),\s*pp\.\s*(\d+)-(\d+)$', host_text)
            if standard_journal_match:
                ref.ref_type = ReferenceType.ARTICLE
                ref.journal = clean_journal(standard_journal_match.group(1))
                ref.volume = standard_journal_match.group(2)
                ref.year = standard_journal_match.group(3)
                ref.page_first = standard_journal_match.group(4)
                ref.page_last = standard_journal_match.group(5)
            else:
                # If it's not a standard format, use LLM backup
                backup_result = await llm_backup(host_text, ref.ref_type)
                if ref.ref_type == ReferenceType.ARTICLE:
                    ref.journal = backup_result.get('journal')
                    ref.volume = backup_result.get('volume')
                    ref.year = backup_result.get('year')
                    ref.page_first = backup_result.get('page_first')
                    ref.page_last = backup_result.get('page_last')
            return ref
        
        # Extract DOI if present
        doi = None
        doi_elem = ref_elem.find('a', href=re.compile(r'doi.org'))
        if doi_elem and 'href' in doi_elem.attrs:
            doi_href = doi_elem['href']
            if doi_href.startswith('https://doi.org/'):
                doi = doi_href[len('https://doi.org/'):]
            elif doi_href.startswith('http://dx.doi.org/'):
                doi = doi_href[len('http://dx.doi.org/'):]
        ref.doi = doi
        
        # Add validation at the end without prints
        if ref.ref_type == ReferenceType.WORKING_PAPER and not ref.working_paper_institution:
            if ref.title:  # Only if we have a title to help identify the paper
                backup_result = await llm_backup(ref_elem.get_text(), ReferenceType.WORKING_PAPER)
                ref.working_paper_institution = backup_result.get('institution')
                ref.year = backup_result.get('year') or ref.year
        
        return ref
        
    except Exception as e:
        if "cannot access local variable 'doi'" not in str(e):
            print(f"Error parsing reference: {str(e)}")
            print(f"Reference text: {ref_elem.get_text()}")
        return ref

async def parse_sciencedirect_html_async(file_path: str) -> ArticleMetadata:
    """Async version of parse_sciencedirect_html"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')
        
        # Extract title from new location
        title = None
        title_elem = soup.find('span', class_='title-text')
        if title_elem:
            title = clean_text(title_elem.get_text())
        
        # Extract authors from new location
        authors = []
        author_elems = soup.find_all('span', class_='react-xocs-alternative-link')
        for author_elem in author_elems:
            given_name = author_elem.find('span', class_='given-name')
            surname = author_elem.find('span', class_='surname')
            
            if given_name and surname:
                full_name = f"{clean_text(given_name.get_text())} {clean_text(surname.get_text())}"
                if full_name.strip():
                    authors.append(full_name)
        
        # Extract DOI from new location
        doi = None
        doi_elem = soup.find('a', class_='anchor doi anchor-primary')
        if doi_elem and 'href' in doi_elem.attrs:
            doi_href = doi_elem['href']
            if doi_href.startswith('https://doi.org/'):
                doi = doi_href[len('https://doi.org/'):]
        
        # Extract volume and issue from new location
        volume = None
        issue = None
        vol_issue_elem = soup.find('span', class_='anchor-text', string=re.compile(r'Volume \d+, Issue \d+'))
        if vol_issue_elem:
            vol_match = re.search(r'Volume (\d+)', vol_issue_elem.get_text())
            issue_match = re.search(r'Issue (\d+)', vol_issue_elem.get_text())
            if vol_match:
                volume = vol_match.group(1)
            if issue_match:
                issue = issue_match.group(1)
        
        # Extract publication date and page numbers from new location
        published_date = None
        page_first = None
        page_last = None
        
        pub_info = soup.find('div', class_='text-xs')
        if pub_info:
            # Extract date
            date_match = re.search(r'([A-Za-z]+)\s+(\d{4})', pub_info.get_text())
            if date_match:
                month = date_match.group(1)
                year = date_match.group(2)
                try:
                    published_date = datetime.strptime(f"01 {month} {year}", "%d %B %Y").date()
                except ValueError:
                    published_date = None
            
            # Extract pages
            pages_match = re.search(r'Pages\s+(\d+)-(\d+)', pub_info.get_text())
            if pages_match:
                page_first = pages_match.group(1)
                page_last = pages_match.group(2)
        
        # Set citation count to None
        citations = None
        
        # Extract references concurrently
        ref_list = soup.find('ol', class_='references')
        if ref_list:
            ref_items = ref_list.find_all('li')
            references = await process_references(ref_items)
        else:
            references = []
        
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

async def process_references(ref_items) -> List[Reference]:
    """Process references concurrently"""
    references = []
    tasks = []
    
    for ref_item in ref_items:
        ref_span = ref_item.find('span', class_='reference')
        if ref_span:
            ref = await parse_reference(ref_span)  # Now awaiting the async function
            if ref.authors:  # Only add if we found at least one author
                references.append(ref)
    
    return references

def process_single_file(file_path: str) -> Optional[dict]:
    """Process a single HTML file and return its metadata as a dictionary"""
    try:
        print(f"Processing {file_path}...")
        metadata = asyncio.run(parse_sciencedirect_html_async(str(file_path)))
        
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

async def test_single_file_async(file_path: str) -> None:
    """Async version of test_single_file"""
    global llm_call_counter
    llm_call_counter = 0
    
    metadata = await parse_sciencedirect_html_async(file_path)
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
    
    # Add at the end of the function
    print(f"\nNumber of LLM backup calls made: {llm_call_counter}")
    # TODO: Remove this debug counter later

if __name__ == "__main__":
    # Process all files in JFE directory
    input_dir = "downloaded_html/JFE"
    output_json = "JFE_articles.json"
    output_csv = "JFE_articles.csv"
    
    print(f"Processing files from {input_dir}...")
    all_metadata = process_html_files(input_dir, output_json, output_csv)

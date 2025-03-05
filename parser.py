from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Type
from enum import Enum
import re
from datetime import datetime
import os
import json
import csv
from dataclasses import asdict
from pathlib import Path
import pandas as pd
from multiprocessing import Pool, Value
from functools import partial
from dotenv import load_dotenv
import openai
import asyncio
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import ProcessPoolExecutor

# Shared enums and dataclasses
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

# Base Parser class with shared functionality
class BaseParser:
    def __init__(self):
        self.llm_call_counter = 0
        self.working_paper_terms = {
            'working paper', 'dissertation', 'research paper',
            'discussion paper', 'brookings paper', 'nber paper',
            'unpublished paper', 'unpublished', 'mimeo',
            'manuscript', 'work in progress'
        }

    # Shared utility functions
    def clean_text(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[.,;:\s]+$', '', text)
        text = re.sub(r'^[.,;:\s]+', '', text)
        text = re.sub(r'^["\']+|["\']+$', '', text)
        text = re.sub(r'"{2,}', '"', text)
        text = re.sub(r"'{2,}", "'", text)
        return text.strip()

    def clean_journal(self, text: str) -> str:
        if not text:
            return ""
        text = self.clean_text(text)
        text = re.sub(r',\s*[A-Z][a-z]+(?!\s+(&|and|of|the|in|on))', '', text)
        
        journal_words = ['Journal', 'Proceedings', 'Conference', 'Transactions']
        for word in journal_words:
            matches = list(re.finditer(word, text))
            if len(matches) > 1:
                text = text[:matches[1].start()].strip()
        
        if text.startswith('['):
            return ""
        
        text = re.sub(r'\s+\d+(?!\w)', '', text)
        
        stop_patterns = [
            r'\s+using\s+.*$',
            r'\s+with\s+.*$',
            r'\s+based\s+on\s+.*$',
            r'\s+for\s+.*$',
            r'\s+in\s+(?!.*Journal).*$'
        ]
        
        for pattern in stop_patterns:
            text = re.sub(pattern, '', text)
        
        return text.strip()

    def format_author_name(self, author: str) -> str:
        """Format author name, converting 'Last, First' to 'First Last' format"""
        if not author or ',' not in author:
            return author
        
        last_name, first_name = author.split(',', 1)
        return f"{first_name.strip()} {last_name.strip()}"

    async def llm_backup(self, text: str, ref_type: ReferenceType) -> dict:
        """Async backup function that uses LLM to parse reference text when regular parsing fails"""
        load_dotenv()
        client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

        self.llm_call_counter += 1
        # Add delay between concurrent LLM calls to avoid rate limits
        if self.llm_call_counter > 1:
            await asyncio.sleep(0.05)  # 50ms delay
        
        if ref_type == ReferenceType.ARTICLE:
            system_prompt = """Please take this input, which is in the form {article: string} and identify the title, journal, year of publication, volume, and first and last page numbers. Respond with a JSON object containing these fields: "title", "journal", "year", "volume", "page_start", "page_end"."""
            input_text = f"{{article: {text}}}"
        elif ref_type == ReferenceType.WORKING_PAPER:
            system_prompt = """Please take this input, which is in the form {working_paper: string} and identify the title, working_paper_institution, and year. Respond with a JSON object containing these fields: "title", "working_paper_institution", "year"."""
            input_text = f"{{working_paper: {text}}}"
        else:  # ReferenceType.BOOK
            system_prompt = """Please take this input, which is in the form {book: string} and identify the book title, chapter title, and year of publication. Respond with a JSON object containing these fields: "book_title", "chapter_title", "year"."""
            input_text = f"{{book: {text}}}"

        max_retries = 50
        retry_delay = 30

        for attempt in range(max_retries):
            try:
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
                
                # Format author names if present in result
                if 'authors' in result:
                    result['authors'] = [self.format_author_name(author) for author in result['authors']]
                
                return self.map_result_to_output(result, ref_type)

            except Exception as e:
                error_msg = str(e).lower()
                if attempt < max_retries - 1 and ("rate" in error_msg or "429" in error_msg):
                    print(f"Rate limit hit on attempt {attempt + 1}/{max_retries}, waiting {retry_delay} seconds before retry... Error: {str(e)}")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    print(f"Error in LLM backup: {str(e)}")
                    return {}

    def map_result_to_output(self, result: dict, ref_type: ReferenceType) -> dict:
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

    # Abstract methods that must be implemented by subclasses
    async def parse_reference(self, ref_elem) -> Reference:
        raise NotImplementedError

    async def parse_html(self, file_path: str) -> ArticleMetadata:
        raise NotImplementedError

# Factory class to get the appropriate parser
class ParserFactory:
    @staticmethod
    def get_parser(platform: str) -> BaseParser:
        parsers = {
            'wiley': WileyParser,
            'oup': OUPParser,
            'sciencedirect': ScienceDirectParser
        }
        parser_class = parsers.get(platform.lower())
        if not parser_class:
            raise ValueError(f"Unknown platform: {platform}")
        return parser_class()

# Shared processing functions
async def process_single_file(file_path: str, parser: BaseParser, api_key: str, counter: Value) -> Optional[dict]:
    """Process a single HTML file and return its metadata as a dictionary"""
    try:
        # Set the API key in the environment for this process
        os.environ['OPENAI_API_KEY'] = api_key
        
        metadata = await parser.parse_html(str(file_path))
        
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
        
        with counter.get_lock():
            counter.value += 1
            print(f"Progress: {counter.value}/{total_files} articles processed")
        print(f"Successfully processed {article_metadata['article.title']}")
        
        # Clean up metadata object
        metadata.references = []
        
        # Force garbage collection
        import gc
        gc.collect()
        
        return article_metadata
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None

async def process_html_files(html_dir: str, output_file_json: str, output_file_csv: str, platform: str) -> List[dict]:
    """Process all HTML files in the specified directory and save metadata to JSON and CSV files."""
    # Load environment variables at the start
    load_dotenv()
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment variables")

    html_files = list(Path(html_dir).glob('*.html'))
    global total_files
    total_files = len(html_files)
    print(f"\nFound {total_files} HTML files to process...")
    
    parser = ParserFactory.get_parser(platform)
    
    # Create a shared counter for tracking progress
    counter = Value('i', 0)
    
    # Process files in smaller batches to manage memory
    batch_size = 10
    all_metadata = []
    
    for i in range(0, len(html_files), batch_size):
        batch_files = html_files[i:i + batch_size]
        print(f"\nProcessing batch {i//batch_size + 1} of {(len(html_files) + batch_size - 1)//batch_size}")
        
        # Process batch in parallel
        with ProcessPoolExecutor(max_workers=4) as executor:
            # Convert to list of strings for serialization
            file_paths = [str(path) for path in batch_files]
            # Create partial function with parser, api_key, and counter
            process_func = partial(process_single_file, parser=parser, api_key=api_key, counter=counter)
            # Process files in parallel
            tasks = [asyncio.create_task(process_func(file_path)) for file_path in file_paths]
            batch_results = await asyncio.gather(*tasks)
            # Filter out None results from failed processing
            batch_results = [m for m in batch_results if m is not None]
            
            # Add batch results to main list
            all_metadata.extend(batch_results)
            
            # Force garbage collection after each batch
            import gc
            gc.collect()
    
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
    
    # Save CSV
    if csv_data:
        df = pd.DataFrame(csv_data)
        df.to_csv(output_file_csv, index=False, encoding='utf-8')
    
    print(f"\nProcessed {len(all_metadata)} articles")
    print(f"JSON data saved to {output_file_json}")
    print(f"CSV data saved to {output_file_csv}")
    
    return all_metadata

async def test_single_file(file_path: str, platform: str) -> None:
    """Test parsing of a single HTML file and print the results."""
    parser = ParserFactory.get_parser(platform)
    metadata = await parser.parse_html(file_path)
    
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
    
    print(f"\nNumber of LLM backup calls made: {parser.llm_call_counter}")

class ScienceDirectParser(BaseParser):
    def clean_working_paper_title(self, title: str) -> str:
        """Remove working paper indicators from title"""
        if not title:
            return ""
        
        # List of terms to remove from end of title
        terms_to_remove = [
            'working paper', 'unpublished', 'unpublished working paper',
            'discussion paper', 'research paper', 'manuscript',
            'work in progress', 'mimeo', 'dissertation'
        ]
        
        title = title.strip()
        title_lower = title.lower()
        
        # Remove any of these terms and following punctuation from the end
        for term in terms_to_remove:
            if title_lower.endswith(term):
                title = title[:-len(term)].strip()
            # Also try with a period
            if title_lower.endswith(term + '.'):
                title = title[:-len(term)-1].strip()
        
        # Clean up any remaining punctuation at the end
        title = re.sub(r'[.,;:\s]+$', '', title)
        
        return title.strip()

    async def parse_reference(self, ref_elem) -> Reference:
        """Parse a reference from its HTML element using specific class names"""
        ref = Reference(
            authors=[], year=None, title=None, journal=None,
            volume=None, page_first=None, page_last=None, doi=None,
            ref_type=ReferenceType.ARTICLE
        )
        
        try:
            # First check if it's a working paper
            contribution = ref_elem.find('div', class_='contribution')
            host_div = ref_elem.find('div', class_='host u-font-sans')
            other_ref = ref_elem.find('div', class_='other-ref')
            
            is_working_paper = False
            working_paper_text = ""
            
            # Check for working paper indicators in various elements and full text
            ref_text = ref_elem.get_text().lower()
            if any(term in ref_text for term in self.working_paper_terms):
                is_working_paper = True
                working_paper_text = ref_elem.get_text().strip()
            
            # Also check specific elements if not already found
            if not is_working_paper:
                if contribution:
                    title_div = contribution.find('div', class_='title text-m')
                    if title_div and any(term in title_div.get_text().lower() for term in self.working_paper_terms):
                        is_working_paper = True
                        working_paper_text = title_div.get_text()
                
                if host_div and any(term in host_div.get_text().lower() for term in self.working_paper_terms):
                    is_working_paper = True
                    working_paper_text = host_div.get_text().strip()
                
                if other_ref and any(term in other_ref.get_text().lower() for term in self.working_paper_terms):
                    is_working_paper = True
                    working_paper_text = other_ref.get_text().strip()
            
            if is_working_paper:
                ref.ref_type = ReferenceType.WORKING_PAPER
                
                # Extract working paper details
                if working_paper_text:
                    author_year_match = re.match(r'([^,]+(?:,\s*[^,]+)*),\s*(\d{4})', working_paper_text)
                    if author_year_match:
                        authors_text = author_year_match.group(1)
                        ref.authors = self.parse_authors(authors_text)
                        ref.year = author_year_match.group(2)
                        
                        title_match = re.search(r'\d{4}\.\s*(.*?)\s*(?:[Ww]orking paper|[Dd]issertation|Ph\.D\.|PhD)', working_paper_text)
                        if title_match:
                            ref.title = self.clean_working_paper_title(self.clean_text(title_match.group(1)))
                
                # Try to find institution - use more flexible patterns
                institution_match = None
                if 'working paper' in working_paper_text.lower():
                    # Try different patterns to find institution
                    patterns = [
                        r'[Ww]orking [Pp]aper(?:[.,]\s*|\s+)([^,.]+(?:[^,.]|,\s+(?:Series|No))[^,.]*)',
                        r'[Ww]orking [Pp]aper[.,]?\s*([^,.]+)',
                        r'[Ww]orking [Pp]aper.*?(?:at|,)\s*([^,.]+)',
                    ]
                    for pattern in patterns:
                        institution_match = re.search(pattern, working_paper_text)
                        if institution_match:
                            break
                elif any(term in working_paper_text.lower() for term in ['dissertation', 'ph.d.', 'phd']):
                    institution_match = re.search(r'(?:Dissertation|Ph\.D\.|PhD)[.,]?\s*([^,.]+)', working_paper_text)
                
                if institution_match:
                    ref.working_paper_institution = self.clean_text(institution_match.group(1))
            
            # If not a working paper, continue with normal parsing...
            else:
                if contribution:
                    # Extract authors
                    authors_div = contribution.find('div', class_='authors u-font-sans')
                    if authors_div:
                        authors_text = authors_div.get_text()
                        ref.authors = self.parse_authors(authors_text)
                    
                    # Extract title
                    title_div = contribution.find('div', class_='title text-m')
                    if title_div:
                        ref.title = self.clean_text(title_div.get_text())
                
                # Parse the host div for journal articles
                if host_div:
                    host_text = host_div.get_text().strip()
                    # Try to match the common format: "Journal Name, Volume (Issue) (Year), pp. Pages"
                    journal_match = re.match(r'([^,]+),\s*(\d+)\s*\((\d+)\)\s*\((\d{4})\),\s*pp\.\s*(\d+)-(\d+)', host_text)
                    
                    if journal_match:
                        ref.journal = self.clean_journal(journal_match.group(1))
                        ref.volume = journal_match.group(2)
                        ref.year = journal_match.group(4)
                        ref.page_first = journal_match.group(5)
                        ref.page_last = journal_match.group(6)
                    else:
                        # Try simpler pattern without issue number
                        journal_match = re.match(r'([^,]+),\s*(\d+)\s*\((\d{4})\),\s*pp\.\s*(\d+)-(\d+)', host_text)
                        if journal_match:
                            ref.journal = self.clean_journal(journal_match.group(1))
                            ref.volume = journal_match.group(2)
                            ref.year = journal_match.group(3)
                            ref.page_first = journal_match.group(4)
                            ref.page_last = journal_match.group(5)
                        else:
                            # If it doesn't match journal format and isn't a working paper, treat as book
                            ref.ref_type = ReferenceType.BOOK
                            ref.book_title = self.clean_text(host_text)
                            # Try to extract year if present
                            year_match = re.search(r'\((\d{4})\)', host_text)
                            if year_match:
                                ref.year = year_match.group(1)
            
            # Extract DOI if present
            doi_elem = ref_elem.find('a', href=re.compile(r'doi.org'))
            if doi_elem and 'href' in doi_elem.attrs:
                doi_href = doi_elem['href']
                if doi_href.startswith('https://doi.org/'):
                    ref.doi = doi_href[len('https://doi.org/'):]
            
            # Single LLM backup check at the end for all reference types
            if ref.ref_type == ReferenceType.BOOK:
                if not ref.book_title or not ref.year:
                    backup_result = await self.llm_backup(ref_elem.get_text(), ref.ref_type)
                    ref.book_title = backup_result.get('book_title') or ref.book_title
                    ref.chapter_title = backup_result.get('chapter_title') or ref.chapter_title
                    ref.year = backup_result.get('year') or ref.year
            elif ref.ref_type == ReferenceType.WORKING_PAPER:
                if not ref.title or not ref.working_paper_institution or not ref.year:
                    backup_result = await self.llm_backup(ref_elem.get_text(), ref.ref_type)
                    ref.title = backup_result.get('title') or ref.title
                    ref.working_paper_institution = backup_result.get('institution') or ref.working_paper_institution
                    ref.year = backup_result.get('year') or ref.year
            elif ref.ref_type == ReferenceType.ARTICLE:
                if not ref.title or not ref.journal or not ref.year:
                    backup_result = await self.llm_backup(ref_elem.get_text(), ref.ref_type)
                    ref.title = backup_result.get('title') or ref.title
                    ref.journal = backup_result.get('journal') or ref.journal
                    ref.year = backup_result.get('year') or ref.year
                    ref.volume = backup_result.get('volume') or ref.volume
                    ref.page_first = backup_result.get('page_first') or ref.page_first
                    ref.page_last = backup_result.get('page_last') or ref.page_last

            return ref
            
        except Exception as e:
            print(f"Error parsing reference: {str(e)}")
            return ref

    async def parse_html(self, file_path: str) -> ArticleMetadata:
        """Parse a ScienceDirect HTML file to extract paper metadata"""
        soup = None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f, 'html.parser')
            
            # Extract title
            title = None
            title_elem = soup.find('span', class_='title-text')
            if title_elem:
                title = self.clean_text(title_elem.get_text())
            
            # Extract authors
            authors = []
            author_elems = soup.find_all('span', class_='react-xocs-alternative-link')
            for author_elem in author_elems:
                given_name = author_elem.find('span', class_='given-name')
                surname = author_elem.find('span', class_='surname')
                
                if given_name and surname:
                    full_name = f"{self.clean_text(given_name.get_text())} {self.clean_text(surname.get_text())}"
                    if full_name.strip():
                        authors.append(full_name)
            
            # Extract DOI
            doi = None
            doi_elem = soup.find('a', class_='anchor doi anchor-primary')
            if doi_elem and 'href' in doi_elem.attrs:
                doi_href = doi_elem['href']
                if doi_href.startswith('https://doi.org/'):
                    doi = doi_href[len('https://doi.org/'):]
            
            # Extract volume and issue
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
            
            # Extract publication date and page numbers
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
            
            # Extract references
            references = []
            ref_list = soup.find('ol', class_='references')
            if ref_list:
                ref_items = ref_list.find_all('li')
                for ref_item in ref_list.find_all('li'):
                    ref_span = ref_item.find('span', class_='reference')
                    if ref_span:
                        ref = await self.parse_reference(ref_span)
                        if ref.authors:  # Only add if we found at least one author
                            references.append(ref)
            
            # Extract citation count
            citations = None
            metrics_elem = soup.find('li', class_='text-xs metrics')
            if metrics_elem:
                citation_text = metrics_elem.find_all('span')[-1].get_text()  # Get the last span
                try:
                    citations = int(citation_text)
                except (ValueError, TypeError):
                    citations = None
            
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
                title=None, authors=[], published_date=None,
                volume=None, issue=None, page_first=None,
                page_last=None, citations=None, doi=None,
                references=[]
            )
        finally:
            # Clean up BeautifulSoup object
            if soup:
                soup.decompose()

    def parse_authors(self, authors_text: str) -> List[str]:
        """Parse and format a list of authors"""
        if not authors_text:
            return []
        
        authors = []
        current_author = ""
        
        parts = authors_text.split(',')
        for i, part in enumerate(parts):
            part = part.strip()
            
            if re.match(r'^[A-Z]\.?\s*$', part):
                current_author += f", {part}"
            else:
                if current_author:
                    authors.append(self.format_author_name(current_author))
                current_author = part
        
        if current_author:
            authors.append(self.format_author_name(current_author))
        
        return [a for a in authors if a]

class WileyParser(BaseParser):
    def extract_year(self, text: str) -> str:
        """Extract a valid year from text"""
        if not text:
            return ""
        match = re.search(r'(19|20)\d{2}', text)
        if match:
            return match.group(0)
        return ""

    def clean_pages(self, text: str) -> str:
        """Clean page numbers by removing any mixed content"""
        if not text:
            return ""
        match = re.search(r'\d+', text)
        if match:
            return match.group(0)
        return ""

    def clean_volume(self, text: str) -> str:
        """Clean volume number by removing any mixed content"""
        if not text:
            return ""
        match = re.search(r'\d+', text)
        if match:
            return match.group(0)
        return ""

    async def parse_reference(self, ref_elem) -> Reference:
        """Parse a reference from its HTML element using specific class names"""
        ref = Reference(
            authors=[], year=None, title=None, journal=None,
            volume=None, page_first=None, page_last=None, doi=None,
            ref_type=ReferenceType.ARTICLE
        )
        
        try:
            # Extract authors from class='author'
            author_elems = ref_elem.find_all('span', class_='author')
            authors = []
            for i, author in enumerate(author_elems):
                author_text = self.clean_text(author.get_text())
                if author_text and len(author_text) > 2:  # Ignore very short author names
                    author_text = author_text.strip(',')
                    if author_text:
                        # For first author, rearrange "Last, First" to "First Last"
                        if i == 0 and ',' in author_text:
                            last_name, first_name = author_text.split(',', 1)
                            author_text = f"{first_name.strip()} {last_name.strip()}"
                        authors.append(author_text)
            ref.authors = authors
            
            # Extract year from class='pubYear'
            year_elem = ref_elem.find('span', class_='pubYear')
            if year_elem:
                ref.year = self.extract_year(year_elem.get_text())
            
            # Check for book indicators first
            book_title_elem = ref_elem.find('span', class_='bookTitle')
            chapter_title_elem = ref_elem.find('span', class_='chapterTitle')
            
            if book_title_elem or chapter_title_elem:
                ref.ref_type = ReferenceType.BOOK
                if book_title_elem:
                    ref.book_title = self.clean_text(book_title_elem.get_text())
                if chapter_title_elem:
                    ref.chapter_title = self.clean_text(chapter_title_elem.get_text())
            
            # If not a book, check if it's a working paper
            elif any(term in ref_elem.get_text().lower() for term in self.working_paper_terms):
                ref.ref_type = ReferenceType.WORKING_PAPER
                # For working papers, title might be in bookTitle class
                title_elem = book_title_elem or ref_elem.find('span', class_='articleTitle')
                if title_elem:
                    ref.title = self.clean_text(title_elem.get_text())
                # Extract institution if available
                full_text = ref_elem.get_text().lower()
                after_working = full_text[full_text.find('working paper')+len('working paper'):]
                institution_match = re.search(r',\s*([^,\.]+)', after_working)
                if institution_match:
                    ref.working_paper_institution = self.clean_text(institution_match.group(1))
            
            # Otherwise, treat as article
            else:
                ref.ref_type = ReferenceType.ARTICLE
                # Extract title from articleTitle class
                title_elem = ref_elem.find('span', class_='articleTitle')
                if title_elem:
                    ref.title = self.clean_text(title_elem.get_text())
                
                # Extract journal name from italicized text or journalTitle class
                journal_elem = ref_elem.find('i') or ref_elem.find('span', class_='journalTitle')
                if journal_elem:
                    ref.journal = self.clean_journal(journal_elem.get_text())
                
                # Extract volume and pages
                volume_elem = ref_elem.find('span', class_='vol')
                if volume_elem:
                    ref.volume = self.clean_volume(volume_elem.get_text())
                
                # Extract pages using pageFirst and pageLast spans
                page_first_elem = ref_elem.find('span', class_='pageFirst')
                if page_first_elem:
                    ref.page_first = self.clean_pages(page_first_elem.get_text())
                
                page_last_elem = ref_elem.find('span', class_='pageLast')
                if page_last_elem:
                    ref.page_last = self.clean_pages(page_last_elem.get_text())
                
                # Fallback to pages span if pageFirst/pageLast not found
                if not ref.page_first and not ref.page_last:
                    pages_elem = ref_elem.find('span', class_='pages')
                    if pages_elem:
                        pages_text = pages_elem.get_text()
                        pages_match = re.search(r'(\d+)[-–](\d+)', pages_text)
                        if pages_match:
                            ref.page_first = pages_match.group(1)
                            ref.page_last = pages_match.group(2)
            
            # Extract DOI if present
            doi_span = ref_elem.find('span', class_='hidden data-doi')
            if doi_span:
                doi_text = doi_span.get_text().strip()
                if doi_text:
                    ref.doi = doi_text
            
            # Use LLM backup if essential fields are missing (at the end)
            if ref.ref_type == ReferenceType.BOOK:
                if not ref.book_title or not ref.year:
                    backup_result = await self.llm_backup(ref_elem.get_text(), ref.ref_type)
                    ref.book_title = backup_result.get('book_title') or ref.book_title
                    ref.chapter_title = backup_result.get('chapter_title') or ref.chapter_title
                    ref.year = backup_result.get('year') or ref.year
            elif ref.ref_type == ReferenceType.WORKING_PAPER:
                if not ref.title or not ref.working_paper_institution or not ref.year:
                    backup_result = await self.llm_backup(ref_elem.get_text(), ref.ref_type)
                    ref.title = backup_result.get('title') or ref.title
                    ref.working_paper_institution = backup_result.get('institution') or ref.working_paper_institution
                    ref.year = backup_result.get('year') or ref.year
            elif ref.ref_type == ReferenceType.ARTICLE:
                if not ref.title or not ref.journal or not ref.year:
                    backup_result = await self.llm_backup(ref_elem.get_text(), ref.ref_type)
                    ref.title = backup_result.get('title') or ref.title
                    ref.journal = backup_result.get('journal') or ref.journal
                    ref.year = backup_result.get('year') or ref.year
                    ref.volume = backup_result.get('volume') or ref.volume
                    ref.page_first = backup_result.get('page_first') or ref.page_first
                    ref.page_last = backup_result.get('page_last') or ref.page_last
            
            return ref
            
        except Exception as e:
            print(f"Error parsing reference: {str(e)}")
            return ref

    async def parse_html(self, file_path: str) -> ArticleMetadata:
        """Parse a Wiley HTML file to extract paper metadata"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f, 'html.parser')
            
            # Extract title
            title = None
            title_elem = soup.find('h1', class_='citation__title')
            if title_elem:
                title = title_elem.get_text().strip()
            
            # Extract authors
            authors = []
            seen_authors = set()
            
            author_elems = soup.find_all('a', class_='author-name')
            if not author_elems:
                author_elems = soup.find_all('div', class_='author-info')
            
            for author_elem in author_elems:
                name = None
                if author_elem.find('span'):
                    name = author_elem.find('span').text
                elif author_elem.get('title'):
                    name = author_elem['title']
                else:
                    name = author_elem.text
                    
                if name:
                    name = self.clean_text(name)
                    if name not in seen_authors:
                        authors.append(name)
                        seen_authors.add(name)
            
            # Extract volume and issue
            volume = None
            issue = None
            volume_issue_elem = soup.find('a', class_='volume-issue')
            if volume_issue_elem:
                volume_text = volume_issue_elem.text
                match = re.match(r'Volume\s+(\d+),\s*Issue\s+(\d+)', volume_text)
                if match:
                    volume = match.group(1)
                    issue = match.group(2)
            
            # Extract page numbers
            page_first = None
            page_last = None
            pages_elem = soup.find('span', class_='citation__page-range')
            if pages_elem:
                pages_text = pages_elem.text
                match = re.search(r'p\.\s*(\d+)-(\d+)', pages_text)
                if match:
                    page_first = match.group(1)
                    page_last = match.group(2)
            
            # Extract publication date
            published_date = None
            date_elem = soup.find('span', class_='epub-date')
            if date_elem:
                try:
                    date_text = date_elem.get_text().strip()
                    if 'First published:' in date_text:
                        date_text = date_text.split('First published:')[1].strip()
                    published_date = datetime.strptime(date_text, '%d %B %Y').date()
                except (ValueError, AttributeError):
                    published_date = None
            
            # Extract citations
            citations = None
            citations_elem = soup.find('a', href='#citedby-section')
            if citations_elem:
                citations_text = citations_elem.text
                citations_match = re.search(r'(\d+)', citations_text)
                if citations_match:
                    citations = int(citations_match.group(1))
            
            # Extract DOI
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
                    for elem in ref_item.find_all(['a', 'button']):
                        if not (elem.get('href') and 'doi.org' in elem['href']):
                            elem.decompose()
                    
                    ref = await self.parse_reference(ref_item)
                    if ref.authors:
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
                title=None, authors=[], published_date=None,
                volume=None, issue=None, page_first=None,
                page_last=None, citations=None, doi=None,
                references=[]
            )

class OUPParser(BaseParser):
    def extract_year(self, text: str) -> str:
        """Extract a valid year from text"""
        if not text:
            return ""
        match = re.search(r'(19|20)\d{2}', text)
        if match:
            return match.group(0)
        return ""

    def clean_pages(self, text: str) -> str:
        """Clean page numbers by removing any mixed content"""
        if not text:
            return ""
        match = re.search(r'\d+', text)
        if match:
            return match.group(0)
        return ""

    def clean_volume(self, text: str) -> str:
        """Clean volume number by removing any mixed content"""
        if not text:
            return ""
        match = re.search(r'\d+', text)
        if match:
            return match.group(0)
        return ""

    async def parse_reference(self, ref_elem) -> Reference:
        """Parse a reference from its HTML element using specific class names"""
        ref = Reference(
            authors=[], year=None, title=None, journal=None,
            volume=None, page_first=None, page_last=None, doi=None,
            ref_type=ReferenceType.ARTICLE
        )
        
        try:
            # Extract authors from name divs
            authors = []
            name_divs = ref_elem.find_all('div', class_='name')
            for name_div in name_divs:
                surname = name_div.find('div', class_='surname')
                given_names = name_div.find('div', class_='given-names')
                
                if surname and given_names:
                    surname_text = self.clean_text(surname.get_text())
                    given_names_text = self.clean_text(given_names.get_text())
                    
                    if surname_text and given_names_text:
                        full_name = f"{given_names_text} {surname_text}"
                        if len(full_name.strip()) > 2:
                            authors.append(full_name)
            
            ref.authors = authors
            
            # Extract year
            year_elem = ref_elem.find('div', class_='year')
            if year_elem:
                ref.year = year_elem.get_text().strip()
            
            # Check if it's a working paper
            comment_elem = ref_elem.find('div', class_='comment')
            if comment_elem and any(term in comment_elem.get_text().lower() for term in self.working_paper_terms):
                ref.ref_type = ReferenceType.WORKING_PAPER
                # Get title from source for working papers
                source_elem = ref_elem.find('div', class_='source')
                if source_elem:
                    ref.title = self.clean_text(source_elem.get_text())
                # Get institution
                publisher_elem = ref_elem.find('div', class_='publisher-name')
                if publisher_elem:
                    ref.working_paper_institution = self.clean_text(publisher_elem.get_text())
                
                # Use LLM backup if essential fields are missing
                if not ref.title or not ref.working_paper_institution or not ref.year:
                    backup_result = await self.llm_backup(ref_elem.get_text(), ReferenceType.WORKING_PAPER)
                    ref.title = backup_result.get('title') or ref.title
                    ref.working_paper_institution = backup_result.get('institution') or ref.working_paper_institution
                    ref.year = backup_result.get('year') or ref.year
            
            else:
                # Check for article elements
                article_title = ref_elem.find('div', class_='article-title')
                source = ref_elem.find('div', class_='source')
                volume = ref_elem.find('div', class_='volume')
                fpage = ref_elem.find('div', class_='fpage')
                lpage = ref_elem.find('div', class_='lpage')
                
                if article_title and source:
                    ref.ref_type = ReferenceType.ARTICLE
                    ref.title = self.clean_text(article_title.get_text())
                    ref.journal = self.clean_text(source.get_text())
                    if volume:
                        ref.volume = volume.get_text().strip()
                    if fpage:
                        ref.page_first = fpage.get_text().strip()
                    if lpage:
                        ref.page_last = lpage.get_text().strip()
                    
                    # Use LLM backup if essential fields are missing
                    if not ref.title or not ref.journal or not ref.year:
                        backup_result = await self.llm_backup(ref_elem.get_text(), ref.ref_type)
                        ref.title = backup_result.get('title') or ref.title
                        ref.journal = backup_result.get('journal') or ref.journal
                        ref.year = backup_result.get('year') or ref.year
                
                else:
                    # If no article title but has source, treat as book
                    ref.ref_type = ReferenceType.BOOK
                    if source:
                        ref.book_title = self.clean_text(source.get_text())
                    
                    # Use LLM backup if essential fields are missing
                    if not ref.book_title or not ref.year:
                        backup_result = await self.llm_backup(ref_elem.get_text(), ReferenceType.BOOK)
                        ref.book_title = backup_result.get('book_title') or ref.book_title
                        ref.chapter_title = backup_result.get('chapter_title')
                        ref.year = backup_result.get('year') or ref.year
            
            # Extract DOI if present
            doi = None
            # First check direct doi.org links
            doi_link = ref_elem.find('a', href=re.compile(r'doi.org'))
            if doi_link and 'href' in doi_link.attrs:
                doi_href = doi_link['href']
                if doi_href.startswith('https://doi.org/'):
                    doi = doi_href[len('https://doi.org/'):]
            
            # If no DOI found, check crossref
            if not doi:
                crossref_elem = ref_elem.find('div', class_='crossref-doi')
                if crossref_elem:
                    crossref_link = crossref_elem.find('a')
                    if crossref_link and 'href' in crossref_link.attrs:
                        doi_href = crossref_link['href']
                        if doi_href.startswith('http://dx.doi.org/'):
                            doi = doi_href[len('http://dx.doi.org/'):]
            
            ref.doi = doi
            
            # Use LLM backup if essential fields are missing (at the end)
            if ref.ref_type == ReferenceType.BOOK:
                if not ref.book_title or not ref.year:
                    backup_result = await self.llm_backup(ref_elem.get_text(), ref.ref_type)
                    ref.book_title = backup_result.get('book_title') or ref.book_title
                    ref.chapter_title = backup_result.get('chapter_title') or ref.chapter_title
                    ref.year = backup_result.get('year') or ref.year
            elif ref.ref_type == ReferenceType.WORKING_PAPER:
                if not ref.title or not ref.working_paper_institution or not ref.year:
                    backup_result = await self.llm_backup(ref_elem.get_text(), ref.ref_type)
                    ref.title = backup_result.get('title') or ref.title
                    ref.working_paper_institution = backup_result.get('institution') or ref.working_paper_institution
                    ref.year = backup_result.get('year') or ref.year
            elif ref.ref_type == ReferenceType.ARTICLE:
                if not ref.title or not ref.journal or not ref.year:
                    backup_result = await self.llm_backup(ref_elem.get_text(), ref.ref_type)
                    ref.title = backup_result.get('title') or ref.title
                    ref.journal = backup_result.get('journal') or ref.journal
                    ref.year = backup_result.get('year') or ref.year
                    ref.volume = backup_result.get('volume') or ref.volume
                    ref.page_first = backup_result.get('page_first') or ref.page_first
                    ref.page_last = backup_result.get('page_last') or ref.page_last
            
            return ref
            
        except Exception as e:
            print(f"Error parsing reference: {str(e)}")
            return ref

    async def parse_html(self, file_path: str) -> ArticleMetadata:
        """Parse an OUP HTML file to extract paper metadata"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f, 'html.parser')
            
            # Extract title
            title = None
            title_elem = soup.find('h1', class_='wi-article-title article-title-main accessible-content-title at-articleTitle')
            if title_elem:
                title = title_elem.get_text().strip()
            
            # Extract authors
            authors = []
            author_wraps = soup.find_all('div', class_='name-role-wrap')
            for wrap in author_wraps:
                name_elem = wrap.find('div', class_='info-card-name')
                if name_elem:
                    # Get text before any span elements (to avoid footnotes)
                    name = name_elem.find(text=True, recursive=False)
                    if name:
                        name = name.strip()
                        if name:
                            authors.append(name)
            
            # Extract citation information (journal, volume, issue, date, pages, doi)
            citation_elem = soup.find('div', class_='ww-citation-primary')
            if citation_elem:
                citation_text = citation_elem.get_text()
                
                # Extract volume and issue
                volume_match = re.search(r'Volume\s+(\d+)', citation_text)
                issue_match = re.search(r'Issue\s+(\d+)', citation_text)
                if volume_match:
                    volume = volume_match.group(1)
                if issue_match:
                    issue = issue_match.group(1)
                
                # Extract pages
                pages_match = re.search(r'Pages\s+(\d+)[-–](\d+)', citation_text)
                if pages_match:
                    page_first = pages_match.group(1)
                    page_last = pages_match.group(2)
                
                # Extract date
                date_match = re.search(r'([A-Za-z]+)\s+(\d{4})', citation_text)
                if date_match:
                    try:
                        date_text = f"1 {date_match.group(1)} {date_match.group(2)}"
                        published_date = datetime.strptime(date_text, '%d %B %Y').date()
                    except (ValueError, AttributeError) as e:
                        published_date = None
                
                # Extract DOI
                doi_link = citation_elem.find('a', href=re.compile(r'doi.org'))
                if doi_link and 'href' in doi_link.attrs:
                    doi_href = doi_link['href']
                    if doi_href.startswith('https://doi.org/'):
                        doi = doi_href[len('https://doi.org/'):]
            
            # Extract references
            references = []
            ref_list = soup.find('div', class_='ref-list')
            if ref_list:
                ref_items = ref_list.find_all('div', class_='ref-content')
                for ref_item in ref_items:
                    ref = await self.parse_reference(ref_item)
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
                citations=None,  # OUP doesn't provide citation count
                doi=doi,
                references=references
            )
            
        except Exception as e:
            print(f"Error parsing HTML file: {str(e)}")
            return ArticleMetadata(
                title=None, authors=[], published_date=None,
                volume=None, issue=None, page_first=None,
                page_last=None, citations=None, doi=None,
                references=[]
            )

if __name__ == "__main__":
    # Process all files in the JF folder
    html_dir = "downloaded_html/JF"
    output_json = "JF_articles.json"
    output_csv = "JF_articles.csv"
    print("Processing all Wiley JF articles...")
    asyncio.run(process_html_files(html_dir, output_json, output_csv, "wiley"))

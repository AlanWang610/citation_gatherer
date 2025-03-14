from habanero import Crossref
import time
from datetime import datetime
import dotenv
import openai
import os
import json
import sys
import pandas as pd
import requests_cache
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
import requests

dotenv.load_dotenv()
openai_api_key = os.getenv('OPENAI_API_KEY')

# Initialize Crossref API client with timeout
cr = Crossref(mailto="wangac@mit.edu", timeout=30)  # 30 second timeout

# Add type mapping dictionary
reference_type_map = {
    'journal-article': 'article'
}

working_paper_terms = {
    'working paper', 'dissertation', 'research paper',
    'discussion paper', 'nber paper',
    'unpublished paper', 'unpublished', 'mimeo',
    'manuscript', 'work in progress'
}

# Initialize cache for API calls
requests_cache.install_cache('crossref_cache', backend='sqlite', expire_after=604800, 
                           allowable_methods=('GET', 'POST'), 
                           allowable_codes=(200, 404, 408, 500),
                           thread_safe=True)  # Add thread_safe=True

class RateLimiter:
    def __init__(self, calls_per_second):
        self.delay = 1.0 / calls_per_second
        self.last_call = time.time()
        self.lock = threading.Lock()
    
    def wait(self):
        with self.lock:
            current_time = time.time()
            time_to_wait = self.last_call + self.delay - current_time
            self.last_call = current_time + max(0, time_to_wait)
        
        if time_to_wait > 0:
            time.sleep(time_to_wait)

# Adjust the rate limiter
rate_limiter = RateLimiter(calls_per_second=15)

def load_processed_dois():
    """Load already processed DOIs from tracking file"""
    processed_file = Path('processed_dois.txt')
    if processed_file.exists():
        with open(processed_file, 'r') as f:
            return set(line.strip() for line in f)
    return set()

def save_processed_doi(doi):
    """Save a DOI to the tracking file"""
    with threading.Lock():  # Add lock
        with open('processed_dois.txt', 'a', buffering=1) as f:
            f.write(f"{doi}\n")
            f.flush()
            os.fsync(f.fileno())

def search_for_doi(ref_data):
    """Try to find DOI using available reference fields"""
    try:
        # Build core search query with just essential fields
        query_parts = []
        
        # Add authors if available - handle both string and list formats
        if 'authors' in ref_data:
            if isinstance(ref_data['authors'], list):
                author_names = []
                for author in ref_data['authors']:
                    if len(author) >= 2:
                        author_names.append(f"{author[0]} {author[1]}")
                if author_names:
                    query_parts.append(f"author:\"{' '.join(author_names)}\"")
            else:
                query_parts.append(f"author:{ref_data['authors']}")
        elif 'author' in ref_data:  # Add this case for single author string
            query_parts.append(f"author:\"{ref_data['author']}\"")
            
        # Add year if available
        if 'year' in ref_data:
            query_parts.append(f"year:{ref_data['year']}")
            
        # Add title
        if 'title' in ref_data and ref_data['title']:
            query_parts.append(f"title:\"{ref_data['title']}\"")
            
        if not query_parts:
            return None
            
        # Define fields we need for validation
        select_fields = [
            'DOI',
            'title',
            'container-title',
            'volume',
            'page',
            'published-print',
            'author'
        ]
            
        # Perform the search with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                rate_limiter.wait()
                query = " ".join(query_parts)
                results = cr.works(
                    query=query,
                    limit=1,
                    select=','.join(select_fields)
                )
                break
            except requests.exceptions.Timeout:
                if attempt == max_retries - 1:  # Last attempt
                    return None
                time.sleep(2 * (attempt + 1))  # Exponential backoff
            except Exception as e:
                if attempt == max_retries - 1:
                    return None
                time.sleep(2 * (attempt + 1))
        
        items = results['message']['items']
        if not items:
            return None
            
        # Validate just the first result
        item = items[0]
        matches = 0
        total_checks = 0
        match_details = []
        
        # Check authors if available
        if 'authors' in ref_data and ref_data['authors']:
            if isinstance(ref_data['authors'], list):
                ref_authors = []
                for author in ref_data['authors']:
                    if len(author) >= 2:
                        first = author[0].lower().strip()
                        last = author[1].lower().strip()
                        first_initial = first[0] if first else ''
                        ref_authors.append((first_initial, first, last))
            else:
                ref_authors = []
        elif 'author' in ref_data and ref_data['author']:
            author_str = ref_data['author'].lower().strip()
            ref_authors = [(author_str[0], author_str, author_str)]
        else:
            ref_authors = []
        
        result_authors = []
        if 'author' in item:
            for author in item['author']:
                if 'given' in author and 'family' in author:
                    given = author.get('given', '').lower().strip()
                    family = author.get('family', '').lower().strip()
                    first_initial = given[0] if given else ''
                    result_authors.append((first_initial, given, family))
        
        if ref_authors and result_authors:
            total_checks += 1
            author_match = any(
                (ref_auth[0] == res_auth[0] and ref_auth[2] in res_auth[2] or res_auth[2] in ref_auth[2])
                or (ref_auth[1] in res_auth[1] or res_auth[1] in ref_auth[1])
                or any(name in res_auth[2] or res_auth[2] in name
                      for name in [ref_auth[1], ref_auth[2]])
                for ref_auth in ref_authors
                for res_auth in result_authors
            )
            matches += 1 if author_match else 0
            match_details.append(f"Author: {ref_authors} vs {result_authors} -> {'✓' if author_match else '✗'}")
        
        # Check year - only if both have valid years
        if 'year' in ref_data and ref_data['year'] and 'published-print' in item:
            try:
                pub_year = item['published-print']['date-parts'][0][0]
                if pub_year:  # Only check if we have a valid year
                    total_checks += 1
                    year_match = str(pub_year) == str(ref_data['year'])
                    matches += 1 if year_match else 0
                    match_details.append(f"Year: {ref_data['year']} vs {pub_year} -> {'✓' if year_match else '✗'}")
            except (IndexError, TypeError):
                pass  # Skip year check if data is invalid
        
        # Check title - only if both have valid titles
        if 'title' in ref_data and ref_data['title']:
            ref_title = ref_data['title'].lower()
            
            # Get potential titles from both title and container-title fields
            result_titles = []
            if 'title' in item and item['title']:
                result_titles.append(item['title'][0].lower())
            if 'container-title' in item and item['container-title']:
                result_titles.append(item['container-title'][0].lower())
            
            if result_titles:  # Only check if we have titles to compare
                total_checks += 1
                
                # Split titles into words and remove common stop words
                stop_words = {'a', 'an', 'and', 'the', 'in', 'on', 'at', 'to', 'for', 'of'}
                ref_words = {word for word in ref_title.split() if word not in stop_words}
                
                # Check word overlap with each result title
                title_match = any(
                    len(ref_words & {word for word in res_title.split() if word not in stop_words}) >= 3  # Match if 3+ words overlap
                    or ref_title in res_title 
                    or res_title in ref_title
                    for res_title in result_titles
                )
                
                matches += 1 if title_match else 0
                match_details.append(f"Title: '{ref_title}' vs {result_titles} -> {'✓' if title_match else '✗'}")
        
        # Check volume - only if both have valid volumes
        if ('volume' in ref_data and ref_data['volume'] and 
            'volume' in item and item['volume']):
            total_checks += 1
            volume_match = str(item['volume']) == str(ref_data['volume'])
            matches += 1 if volume_match else 0
            match_details.append(f"Volume: {ref_data['volume']} vs {item['volume']} -> {'✓' if volume_match else '✗'}")
        
        # Check first page - only if both have valid pages
        if ('first-page' in ref_data and ref_data['first-page'] and 
            'page' in item and item['page']):
            total_checks += 1
            page_match = str(item['page']).startswith(str(ref_data['first-page']))
            matches += 1 if page_match else 0
            match_details.append(f"First page: {ref_data['first-page']} vs {item['page']} -> {'✓' if page_match else '✗'}")
        
        # Check if we have at least one author or title match
        author_matched = any(detail.startswith("Author") and detail.endswith("✓") for detail in match_details)
        title_matched = any(detail.startswith("Title") and detail.endswith("✓") for detail in match_details)
        
        # Require both minimum percentage and minimum number of matching fields, plus at least one critical field
        if (total_checks > 0 and matches/total_checks >= 0.6 and matches >= 2 
            and (author_matched or title_matched)):
            return item.get('DOI')
            
        return None
            
    except Exception as e:
        return None

def fetch_complete_article_data(doi):
    rate_limiter.wait()  # Wait before making API call
    # Add follow parameter to handle redirects
    result = cr.works(ids=doi, follow=True)
    message = result['message']
    
    # Parse authors with error handling and affiliations
    authors = []
    if 'author' in message:
        for author in message.get('author', []):
            given = author.get('given', '')
            family = author.get('family', '')
            affiliation = None
            # Try to get the first affiliation if available
            if 'affiliation' in author and author['affiliation']:
                affiliation = author['affiliation'][0].get('name') if author['affiliation'][0] else None
            authors.append([given, family, affiliation])
    
    # Get abstract safely
    abstract = None
    if 'abstract' in message:
        abstract = message['abstract']
    
    # Get publication date, trying different date fields
    published_date = None
    if 'published-print' in message and 'date-parts' in message['published-print']:
        date_parts = message['published-print']['date-parts'][0]
        if len(date_parts) >= 2:
            published_date = f"{date_parts[0]}-{date_parts[1]:02d}-01"
    if not published_date and 'published-online' in message and 'date-parts' in message['published-online']:
        date_parts = message['published-online']['date-parts'][0]
        if len(date_parts) >= 2:
            published_date = f"{date_parts[0]}-{date_parts[1]:02d}-01"
    
    # Process references with error handling
    references = message.get('reference', [])
    total_ref_count = message.get('reference-count', 0)
    parsed_references = []
    skipped_references = 0
    
    for i, ref in enumerate(references):
        time.sleep(0.02)
        if 'DOI' in ref:
            parsed_ref = fetch_reference_article_data_by_doi(ref['DOI'])
            parsed_references.append(parsed_ref)
        else:
            # First try using unstructured field if available
            if 'unstructured' in ref:
                # Try LLM parsing first
                llm_parsed = fetch_llm_backup(ref['unstructured'], openai_api_key)
                # Try to find DOI using LLM parsed data
                found_doi_from_llm = search_for_doi(llm_parsed)
                
                if found_doi_from_llm:
                    parsed_ref = fetch_reference_article_data_by_doi(found_doi_from_llm)
                    # If this is a working paper and authors have no affiliations, use working paper institution
                    if (llm_parsed.get('reference_type') == 'working_paper' and 
                        llm_parsed.get('working_paper_institution')):
                        for author in parsed_ref['authors']:
                            if not author[2]:  # if no affiliation
                                author[2] = llm_parsed['working_paper_institution']
                    parsed_references.append(parsed_ref)
                else:
                    # If no DOI found, use the LLM parsed data directly
                    # For working papers, set institution as affiliation for all authors
                    if (llm_parsed.get('reference_type') == 'working_paper' and 
                        llm_parsed.get('working_paper_institution') and 
                        llm_parsed.get('authors')):
                        llm_parsed['authors'] = [
                            [author[0], author[1], llm_parsed['working_paper_institution']]
                            for author in llm_parsed['authors']
                        ]
                    parsed_references.append(llm_parsed)
            else:
                # If no unstructured field, try with available structured fields
                ref_data = {}
                for k, v in ref.items():
                    if k not in ['key', 'doi-asserted-by']:
                        # Normalize field names
                        if k in ['article-title', 'volume-title', 'book-title']:
                            ref_data['title'] = v
                        elif k == 'journal-title':
                            ref_data['journal'] = v
                        else:
                            ref_data[k] = v
                
                found_doi = search_for_doi(ref_data)
                
                if found_doi:
                    parsed_ref = fetch_reference_article_data_by_doi(found_doi)
                    # If this is a working paper and authors have no affiliations, use working paper institution
                    if (ref_data.get('reference_type') == 'working_paper' and 
                        ref_data.get('working_paper_institution')):
                        for author in parsed_ref['authors']:
                            if not author[2]:  # if no affiliation
                                author[2] = ref_data['working_paper_institution']
                    parsed_references.append(parsed_ref)
                elif 'title' in ref_data or 'journal' in ref_data:
                    ref_data['reference_type'] = 'article'
                    # For working papers, set institution as affiliation for all authors
                    if (ref_data.get('reference_type') == 'working_paper' and 
                        ref_data.get('working_paper_institution') and 
                        ref_data.get('authors')):
                        ref_data['authors'] = [
                            [author[0], author[1], ref_data['working_paper_institution']]
                            for author in ref_data['authors']
                        ]
                    parsed_references.append(ref_data)
                else:
                    skipped_references += 1
                    print(f"Warning: Reference {i+1} could not be parsed - no DOI found and insufficient fields")
    
    if len(references) != total_ref_count:
        print(f"Warning: Reference count mismatch for DOI {doi}")
        print(f"Expected {total_ref_count} references but found {len(references)}")
    
    # Get journal name safely
    journal = None
    if message.get('container-title') and len(message['container-title']) > 0:
        journal = message['container-title'][0]
    
    return {
        'doi': message.get('DOI'),
        'type': message.get('type'),
        'published_date': published_date,
        'title': message.get('title', [None])[0],
        'journal': journal,  # Use safer journal extraction
        'abstract': abstract,  # Add abstract to the returned data
        'volume': message.get('volume'),
        'issue': message.get('journal-issue', {}).get('issue'),
        'authors': authors,  # Now contains [given, family, affiliation]
        'references': parsed_references,
        'reference_stats': {
            'total_references': total_ref_count,
            'parsed_references': len(parsed_references),
            'skipped_references': skipped_references
        }
    }

def fetch_reference_article_data_by_doi(doi):
    try:
        rate_limiter.wait()
        result = cr.works(ids=doi, follow=True)
        
        # If we get a redirect response, try to get the new DOI from the Location header
        if isinstance(result, dict) and result.get('status') == 'ok':
            message = result['message']
        else:
            # Get the redirect URL from the Crossref client's last response
            redirect_url = cr._session.last_response.headers.get('Location')
            if redirect_url:
                # Extract new DOI from redirect URL if possible
                new_doi = redirect_url.split('works/')[-1] if 'works/' in redirect_url else None
                if new_doi:
                    rate_limiter.wait()  # Wait before making new API call
                    result = cr.works(ids=new_doi, follow=True)
                    message = result['message']
                else:
                    raise Exception(f"Could not extract DOI from redirect URL: {redirect_url}")
            else:
                raise Exception("No redirect URL found in response headers")
        
        # Parse authors with affiliations
        authors = []
        if 'author' in message:
            for author in message['author']:
                given = author.get('given', '')
                family = author.get('family', '')
                affiliation = None
                # Try to get the first affiliation if available
                if 'affiliation' in author and author['affiliation']:
                    affiliation = author['affiliation'][0].get('name') if author['affiliation'][0] else None
                authors.append([given, family, affiliation])

        # Get published year if available
        year = None
        if 'published-print' in message and 'date-parts' in message['published-print']:
            year = message['published-print']['date-parts'][0][0]

        # Get issue if available
        issue = None
        if 'journal-issue' in message and 'issue' in message['journal-issue']:
            issue = message['journal-issue']['issue']

        # Get journal name safely
        journal = None
        if message.get('container-title') and len(message['container-title']) > 0:
            journal = message['container-title'][0]

        return {
            'reference_type': reference_type_map.get(message.get('type')),
            'doi': message.get('DOI'),
            'year': year,
            'title': message['title'][0] if message.get('title') else None,
            'journal': journal,
            'volume': message.get('volume'),
            'issue': issue,
            'authors': authors,
            'working_paper_institution': None
        }
    except Exception as e:
        print(f"Error fetching reference data for DOI {doi}: {str(e)}")
        return {
            'doi': doi,
            'type': None,
            'year': None,
            'title': None,
            'journal': None,
            'volume': None,
            'issue': None,
            'authors': [],
            'working_paper_institution': None
        }


def fetch_llm_backup(text, openai_api_key):
    client = openai.OpenAI(api_key=openai_api_key)
    
    system_instruction = """Please determine if this citation is a journal article, a working paper, or a book. Return this in the reference_type schema field as either ['article', 'working_paper', 'book'].

IMPORTANT: For ALL reference types, you must extract and include the authors field.

If article, parse the authors as a list of lists [['first_1', 'last_1'], ['first_2', 'last_2']], parse the year, parse the title of the article, the name of the journal, the volume, and the issue

If working_paper, parse the authors as a list of lists [['first_1', 'last_1'], ['first_2', 'last_2']], parse the year, the title of the working paper, and the institution

If book, parse the authors as a list of lists [['first_1', 'last_1'], ['first_2', 'last_2']], parse the year, and the title

The authors field is REQUIRED for all reference types and should always be a list of [first_name, last_name] pairs.

Return ONLY a valid JSON object with this exact schema, no other text:
{
    "reference_type": "article" | "working_paper" | "book",
    "doi": null,
    "year": 2024,
    "title": "title of the work",
    "journal": "name of the journal if article",
    "volume": "volume number if article",
    "issue": "issue number if article",
    "authors": [["first1", "last1"], ["first2", "last2"]],  # Required for ALL types
    "working_paper_institution": "institution name if working paper"
}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini-2024-07-18",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": text}
            ],
            temperature=0
        )
        
        # Get the response content and parse it as JSON
        response_text = response.choices[0].message.content
        parsed_data = json.loads(response_text)
        
        # Convert the response to match the schema
        result = {
            'reference_type': parsed_data.get('reference_type'),
            'doi': None,
            'year': parsed_data.get('year'),
            'title': parsed_data.get('title'),
            'journal': parsed_data.get('journal'),
            'volume': parsed_data.get('volume'),
            'issue': parsed_data.get('issue'),
            'authors': parsed_data.get('authors', []),
            'working_paper_institution': parsed_data.get('working_paper_institution')
        }
        
        return result
        
    except Exception as e:
        print(f"Error in LLM parsing: {str(e)}")
        return {
            'reference_type': None,
            'doi': None,
            'year': None,
            'title': None,
            'journal': None,
            'volume': None,
            'issue': None,
            'authors': [],
            'working_paper_institution': None
        }

def safe_jsonl_append(data, filepath):
    """Safely append a single JSON object as a new line"""
    try:
        # Convert the data to a JSON string and add a newline
        json_str = json.dumps(data) + '\n'
        
        # Append to the file
        with open(filepath, 'a', buffering=1) as f:
            f.write(json_str)
            f.flush()
            os.fsync(f.fileno())
            
    except Exception as e:
        print(f"Error appending to JSONL: {str(e)}")
        raise e

def initialize_files():
    """Initialize necessary files if they don't exist"""
    # Initialize processed_dois.txt
    processed_file = Path('processed_dois.txt')
    if not processed_file.exists():
        processed_file.touch()
        print("Created processed_dois.txt")

    # Initialize articles_data.jsonl instead of .json
    output_file = Path('articles_data.jsonl')
    if not output_file.exists():
        output_file.touch()
        print("Created articles_data.jsonl")

def process_single_doi(args):
    doi, total_dois, current_position = args
    try:
        print(f"Processing DOI ({current_position}/{total_dois}): {doi}")
        article_data = fetch_complete_article_data(doi)
        return doi, article_data, None  # None means no error
    except Exception as e:
        print(f"Error processing DOI {doi}: {str(e)}")
        return doi, None, str(e)  # Return the error message

def process_dois_from_csv(doi_file):
    # Initialize files
    initialize_files()
    
    # Read DOIs from CSV
    df = pd.read_csv(doi_file)
    dois = df['DOI'].tolist()
    del df  # Clear DataFrame from memory
    
    # Load already processed DOIs
    processed_dois = load_processed_dois()
    
    # Filter out already processed DOIs
    dois_to_process = [doi for doi in dois if doi not in processed_dois]
    total_to_process = len(dois_to_process)
    
    print(f"Found {len(dois)} total DOIs")
    print(f"Already processed {len(processed_dois)} DOIs")
    print(f"Remaining DOIs to process: {total_to_process}")
    
    # Process DOIs in batches of 50
    batch_size = 50
    for batch_start in range(0, len(dois_to_process), batch_size):
        batch_end = min(batch_start + batch_size, len(dois_to_process))
        current_batch = dois_to_process[batch_start:batch_end]
        
        # Load only the most recent batch of data
        output_file = Path('articles_data.jsonl')
        articles_data = []  # Start fresh for each batch
        
        # Prepare arguments for worker function
        worker_args = [(doi, total_to_process, i+batch_start+1) 
                      for i, doi in enumerate(current_batch)]
        
        # Process current batch using thread pool
        results_lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(process_single_doi, args) for args in worker_args]
            
            # Process results as they complete
            for future in concurrent.futures.as_completed(futures):
                try:
                    doi, article_data, error = future.result()
                    if error is None and article_data is not None:
                        with results_lock:
                            try:
                                # Directly append the new data
                                safe_jsonl_append(article_data, output_file)
                                
                                # Mark DOI as processed
                                save_processed_doi(doi)
                                
                                print(f"Successfully processed and saved DOI: {doi}")
                            except Exception as e:
                                print(f"Error saving data for DOI {doi}: {str(e)}")
                                with open('error_log.txt', 'a') as f:
                                    f.write(f"Error with DOI {doi} at {datetime.now()}: {str(e)}\n")
                except Exception as e:
                    print(f"Error processing future: {str(e)}")
        
        # Clear memory after each batch
        articles_data = None
        print(f"Completed batch {batch_start//batch_size + 1}, cleared memory")

def read_jsonl(filepath):
    data = []
    with open(filepath, 'r') as f:
        for line in f:
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"Error reading line: {e}")
                continue
    return data

if __name__ == "__main__":
    # Get input file from command line argument
    if len(sys.argv) != 2:
        print("Usage: python scrape.py <doi_csv_file>")
        sys.exit(1)
    
    doi_file = sys.argv[1]
    if not os.path.exists(doi_file):
        print(f"Error: File {doi_file} not found")
        sys.exit(1)
    process_dois_from_csv(doi_file)
    

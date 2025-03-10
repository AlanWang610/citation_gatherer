from habanero import Crossref
import time
from datetime import datetime
import dotenv
import openai
import os
import json
import pandas as pd
import requests_cache
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures

dotenv.load_dotenv()
openai_api_key = os.getenv('OPENAI_API_KEY')

# Initialize Crossref API client
cr = Crossref(mailto="wangac@mit.edu")

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
requests_cache.install_cache('crossref_cache', backend='sqlite', expire_after=604800)  # Cache for 1 week

class RateLimiter:
    def __init__(self, calls_per_second):
        self.delay = 1.0 / calls_per_second
        self.last_call = time.time()
        self.lock = threading.Lock()
    
    def wait(self):
        with self.lock:
            current_time = time.time()
            time_to_wait = self.last_call + self.delay - current_time
            if time_to_wait > 0:
                time.sleep(time_to_wait)
            self.last_call = time.time()

# Adjust the rate limiter to be less conservative (50 requests per second instead of 2)
rate_limiter = RateLimiter(calls_per_second=25)  # Half of the 50 req/s limit to be safe

def load_processed_dois():
    """Load already processed DOIs from tracking file"""
    processed_file = Path('processed_dois.txt')
    if processed_file.exists():
        with open(processed_file, 'r') as f:
            return set(line.strip() for line in f)
    return set()

def save_processed_doi(doi):
    """Save a DOI to the tracking file"""
    with open('processed_dois.txt', 'a') as f:
        f.write(f"{doi}\n")

def fetch_complete_article_data(doi):
    rate_limiter.wait()  # Wait before making API call
    # Add follow parameter to handle redirects
    result = cr.works(ids=doi, follow=True)
    message = result['message']
    
    # Parse authors with error handling
    authors = []
    if 'author' in message:
        for author in message.get('author', []):
            given = author.get('given', '')
            family = author.get('family', '')
            authors.append([given, family])
    
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
        elif 'journal-title' in ref:
            ref_data = {k:v for k,v in ref.items() if k != 'key'}
            ref_data['reference_type'] = 'article'
            parsed_references.append(ref_data)
        elif 'article-title' in ref:
            ref_data = {k:v for k,v in ref.items() if k != 'key'}
            ref_data['reference_type'] = 'article'
            parsed_references.append(ref_data)
        elif 'unstructured' in ref:
            parsed_ref = fetch_llm_backup(ref['unstructured'], openai_api_key)
            parsed_references.append(parsed_ref)
        else:
            skipped_references += 1
            print(f"Warning: Reference {i+1} could not be parsed - no DOI, journal-title, or unstructured field")
    
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
        'volume': message.get('volume'),
        'issue': message.get('journal-issue', {}).get('issue'),
        'authors': authors,
        'references': parsed_references,
        'reference_stats': {
            'total_references': total_ref_count,
            'parsed_references': len(parsed_references),
            'skipped_references': skipped_references
        }
    }

def fetch_reference_article_data_by_doi(doi):
    try:
        rate_limiter.wait()  # Wait before making API call
        # First try with follow=True
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
        
        # Parse authors
        authors = []
        if 'author' in message:
            for author in message['author']:
                given = author.get('given', '')
                family = author.get('family', '')
                authors.append([given, family])

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
            'journal': journal,  # Use safer journal extraction
            'volume': message.get('volume'),
            'issue': issue,
            'authors': authors,
            'working_paper_institution': None,
            'book_title': None,
            'chapter_title': None
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
            'working_paper_institution': None,
            'book_title': None,
            'chapter_title': None
        }


def fetch_llm_backup(text, openai_api_key):
    client = openai.OpenAI(api_key=openai_api_key)
    
    system_instruction = """Please determine if this citation is a journal article, a working paper, or a book. Return this in the reference_type schema field as either ['article', 'working_paper', 'book'].

If article, parse the authors as a list of lists [['first_1', 'last_1'], ['first_2', 'last_2']], parse the year, parse the title of the article, the name of the journal, the volume, and the issue

If working_paper, parse the authors as a list of lists [['first_1', 'last_1'], ['first_2', 'last_2']], parse the year, the title of the working paper, and the institution

If book, parse parse the authors as a list of lists [['first_1', 'last_1'], ['first_2', 'last_2']], parse the year, the book title, and the chapter title

If a given field is missing, it's okay to return nothing in that field. If a field isn't requested for that reference type, don't return it.

Return ONLY a valid JSON object with this exact schema, no other text:
{
    "reference_type": "article" | "working_paper" | "book",
    "doi": null,
    "year": 2024,
    "title": "title of the work",
    "journal": "name of the journal if article",
    "volume": "volume number if article",
    "issue": "issue number if article",
    "authors": [["first1", "last1"], ["first2", "last2"]],
    "working_paper_institution": "institution name if working paper",
    "book_title": "title of the book if book",
    "chapter_title": "title of the chapter if book"
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
            'doi': None,  # Citations typically don't include DOIs
            'year': parsed_data.get('year'),
            'title': parsed_data.get('title'),
            'journal': parsed_data.get('journal'),
            'volume': parsed_data.get('volume'),
            'issue': parsed_data.get('issue'),
            'authors': parsed_data.get('authors', []),
            'working_paper_institution': parsed_data.get('working_paper_institution'),
            'book_title': parsed_data.get('book_title'),
            'chapter_title': parsed_data.get('chapter_title')
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
            'working_paper_institution': None,
            'book_title': None,
            'chapter_title': None
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

def process_dois_from_csv():
    # Initialize files
    initialize_files()
    
    # Read DOIs from CSV
    df = pd.read_csv('RFS_dois.csv')
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
                                with open('processed_dois.txt', 'a', buffering=1) as f:
                                    f.write(f"{doi}\n")
                                    f.flush()
                                    os.fsync(f.fileno())
                                
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
    process_dois_from_csv()
    

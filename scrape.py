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

# Create a global rate limiter (50 calls per second as per Crossref's guidelines)
rate_limiter = RateLimiter(calls_per_second=2)  # Conservative rate limit

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
    result = cr.works(ids=doi)
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
    
    return {
        'doi': message.get('DOI'),
        'type': message.get('type'),
        'published_date': published_date,
        'title': message.get('title', [None])[0],
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
        result = cr.works(ids=doi)
        message = result['message']
        
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

        return {
            'reference_type': reference_type_map.get(message.get('type')),
            'doi': message.get('DOI'),
            'year': year,
            'title': message['title'][0] if message.get('title') else None,
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
            'volume': None,
            'issue': None,
            'authors': [],
            'working_paper_institution': None,
            'book_title': None,
            'chapter_title': None
        }

def initialize_files():
    """Initialize necessary files if they don't exist"""
    # Initialize processed_dois.txt
    processed_file = Path('processed_dois.txt')
    if not processed_file.exists():
        processed_file.touch()
        print("Created processed_dois.txt")

    # Initialize articles_data.json
    output_file = Path('articles_data.json')
    if not output_file.exists():
        with open(output_file, 'w') as f:
            json.dump([], f)
        print("Created articles_data.json")

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
    
    # Load already processed DOIs
    processed_dois = load_processed_dois()
    
    # Filter out already processed DOIs
    dois_to_process = [doi for doi in dois if doi not in processed_dois]
    total_dois = len(dois)
    
    # Create or load existing output file
    output_file = Path('articles_data.json')
    try:
        with open(output_file, 'r') as f:
            articles_data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        print("Warning: Could not load existing articles_data.json, starting fresh")
        articles_data = []
    
    # Prepare arguments for worker function
    worker_args = [(doi, total_dois, i+1) for i, doi in enumerate(dois_to_process)]
    
    # Process DOIs using thread pool
    results_lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = list(executor.map(process_single_doi, worker_args))
        
        # Process results as they complete
        for doi, article_data, error in futures:
            if error is None and article_data is not None:
                with results_lock:
                    # Save to articles_data
                    articles_data.append(article_data)
                    # Save progress after each successful fetch
                    try:
                        with open(output_file, 'w') as f:
                            json.dump(articles_data, f, indent=4)
                        save_processed_doi(doi)
                    except Exception as e:
                        print(f"Error saving data for DOI {doi}: {str(e)}")

if __name__ == "__main__":
    process_dois_from_csv()
    

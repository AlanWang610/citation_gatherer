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
    result = cr.works(ids=doi)
    message = result['message']
    authors = message['author']
    parsed_authors = []
    for author in authors:
        given = author['given']
        family = author['family']
        parsed_authors.append([given, family])
    authors = parsed_authors
    
    references = message['reference']
    # Verify reference count matches
    total_ref_count = message['reference-count']
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
        'doi': message['DOI'],
        'type': message['type'],
        'published_date': f"{message['published-print']['date-parts'][0][0]}-{message['published-print']['date-parts'][0][1]:02d}-01",
        'title': message['title'][0],
        'volume': message['volume'],
        'issue': message['journal-issue']['issue'],
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

def process_dois_from_csv():
    # Read DOIs from CSV
    df = pd.read_csv('RFS_dois.csv')
    dois = df['DOI'].tolist()
    
    # Load already processed DOIs
    processed_dois = load_processed_dois()
    
    # Create or load existing output file
    output_file = Path('articles_data.json')
    if output_file.exists():
        with open(output_file, 'r') as f:
            articles_data = json.load(f)
    else:
        articles_data = []
    
    # Process each DOI
    total_dois = len(dois)
    for i, doi in enumerate(dois):
        if doi in processed_dois:
            print(f"Skipping already processed DOI ({i+1}/{total_dois}): {doi}")
            continue
            
        try:
            print(f"Processing DOI ({i+1}/{total_dois}): {doi}")
            article_data = fetch_complete_article_data(doi)
            articles_data.append(article_data)
            
            # Save progress after each successful fetch
            with open(output_file, 'w') as f:
                json.dump(articles_data, f, indent=4)
            
            # Mark DOI as processed
            save_processed_doi(doi)
            
        except Exception as e:
            print(f"Error processing DOI {doi}: {str(e)}")
            continue

if __name__ == "__main__":
    process_dois_from_csv()
    

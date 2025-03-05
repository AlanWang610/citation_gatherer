from habanero import Crossref
import time
import dotenv
import openai
import os
dotenv.load_dotenv()
openai_api_key = os.getenv('OPENAI_API_KEY')

cr = Crossref()

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
    ref_count = message['reference-count']
    if references and len(references) != ref_count:
        print(f"Warning: Reference count mismatch for DOI {doi}")
        print(f"Expected {ref_count} references but found {len(references)}")
    parsed_references = []
    for i, ref in enumerate(references):
        time.sleep(0.02)
        if 'DOI' in ref:
            parsed_ref = fetch_reference_article_data(ref['DOI'])
            parsed_references.append(parsed_ref)
        elif 'journal-title' in ref:
            ref_data = {k:v for k,v in ref.items() if k != 'key'}
            ref_data['reference_type'] = 'article'
            parsed_references.append(ref_data)
        elif 'unstructured' in ref:
            parsed_ref = fetch_llm_backup(ref['unstructured'], openai_api_key)
            parsed_references.append(parsed_ref)        
    references = parsed_references
    return {
        'doi': message['DOI'],
        'type': message['type'],
        'published_date': message['published-print']['date-parts'][0],
        'publisher': message['publisher'],
        'title': message['title'][0],
        'volume': message['volume'],
        'issue': message['journal-issue']['issue'],
        'authors': authors,
        'references': references
    }

def fetch_reference_article_data(doi):
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

        # Get published date if available
        published_date = None
        if 'published-print' in message and 'date-parts' in message['published-print']:
            published_date = message['published-print']['date-parts'][0]

        # Get issue if available
        issue = None
        if 'journal-issue' in message and 'issue' in message['journal-issue']:
            issue = message['journal-issue']['issue']

        return {
            'doi': message.get('DOI'),
            'type': message.get('type'),
            'published_date': published_date,
            'publisher': message.get('publisher'),
            'title': message['title'][0] if message.get('title') else None,
            'volume': message.get('volume'),
            'issue': issue,
            'authors': authors
        }
    except Exception as e:
        print(f"Error fetching reference data for DOI {doi}: {str(e)}")
        return {
            'doi': doi,
            'type': None,
            'published_date': None, 
            'publisher': None,
            'title': None,
            'volume': None,
            'issue': None,
            'authors': []
        }


def llm_backup(text):
    
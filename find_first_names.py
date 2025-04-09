import json
import csv
import os
import re
import argparse
import time
from difflib import SequenceMatcher
from tqdm import tqdm

def is_initial_name(name):
    """Check if name appears to be just an initial (with or without period)"""
    if not name:
        return False
        
    # Remove any periods and spaces
    cleaned = name.replace('.', '').replace(' ', '')
    
    # Check if it's a single letter (like "J") - must be capitalized
    if len(cleaned) == 1 and cleaned.isupper():
        return True
    
    # Check if it's two-letter initials (like "JE" or "J.E." or "P. A.") - must be capitalized
    if len(cleaned) == 2 and cleaned.isupper():
        return True
        
    # Check for patterns like "P. A." or "J. R."
    if re.match(r'^[A-Z]\.\s+[A-Z]\.?$', name):
        return True
    
    # Check if it's initials with periods (like "J.E." or "J. E.") - first letter must be capitalized
    if '.' in name and name[0].isupper():
        # Count the number of periods - if it's similar to the number of characters, it's likely initials
        period_count = name.count('.')
        letter_count = sum(1 for c in name if c.isalpha())
        # Cap to 3 letters with periods (like "J.E.A.")
        if period_count >= letter_count - 1 and letter_count <= 3:
            return True
    
    return False

def count_jsonl_lines(file_path):
    """Count the number of lines in a JSONL file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return sum(1 for _ in f)

def normalize_title(title):
    """Normalize title for better matching"""
    if not title:
        return ""
    
    # Convert to lowercase
    title = title.lower()
    
    # Remove punctuation and extra whitespace
    title = re.sub(r'[^\w\s]', ' ', title)
    title = re.sub(r'\s+', ' ', title).strip()
    
    # Remove common articles and prepositions
    stop_words = ['a', 'an', 'the', 'and', 'or', 'but', 'of', 'in', 'on', 'at', 'to', 'for', 'with']
    words = title.split()
    filtered_words = [word for word in words if word not in stop_words]
    
    return ' '.join(filtered_words)

def levenshtein_distance(s1, s2):
    """Calculate the Levenshtein distance between two strings"""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]

def similarity_ratio(s1, s2):
    """Calculate similarity ratio between two strings"""
    return SequenceMatcher(None, s1, s2).ratio()

def parse_author_name(author_string):
    """Parse author name and determine if it's in 'Last, First' or 'First Last' format"""
    author_string = author_string.strip()
    
    # Check if it's in "Last, First" format
    if ',' in author_string:
        parts = author_string.split(',', 1)
        last_name = parts[0].strip()
        first_name = parts[1].strip() if len(parts) > 1 else ""
        return last_name, first_name, "last_first"
    
    # Otherwise assume "First Last" format
    parts = author_string.split()
    if len(parts) >= 2:
        last_name = parts[-1]
        first_name = ' '.join(parts[:-1])
        return last_name, first_name, "first_last"
    
    # If only one part, assume it's a last name
    return author_string, "", "unknown"

def load_csv_data(csv_file):
    """Load article data from CSV file into a searchable format"""
    article_data = {}
    reference_data = {}
    
    # Also create normalized title mappings
    normalized_article_titles = {}
    normalized_reference_titles = {}
    
    # Count lines for progress bar
    total_lines = sum(1 for _ in open(csv_file, 'r', encoding='utf-8')) - 1  # Subtract header
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in tqdm(reader, total=total_lines, desc="Loading CSV data"):
            # Store main article data
            article_title = row['article.title'].strip()
            if article_title:
                article_authors = row['article.authors'].split(';')
                # Parse author names and store with format information
                parsed_authors = []
                for author in article_authors:
                    last_name, first_name, format_type = parse_author_name(author)
                    parsed_authors.append((last_name, first_name, format_type))
                article_data[article_title] = parsed_authors
                
                # Store normalized title mapping
                norm_title = normalize_title(article_title)
                if norm_title:
                    normalized_article_titles[norm_title] = article_title
            
            # Store reference data
            ref_title = row['reference.title'].strip()
            if ref_title:
                ref_authors = row['reference.authors'].split(';')
                # Parse reference author names
                parsed_ref_authors = []
                for author in ref_authors:
                    last_name, first_name, format_type = parse_author_name(author)
                    parsed_ref_authors.append((last_name, first_name, format_type))
                
                if ref_title not in reference_data:
                    reference_data[ref_title] = parsed_ref_authors
                    
                    # Store normalized title mapping
                    norm_ref_title = normalize_title(ref_title)
                    if norm_ref_title:
                        normalized_reference_titles[norm_ref_title] = ref_title
    
    return article_data, reference_data, normalized_article_titles, normalized_reference_titles

def find_matching_authors(target_last_name, authors_list):
    """Find authors with matching last name in the authors list"""
    matches = []
    for last_name, first_name, format_type in authors_list:
        if last_name == target_last_name:
            matches.append((last_name, first_name, format_type))
    return matches

def find_matching_title(title, normalized_titles, max_distance=2):
    """Find matching title using normalized form and Levenshtein distance"""
    if not title:
        return None
    
    # First try exact match
    norm_title = normalize_title(title)
    if norm_title in normalized_titles:
        return normalized_titles[norm_title]
    
    # If no exact match, try fuzzy matching
    best_match = None
    best_score = 0
    
    for norm_key, original_title in normalized_titles.items():
        # Skip very different length titles
        if abs(len(norm_key) - len(norm_title)) > max_distance * 3:
            continue
        
        # Calculate similarity
        similarity = similarity_ratio(norm_title, norm_key)
        
        # If similarity is high enough, consider it a match
        if similarity > 0.9 and similarity > best_score:
            best_score = similarity
            best_match = original_title
        elif similarity > 0.8:
            # For lower similarities, check Levenshtein distance
            distance = levenshtein_distance(norm_title, norm_key)
            if distance <= max_distance and similarity > best_score:
                best_score = similarity
                best_match = original_title
    
    return best_match

def process_jsonl_file(jsonl_file, output_file, article_data, reference_data, 
                      normalized_article_titles, normalized_reference_titles,
                      max_distance=2):
    """Process the JSONL file and update author names"""
    # Check if output file exists and get the number of processed lines
    processed_lines = 0
    if os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            processed_lines = sum(1 for _ in f)
    
    # Count total lines for progress tracking
    total_lines = count_jsonl_lines(jsonl_file)
    remaining_lines = total_lines - processed_lines
    
    # Statistics for reporting
    stats = {
        'articles_processed': 0,
        'authors_updated': 0,
        'reference_authors_updated': 0,
        'title_matches': 0,
        'title_fuzzy_matches': 0,
        'ref_title_matches': 0,
        'ref_title_fuzzy_matches': 0,
        'start_time': time.time()
    }
    
    # Open input and output files
    with open(jsonl_file, 'r', encoding='utf-8') as in_f:
        # Skip already processed lines
        for _ in range(processed_lines):
            next(in_f, None)
        
        # Process remaining lines
        with open(output_file, 'a', encoding='utf-8') as out_f:
            # Create progress bar
            pbar = tqdm(total=remaining_lines, initial=0, 
                        desc=f"Processing articles ({processed_lines}/{total_lines})")
            
            for line in in_f:
                article = json.loads(line)
                stats['articles_processed'] += 1
                
                # Process main article authors
                if 'authors' in article:
                    article_title = article.get('title', '')
                    
                    # Try to find matching title
                    matched_title = None
                    if article_title in article_data:
                        matched_title = article_title
                        stats['title_matches'] += 1
                    else:
                        matched_title = find_matching_title(article_title, normalized_article_titles, max_distance)
                        if matched_title:
                            stats['title_fuzzy_matches'] += 1
                    
                    if matched_title:
                        csv_authors = article_data[matched_title]
                        for i, author in enumerate(article['authors']):
                            if author[0] and is_initial_name(author[0]):
                                # Try to find matching author in CSV data
                                matches = find_matching_authors(author[1], csv_authors)
                                if matches:
                                    for last_name, first_name, format_type in matches:
                                        if first_name:  # Only update if we have a first name
                                            article['authors'][i][0] = first_name
                                            stats['authors_updated'] += 1
                                            break
                
                # Process references authors
                if 'references' in article:
                    for ref_idx, ref in enumerate(article['references']):
                        if 'authors' in ref and 'title' in ref:
                            ref_title = ref['title']
                            
                            # Try to find matching reference title
                            matched_ref_title = None
                            if ref_title in reference_data:
                                matched_ref_title = ref_title
                                stats['ref_title_matches'] += 1
                            else:
                                matched_ref_title = find_matching_title(ref_title, normalized_reference_titles, max_distance)
                                if matched_ref_title:
                                    stats['ref_title_fuzzy_matches'] += 1
                            
                            if matched_ref_title:
                                csv_ref_authors = reference_data[matched_ref_title]
                                for i, author in enumerate(ref['authors']):
                                    if author[0] and is_initial_name(author[0]):
                                        # Try to find matching author in CSV reference data
                                        matches = find_matching_authors(author[1], csv_ref_authors)
                                        if matches:
                                            for last_name, first_name, format_type in matches:
                                                if first_name:  # Only update if we have a first name
                                                    article['references'][ref_idx]['authors'][i][0] = first_name
                                                    stats['reference_authors_updated'] += 1
                                                    break
                
                # Write the updated article to the output file
                out_f.write(json.dumps(article) + '\n')
                
                # Update progress bar
                pbar.update(1)
                
                # Update progress description occasionally
                if stats['articles_processed'] % 100 == 0:
                    elapsed = time.time() - stats['start_time']
                    rate = stats['articles_processed'] / elapsed if elapsed > 0 else 0
                    pbar.set_description(
                        f"Processing: {processed_lines + stats['articles_processed']}/{total_lines} "
                        f"({rate:.1f} articles/sec)"
                    )
            
            # Close progress bar
            pbar.close()
    
    # Calculate elapsed time
    elapsed_time = time.time() - stats['start_time']
    hours, remainder = divmod(elapsed_time, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    # Print final statistics
    print("\nProcessing Statistics:")
    print(f"Total articles processed: {stats['articles_processed']}")
    print(f"Main article authors updated: {stats['authors_updated']}")
    print(f"Reference authors updated: {stats['reference_authors_updated']}")
    print(f"Title exact matches: {stats['title_matches']}")
    print(f"Title fuzzy matches: {stats['title_fuzzy_matches']}")
    print(f"Reference title exact matches: {stats['ref_title_matches']}")
    print(f"Reference title fuzzy matches: {stats['ref_title_fuzzy_matches']}")
    print(f"Processing time: {int(hours)}h {int(minutes)}m {int(seconds)}s")
    
    return stats

def main():
    # Set up command line argument parsing
    parser = argparse.ArgumentParser(description='Find full first names for authors with initials')
    parser.add_argument('csv_file', help='Path to the CSV file with author data')
    parser.add_argument('jsonl_file', help='Path to the JSONL file to process')
    parser.add_argument('output_file', help='Path to the output JSONL file')
    parser.add_argument('--max-distance', type=int, default=2, 
                        help='Maximum Levenshtein distance for fuzzy matching (default: 2)')
    args = parser.parse_args()
    
    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(args.output_file), exist_ok=True)
    
    # Print start message
    print(f"Starting first name resolution process")
    print(f"CSV file: {args.csv_file}")
    print(f"Input JSONL: {args.jsonl_file}")
    print(f"Output JSONL: {args.output_file}")
    print(f"Max Levenshtein distance: {args.max_distance}")
    
    # Load CSV data
    print(f"\nLoading CSV data...")
    article_data, reference_data, normalized_article_titles, normalized_reference_titles = load_csv_data(args.csv_file)
    print(f"Loaded {len(article_data)} articles and {len(reference_data)} references from CSV")
    print(f"Created {len(normalized_article_titles)} normalized article titles")
    print(f"Created {len(normalized_reference_titles)} normalized reference titles")
    
    # Process JSONL file
    print(f"\nProcessing JSONL file...")
    stats = process_jsonl_file(
        args.jsonl_file, 
        args.output_file, 
        article_data, 
        reference_data, 
        normalized_article_titles, 
        normalized_reference_titles,
        args.max_distance
    )
    
    print(f"\nProcessing complete! Results written to {args.output_file}")

if __name__ == "__main__":
    main()

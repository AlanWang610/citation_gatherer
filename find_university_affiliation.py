import requests
import json
import time
import argparse
import os
from typing import List, Dict, Any, Optional
import Levenshtein  # For fuzzy string matching

def search_author_openalex(first_name: str, last_name: str, paper_title: Optional[str] = None, save_json: bool = False) -> List[Dict[str, Any]]:
    """
    Search for an author in OpenAlex using first and last name, with optional paper title for disambiguation.
    
    Args:
        first_name: Author's first name
        last_name: Author's last name
        paper_title: Optional paper title to help with disambiguation
        save_json: Whether to save the API response as JSON
        
    Returns:
        List of potential author matches with their details
    """
    base_url = "https://api.openalex.org/authors"
    
    # Construct the query
    query = f"display_name.search:{first_name} {last_name}"
    
    params = {
        "filter": query,
        "per-page": 10  # Limit results to avoid large responses
    }
    
    # Add email for polite pool
    headers = {"Accept": "application/json"}
    
    try:
        response = requests.get(base_url, params=params, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        
        # Save the JSON response if requested
        if save_json:
            os.makedirs("api_responses", exist_ok=True)
            filename = f"api_responses/openalex_search_{first_name}_{last_name}.json"
            with open(filename, "w") as f:
                json.dump(data, f, indent=2)
            print(f"Saved search results to {filename}")
        
        if data["meta"]["count"] == 0:
            print(f"No authors found for {first_name} {last_name}")
            return []
        
        authors = data["results"]
        
        # If paper title is provided, try to filter authors who have written that paper
        if paper_title and len(authors) > 1:
            filtered_authors = []
            for author in authors:
                # Get works by this author
                works_url = author["works_api_url"]
                works_response = requests.get(works_url, headers=headers)
                works_data = works_response.json()
                
                # Save the works JSON response if requested
                if save_json:
                    author_id = author["id"].split("/")[-1]
                    filename = f"api_responses/openalex_works_{first_name}_{last_name}_{author_id}.json"
                    with open(filename, "w") as f:
                        json.dump(works_data, f, indent=2)
                    print(f"Saved works data to {filename}")
                
                # Check if any work title matches the paper title using fuzzy matching
                for work in works_data.get("results", []):
                    work_title = work.get("title", "")
                    # Use fuzzy matching with Levenshtein distance
                    if work_title and is_title_match(work_title, paper_title):
                        filtered_authors.append(author)
                        break
                
                # Respect rate limits
                time.sleep(0.1)
            
            if filtered_authors:
                return filtered_authors
        
        return authors
        
    except requests.exceptions.RequestException as e:
        print(f"Error querying OpenAlex API: {e}")
        return []

def get_affiliations_openalex(author_id: str, save_json: bool = False) -> List[Dict[str, Any]]:
    """
    Get the affiliations for a specific author by ID using OpenAlex.
    
    Args:
        author_id: OpenAlex author ID
        save_json: Whether to save the API response as JSON
        
    Returns:
        List of affiliations for the author
    """
    url = f"https://api.openalex.org/authors/{author_id}"
    
    # Add email for polite pool
    headers = {"Accept": "application/json"}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        
        # Save the JSON response if requested
        if save_json:
            os.makedirs("api_responses", exist_ok=True)
            author_id_short = author_id.split("/")[-1]
            filename = f"api_responses/openalex_author_{author_id_short}.json"
            with open(filename, "w") as f:
                json.dump(data, f, indent=2)
            print(f"Saved author details to {filename}")
        
        # Extract current and past affiliations
        affiliations = []
        
        # Current institution
        if "last_known_institution" in data and data["last_known_institution"]:
            affiliations.append({
                "institution": data["last_known_institution"]["display_name"],
                "id": data["last_known_institution"]["id"],
                "type": "current"
            })
        
        # Get more detailed affiliation history if available
        if "x_concepts" in data and data["x_concepts"]:
            for concept in data["x_concepts"]:
                if concept.get("wikidata") == "Q3918":  # University
                    affiliations.append({
                        "institution": concept["display_name"],
                        "id": concept["id"],
                        "type": "associated"
                    })
        
        return affiliations
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching affiliations from OpenAlex: {e}")
        return []

def search_author_semantic_scholar(first_name: str, last_name: str, paper_title: Optional[str] = None, save_json: bool = False) -> List[Dict[str, Any]]:
    """
    Search for an author in Semantic Scholar using first and last name, with optional paper title for disambiguation.
    
    Args:
        first_name: Author's first name
        last_name: Author's last name
        paper_title: Optional paper title to help with disambiguation
        save_json: Whether to save the API response as JSON
        
    Returns:
        List of potential author matches with their details
    """
    base_url = "https://api.semanticscholar.org/graph/v1/author/search"
    
    # Construct the query
    query = f"{first_name} {last_name}"
    
    params = {
        "query": query,
        "limit": 10,  # Limit results to avoid large responses
        "fields": "name,affiliations,paperCount,papers.title"
    }
    
    headers = {"Accept": "application/json"}
    
    try:
        response = requests.get(base_url, params=params, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        
        # Save the JSON response if requested
        if save_json:
            os.makedirs("api_responses", exist_ok=True)
            filename = f"api_responses/semanticscholar_search_{first_name}_{last_name}.json"
            with open(filename, "w") as f:
                json.dump(data, f, indent=2)
            print(f"Saved search results to {filename}")
            
            # Also save the API URL for reference
            url_filename = f"api_responses/semanticscholar_search_url_{first_name}_{last_name}.txt"
            full_url = f"{base_url}?query={query}&limit=10&fields=name,affiliations,paperCount,papers.title"
            with open(url_filename, "w") as f:
                f.write(full_url)
            print(f"Saved API URL to {url_filename}")
        
        if "data" not in data or len(data["data"]) == 0:
            print(f"No authors found for {first_name} {last_name}")
            return []
        
        authors = data["data"]
        
        # If paper title is provided, try to filter authors who have written that paper
        if paper_title and len(authors) > 1:
            filtered_authors = []
            for author in authors:
                # Check if any paper title matches the paper title using fuzzy matching
                if "papers" in author:
                    for paper in author["papers"]:
                        paper_title_text = paper.get("title", "")
                        if paper_title_text and is_title_match(paper_title_text, paper_title):
                            filtered_authors.append(author)
                            break
            
            if filtered_authors:
                return filtered_authors
        
        return authors
        
    except requests.exceptions.RequestException as e:
        print(f"Error querying Semantic Scholar API: {e}")
        return []

def get_affiliations_semantic_scholar(author_data: Dict[str, Any], save_json: bool = False) -> List[Dict[str, Any]]:
    """
    Get detailed affiliations for a specific author from Semantic Scholar.
    
    Args:
        author_data: Basic author data from search results
        save_json: Whether to save the API response as JSON
        
    Returns:
        List of affiliations for the author
    """
    affiliations = []
    
    # First, check if we already have affiliations in the search results
    if "affiliations" in author_data and author_data["affiliations"]:
        for affiliation in author_data["affiliations"]:
            affiliations.append({
                "institution": affiliation,
                "type": "current"
            })
    
    # If we have an author ID, make a detailed API call to get more information
    if "authorId" in author_data and author_data["authorId"]:
        author_id = author_data["authorId"]
        url = f"https://api.semanticscholar.org/graph/v1/author/{author_id}"
        
        params = {
            "fields": "name,affiliations,homepage,papers.year,papers.title,papers.venue,papers.authors"
        }
        
        headers = {"Accept": "application/json"}
        
        try:
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()
            
            detailed_data = response.json()
            
            # Save the JSON response if requested
            if save_json:
                os.makedirs("api_responses", exist_ok=True)
                filename = f"api_responses/semanticscholar_author_{author_id}.json"
                with open(filename, "w") as f:
                    json.dump(detailed_data, f, indent=2)
                print(f"Saved author details to {filename}")
                
                # Also save the API URL for reference
                url_filename = f"api_responses/semanticscholar_author_url_{author_id}.txt"
                full_url = f"{url}?fields=name,affiliations,homepage,papers.year,papers.title,papers.venue,papers.authors"
                with open(url_filename, "w") as f:
                    f.write(full_url)
                print(f"Saved API URL to {url_filename}")
            
            # Get current affiliations
            if "affiliations" in detailed_data and detailed_data["affiliations"]:
                # Clear previous affiliations if we have more detailed ones
                if affiliations:
                    affiliations = []
                
                for affiliation in detailed_data["affiliations"]:
                    affiliations.append({
                        "institution": affiliation,
                        "type": "current"
                    })
            
            # Try to extract historical affiliations from papers
            if "papers" in detailed_data and detailed_data["papers"]:
                # Sort papers by year (newest first) to prioritize recent affiliations
                sorted_papers = sorted(
                    [p for p in detailed_data["papers"] if "year" in p and p["year"]],
                    key=lambda x: x["year"],
                    reverse=True
                )
                
                # Track institutions we've already seen to avoid duplicates
                seen_institutions = {aff["institution"].lower() for aff in affiliations}
                
                for paper in sorted_papers[:20]:  # Look at the 20 most recent papers
                    if "authors" in paper:
                        # Find this author in the paper's author list
                        for paper_author in paper["authors"]:
                            if paper_author.get("authorId") == author_id and "affiliations" in paper_author:
                                for paper_affiliation in paper_author["affiliations"]:
                                    # Skip if we've already seen this institution
                                    if paper_affiliation.lower() in seen_institutions:
                                        continue
                                    
                                    affiliations.append({
                                        "institution": paper_affiliation,
                                        "type": "historical",
                                        "year": paper.get("year", "unknown")
                                    })
                                    
                                    seen_institutions.add(paper_affiliation.lower())
            
            return affiliations
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching detailed author data from Semantic Scholar: {e}")
            # Return basic affiliations if detailed request fails
            return affiliations
    
    return affiliations

def is_title_match(title1: str, title2: str, max_distance: int = 3) -> bool:
    """
    Check if two titles match using Levenshtein distance.
    
    Args:
        title1: First title
        title2: Second title
        max_distance: Maximum Levenshtein distance to consider a match
        
    Returns:
        True if titles match within the specified distance, False otherwise
    """
    # Convert to lowercase for case-insensitive comparison
    title1 = title1.lower()
    title2 = title2.lower()
    
    # Check if one title is a substring of the other (with some flexibility)
    if title1 in title2 or title2 in title1:
        return True
    
    # Check Levenshtein distance for similar titles
    distance = Levenshtein.distance(title1, title2)
    
    # For longer titles, allow proportionally larger distances
    max_length = max(len(title1), len(title2))
    if max_length > 50:
        # Allow up to 10% of the title length for longer titles
        adjusted_max_distance = min(max(max_distance, int(max_length * 0.1)), 10)
        return distance <= adjusted_max_distance
    
    return distance <= max_distance

def main():
    parser = argparse.ArgumentParser(description="Find university affiliations for academics using academic APIs")
    parser.add_argument("--first", required=True, help="Author's first name")
    parser.add_argument("--last", required=True, help="Author's last name")
    parser.add_argument("--title", help="Paper title for disambiguation (optional)")
    parser.add_argument("--api", choices=["openalex", "semanticscholar"], default="openalex", 
                        help="API to use for searching (default: openalex)")
    parser.add_argument("--max-distance", type=int, default=3,
                        help="Maximum Levenshtein distance for fuzzy title matching (default: 3)")
    parser.add_argument("--save-json", action="store_true",
                        help="Save the API responses as JSON files")
    
    args = parser.parse_args()
    
    print(f"Searching for author: {args.first} {args.last} using {args.api} API")
    
    if args.api == "openalex":
        authors = search_author_openalex(args.first, args.last, args.title, args.save_json)
        
        if not authors:
            print("No matching authors found.")
            return
        
        print(f"Found {len(authors)} potential matches:")
        
        for i, author in enumerate(authors):
            print(f"\n[{i+1}] {author['display_name']}")
            print(f"  ID: {author['id']}")
            print(f"  Works count: {author['works_count']}")
            
            if "last_known_institution" in author and author["last_known_institution"]:
                print(f"  Current institution: {author['last_known_institution']['display_name']}")
            
            # Get detailed affiliations
            affiliations = get_affiliations_openalex(author["id"], args.save_json)
            
            if affiliations:
                print("  Affiliations:")
                for affiliation in affiliations:
                    print(f"    - {affiliation['institution']} ({affiliation['type']})")
            else:
                print("  No detailed affiliation information available")
            
            # Respect rate limits
            time.sleep(0.1)
    
    elif args.api == "semanticscholar":
        authors = search_author_semantic_scholar(args.first, args.last, args.title, args.save_json)
        
        if not authors:
            print("No matching authors found.")
            return
        
        print(f"Found {len(authors)} potential matches:")
        
        for i, author in enumerate(authors):
            print(f"\n[{i+1}] {author.get('name', 'Unknown')}")
            print(f"  ID: {author.get('authorId', 'Unknown')}")
            print(f"  Papers count: {author.get('paperCount', 'Unknown')}")
            
            # Get detailed affiliations
            affiliations = get_affiliations_semantic_scholar(author, args.save_json)
            
            if affiliations:
                print("  Affiliations:")
                current_affiliations = [a for a in affiliations if a['type'] == 'current']
                historical_affiliations = [a for a in affiliations if a['type'] == 'historical']
                
                # Show current affiliations first
                for affiliation in current_affiliations:
                    print(f"    - {affiliation['institution']} (current)")
                
                # Then show historical affiliations with years
                for affiliation in historical_affiliations:
                    print(f"    - {affiliation['institution']} (historical, {affiliation.get('year', 'unknown')})")
            else:
                print("  No affiliation information available")
            
            # Respect rate limits
            time.sleep(0.1)
    
    # Test with Igor Makarov
    if args.first == "Igor" and args.last == "Makarov":
        print("\nTest case for Igor Makarov completed.")

if __name__ == "__main__":
    main()

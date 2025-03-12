import json
import networkx as nx
import pickle
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
from itertools import product

def load_articles(file_path):
    """Load articles from a JSONL file."""
    articles = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            articles.append(json.loads(line))
    return articles

def should_filter_title(title):
    """Check if title should be filtered out."""
    titles_to_filter = {
        "editorial board", "publishers note", "advert:", "call for papers:", 
        "table of contents", "forthcoming articles", "cover", "index", "acknowledgments", 
        "erratum", "acknowledgements", "joint editorial", "a note from the editor", "annual report", 
        "oup accepted manuscript", "turnaround times", "recent referees", "front matter", "back matter", 
        "prize announcement", "index to volume", "masthead", "front cover", "back cover", 
        "journal of political economy", "jpe submissions", "annual meeting", "medalist", 
        "executive commmittee meetings", "report of the", "american economic association"
    }
    
    if title in ["Index", "Content"]:
        return True
        
    title = title.lower()
    return any(filter_term in title for filter_term in titles_to_filter)

def format_authors(authors):
    """Convert authors list to string representation."""
    if not authors:
        return ""
    return "; ".join(" ".join(author) for author in authors)

def build_citation_network():
    """Build directed citation network from article data."""
    G = nx.DiGraph()
    
    # Load articles from all sources
    data_files = [
        'data/AER_articles.jsonl',
        'data/JPE_articles.jsonl', 
        'data/RFS_articles.jsonl'
    ]
    
    for file_path in data_files:
        articles = load_articles(file_path)
        
        for article in articles:
            # Skip articles with filtered titles
            if 'title' not in article or should_filter_title(article['title']):
                continue
                
            # Skip if no DOI
            if 'doi' not in article or not article['doi']:
                continue
                
            # Add node for main article with metadata
            main_doi = article['doi']
            
            # Convert None values to empty strings for node attributes
            node_attrs = {
                'title': article.get('title', ''),
                'year': article.get('published_date', '').split('-')[0] if article.get('published_date') else '',
                'journal': article.get('journal', ''),
                'authors': format_authors(article.get('authors', []))
            }
            
            # Remove any None values
            node_attrs = {k: v for k, v in node_attrs.items() if v is not None}
            
            G.add_node(main_doi, **node_attrs)
            
            # Add edges to references
            if 'references' in article:
                for ref in article['references']:
                    if 'doi' in ref and ref['doi']:
                        ref_doi = ref['doi']
                        
                        # Get journal from either journal or journal-title field
                        journal = ref.get('journal') or ref.get('journal-title', '')
                        
                        # Convert None values to empty strings for reference node attributes
                        ref_attrs = {
                            'title': ref.get('title', ''),
                            'year': str(ref.get('year', '')),
                            'journal': journal,
                            'authors': format_authors(ref.get('authors', []))
                        }
                        
                        # Remove any None values
                        ref_attrs = {k: v for k, v in ref_attrs.items() if v is not None}
                        
                        # Add node for reference with metadata
                        G.add_node(ref_doi, **ref_attrs)
                        
                        # Add directed edge from article to reference
                        G.add_edge(main_doi, ref_doi)
    
    # Debug: Check for None values in node attributes
    for node, attrs in G.nodes(data=True):
        for key, value in attrs.items():
            if value is None:
                print(f"Found None value in node {node} for attribute {key}")
    
    return G

def load_saved_graph(format='pickle'):
    """Load the saved citation network graph.
    
    Args:
        format (str): Format to load - 'pickle', 'graphml', or 'gexf'
    
    Returns:
        networkx.DiGraph: The loaded citation network
    """
    if format == 'pickle':
        with open("saved_graphs/citation_network.pickle", "rb") as f:
            return pickle.load(f)
    elif format == 'graphml':
        return nx.read_graphml("saved_graphs/citation_network.graphml")
    elif format == 'gexf':
        return nx.read_gexf("saved_graphs/citation_network.gexf")
    else:
        raise ValueError("Unknown format. Use 'pickle', 'graphml', or 'gexf'")

def abbreviate_title(title, max_chars_per_line=30, max_lines=3):
    """Format title to fit in visualization with line breaks."""
    if not title:
        return "No title"
    
    words = title.split()
    lines = []
    current_line = []
    current_length = 0
    
    for word in words:
        if current_length + len(word) + 1 <= max_chars_per_line:
            current_line.append(word)
            current_length += len(word) + 1
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            current_length = len(word)
            
            if len(lines) >= max_lines - 1:
                break
    
    if current_line and len(lines) < max_lines:
        lines.append(" ".join(current_line))
    
    if len(words) > sum(len(line.split()) for line in lines):
        lines[-1] = lines[-1] + "..."
    
    return "\n".join(lines)

def add_period_variants(names):
    """Add variants with periods to journal names."""
    expanded = set()
    for name in names:
        words = name.split()
        for i in range(len(words)):
            variants = [(w, w + '.') for w in words]
            for combo in product(*variants):
                expanded.add(' '.join(combo))
    return expanded

def get_journal_color(journal_name):
    """Return color based on journal name."""
    if not journal_name:
        return 'lightblue'
        
    journal_name = journal_name.lower()
    
    # Define journal name sets
    jf_names = {"j finan", "journal finan", "j financ", "journal financ", "j finance", "journal finance", 
                "j of finan", "journal of finan", "j of financ", "journal of financ", "j of finance", 
                "journal of finance"}
    
    jfe_names = {"j finan econ", "journal finan econ", "j financ econ", "journal financ econ", 
                 "j finance econ", "journal finance econ", "j of finan econ", "journal of finan econ", 
                 "j of financ econ", "journal of financ econ", "j of finance econ", 
                 "journal of finance econ", "journal of financial economics"}
    
    rfs_names = {"rev finan stud", "review finan stud", "rev financ stud", "review financ stud", 
                 "rev finance stud", "review finance stud", "rev of finan stud", "review of finan stud", 
                 "rev of financ stud", "review of financ stud", "rev of finance stud", 
                 "review of finance stud", "review of financial studies"}
    
    aer_names = {"am econ rev", "ame econ rev", "amer econ rev", "american econ rev", "am econ review", 
                 "ame econ review", "amer econ review", "american econ review", "american economic review"}
    
    econometrica_names = {"econometrica"}
    
    qje_names = {"q j econ", "q j of econ", "q j economics", "q j of economics", "quart j econ", 
                 "quart j of econ", "quart j economics", "quart j of economics", "quarterly j econ", 
                 "quarterly j of econ", "quarterly j economnics", "quarterly j of economnics", 
                 "quarterly journal economics", "quarterly journal of economics"}
    
    res_names = {"rev econ stud", "review of economics studies"}
    
    jpe_names = {"j polit econ", "j polit economics", "j political econ", "j political economics", 
                 "journal of political economy"}
    
    # Add period variants
    jf_names = add_period_variants(jf_names)
    jfe_names = add_period_variants(jfe_names)
    rfs_names = add_period_variants(rfs_names)
    aer_names = add_period_variants(aer_names)
    econometrica_names = add_period_variants(econometrica_names)
    qje_names = add_period_variants(qje_names)
    res_names = add_period_variants(res_names)
    jpe_names = add_period_variants(jpe_names)
    
    # Add 'the' variants
    for name_set in [jf_names, jfe_names, rfs_names, aer_names, econometrica_names, qje_names, res_names, jpe_names]:
        name_set.update({f"the {name}" for name in name_set})
    
    # Color mapping
    if any(name in journal_name for name in jf_names):
        return 'red'
    elif any(name in journal_name for name in jfe_names):
        return 'blue'
    elif any(name in journal_name for name in rfs_names):
        return 'green'
    elif any(name in journal_name for name in aer_names):
        return 'purple'
    elif any(name in journal_name for name in econometrica_names):
        return 'orange'
    elif any(name in journal_name for name in qje_names):
        return 'yellow'
    elif any(name in journal_name for name in res_names):
        return 'brown'
    elif any(name in journal_name for name in jpe_names):
        return 'pink'
    
    return 'lightblue'

def visualize_citation_network(top_n=1000):
    """
    Visualize citation network for top N most cited papers.
    
    Args:
        top_n (int): Number of top cited papers to include in visualization
    """
    # Load the graph from GEXF file
    print("Loading citation network...")
    G = load_saved_graph(format='gexf')
    
    print("\nNetwork Statistics:")
    print(f"Number of nodes: {G.number_of_nodes()}")
    print(f"Number of edges: {G.number_of_edges()}")
    
    # Calculate some basic network metrics
    print("\nCalculating network metrics...")
    
    # In-degree and out-degree distributions
    in_degrees = [d for n, d in G.in_degree()]
    out_degrees = [d for n, d in G.out_degree()]
    
    print(f"Average in-degree: {sum(in_degrees)/len(in_degrees):.2f}")
    print(f"Average out-degree: {sum(out_degrees)/len(out_degrees):.2f}")
    
    # Find most cited papers (highest in-degree)
    most_cited = sorted(G.in_degree(), key=lambda x: x[1], reverse=True)[:10]
    print("\nTop 10 Most Cited Papers:")
    for doi, citations in most_cited:
        title = G.nodes[doi].get('title', 'No title')
        year = G.nodes[doi].get('year', 'No year')
        print(f"Citations: {citations}, Year: {year}")
        print(f"Title: {title}")
        print(f"DOI: {doi}")
        print()
    
    # Create subgraph of top N cited papers
    print(f"\nCreating visualization of top {top_n} cited papers...")
    top_nodes = [node for node, _ in sorted(G.in_degree(), key=lambda x: x[1], reverse=True)[:top_n]]
    subgraph = G.subgraph(top_nodes)
    
    plt.figure(figsize=(40, 40))  # Doubled figure size for more space
    
    # Calculate local citation counts (within the subgraph)
    local_citations = dict(subgraph.in_degree())
    max_local_citations = max(local_citations.values())
    
    # Create positions based on local citation counts
    print("Computing layout...")
    pos = {}
    for i, node in enumerate(subgraph.nodes()):
        radius = 1 - (local_citations[node] / max_local_citations) * 0.8
        angle = (i * 2 * 3.14159) / len(subgraph.nodes())
        x = radius * np.cos(angle)
        y = radius * np.sin(angle)
        pos[node] = np.array([x, y])
    
    # Scale node sizes based on global citation count (reduced size for density)
    node_sizes = [G.in_degree(node) * 10 for node in subgraph.nodes()]
    
    # Color nodes by journal
    node_colors = [get_journal_color(G.nodes[node].get('journal', '')) for node in subgraph.nodes()]
    
    # Draw nodes
    nx.draw_networkx_nodes(subgraph, pos, 
                          node_size=node_sizes,
                          node_color=node_colors,
                          alpha=0.6,
                          edgecolors='gray')
    
    # Draw edges with curved arrows (reduced alpha for density)
    print("Drawing edges...")
    nx.draw_networkx_edges(subgraph, pos, 
                          alpha=0.15,  # Reduced alpha
                          arrows=True,
                          arrowsize=5,  # Smaller arrows
                          edge_color='gray',
                          connectionstyle='arc3,rad=0.2')
    
    # Add wrapped labels
    print("Adding labels...")
    labels = {}
    for node in subgraph.nodes():
        title = G.nodes[node].get('title', 'No title')
        labels[node] = abbreviate_title(title)
    
    nx.draw_networkx_labels(subgraph, pos, 
                           labels,
                           font_size=4,  # Smaller font
                           font_weight='bold')
    
    plt.title(f"Top {top_n} Most Cited Papers\n(Most cited papers in center)")
    plt.axis('off')
    plt.margins(0.2)
    
    print("Saving visualization...")
    plt.savefig(f'saved_graphs/top_{top_n}_citations.png', 
                dpi=300, 
                bbox_inches='tight',
                format='png')
    print(f"Visualization saved as 'saved_graphs/top_{top_n}_citations.png'")

if __name__ == "__main__":
    # Create data directory if it doesn't exist
    Path("saved_graphs").mkdir(exist_ok=True)
    
    # Build the citation network
    G = build_citation_network()
    
    # Print some basic statistics
    print(f"Number of nodes: {G.number_of_nodes()}")
    print(f"Number of edges: {G.number_of_edges()}")
    print(f"Is directed: {nx.is_directed(G)}")
    
    # Additional debug info
    print("\nChecking node attributes...")
    all_attrs = set()
    for node, attrs in G.nodes(data=True):
        all_attrs.update(attrs.keys())
    print(f"All node attributes found: {all_attrs}")
    
    # Save the graph in multiple formats for flexibility
    print("\nAttempting to save in GraphML format...")
    nx.write_graphml(G, "saved_graphs/citation_network.graphml")
    
    print("Saving in GEXF format...")
    nx.write_gexf(G, "saved_graphs/citation_network.gexf")
    
    print("Saving in Pickle format...")
    with open("saved_graphs/citation_network.pickle", "wb") as f:
        pickle.dump(G, f)
    
    print("\nGraph saved in multiple formats in saved_graphs/:")
    print("- citation_network.graphml (for general use)")
    print("- citation_network.gexf (for visualization)")
    print("- citation_network.pickle (for Python use)")

    # Visualize the citation network with default 500 papers
    visualize_citation_network()

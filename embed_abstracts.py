from transformers import pipeline
from typing import List
import torch

def extract_topic_tags(abstract: str, num_tags: int = 5) -> List[str]:
    """
    Extract topic tags from an academic abstract using SciBERT.
    
    Args:
        abstract (str): The academic abstract text
        num_tags (int): Number of topic tags to extract (default: 5)
        
    Returns:
        List[str]: List of topic tags with their confidence scores
    """
    # Define candidate topics relevant for economics papers
    candidate_topics = [
        "monetary policy", "banking", "interest rates", "financial intermediation",
        "credit markets", "inflation", "macroeconomics", "financial stability",
        "bank lending", "deposit markets", "zero lower bound", "equity markets",
        "liquidity", "financial regulation", "credit supply", "bank capital",
        "monetary transmission", "financial institutions", "risk management",
        "market efficiency"
    ]
    
    # Initialize zero-shot classification pipeline with SciBERT
    classifier = pipeline(
        "zero-shot-classification",
        model="allenai/scibert_scivocab_uncased",
        device=0 if torch.cuda.is_available() else -1
    )
    
    # Classify abstract against candidate topics
    result = classifier(
        abstract,
        candidate_labels=candidate_topics,
        multi_label=True
    )
    
    # Get top N tags with their scores
    tags = [
        (label, score) 
        for label, score in zip(result['labels'], result['scores'])
    ]
    tags.sort(key=lambda x: x[1], reverse=True)
    
    return [tag[0] for tag in tags[:num_tags]]

# Example usage
if __name__ == "__main__":
    abstract = """I study how the secular decline in interest rates affects banks' intermediation spreads and credit supply. Following a permanent decrease in rates, bank lending may rise initially but contracts in the long run. As lower rates compress deposit spreads even well above the zero lower bound, banks' retained earnings, equity, and lending fall until loan spreads have risen enough to offset the reduction in deposit spreads. A higher inflation target can support bank lending at the cost of higher liquidity premia. I find support for the model's predictions in U.S. aggregate and bank-level data."""
    
    tags = extract_topic_tags(abstract)
    print("\nExtracted topics:")
    for i, tag in enumerate(tags, 1):
        print(f"{i}. {tag}")

from habanero import Crossref
import time
from datetime import datetime, timedelta
import csv
import pandas as pd

# Initialize Crossref API client
cr = Crossref(mailto="wangac@mit.edu")

# Define search parameters
issn = "0022-3808"  # ISSN for The Review of Financial Studies
start_date = datetime(2000, 1, 1)
end_date = datetime(2025, 3, 1)

# Store all articles
all_articles = []

# Function to get the first day of next quarter
def get_next_quarter(date):
    if date.month in [1, 2, 3]:
        return datetime(date.year, 4, 1)
    elif date.month in [4, 5, 6]:
        return datetime(date.year, 7, 1)
    elif date.month in [7, 8, 9]:
        return datetime(date.year, 10, 1)
    else:
        return datetime(date.year + 1, 1, 1)

# Query quarter by quarter
current_date = start_date
while current_date < end_date:
    next_date = min(get_next_quarter(current_date), end_date)  # Don't go past end_date
    
    from_date = current_date.strftime("%Y-%m-%d")
    until_date = next_date.strftime("%Y-%m-%d")
    
    print(f"\nQuerying period: {from_date} to {until_date}")
    
    try:
        results = cr.works(
            filter={
                "issn": issn,
                "from-pub-date": from_date,
                "until-pub-date": until_date
            },
            limit=100
        )
        
        # Extract articles with publication date
        quarter_articles = [
            (
                item["DOI"],
                item.get("title", [""])[0],
                item.get("published-print", {}).get("date-parts", [[""]])[0][0]
            )
            for item in results["message"]["items"]
        ]
        
        all_articles.extend(quarter_articles)
        print(f"Found {len(quarter_articles)} articles")
        
    except Exception as e:
        print(f"Error querying {from_date}: {str(e)}")
    
    time.sleep(0.25)  # Delay between requests
    current_date = next_date

# Remove duplicates while preserving order
seen = set()
unique_articles = []
for article in all_articles:
    if article[0] not in seen:  # Check DOI
        seen.add(article[0])
        unique_articles.append(article)

# Sort by DOI
unique_articles.sort(key=lambda x: x[0])

# Save to CSV
df = pd.DataFrame(unique_articles, columns=['DOI', 'Title', 'Published Date'])
df.to_csv('JPE_dois.csv', index=False)

# Print summary
print(f"\nCollection complete!")
print(f"Total unique articles found: {len(unique_articles)}")
print(f"Results saved to JPE_dois.csv")

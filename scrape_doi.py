from habanero import Crossref
from calendar import monthrange
from datetime import datetime
import time

# Initialize Crossref API client
cr = Crossref()

# Define search parameters
issn = "1465-7368"  # ISSN for The Review of Financial Studies
year = "2023"  # Replace with desired year

# Function to get last day of month
def get_last_day(year, month):
    return monthrange(int(year), month)[1]

# Store all articles info
all_articles = []

# Query each month
for month in range(1, 13):
    time.sleep(0.1)
    last_day = get_last_day(year, month)
    
    # Format dates with zero-padding for months 1-9
    from_date = f"{year}-{month:02d}-01"
    until_date = f"{year}-{month:02d}-{last_day}"
    
    print(f"\nQuerying {datetime.strptime(f'{month:02d}', '%m').strftime('%B')}...")
    
    results = cr.works(
        filter={
            "issn": issn,
            "from-pub-date": from_date,
            "until-pub-date": until_date
        },
        limit=50
    )
    
    # Add new articles to our list
    month_articles = [(item["DOI"], item.get("title", [""])[0]) for item in results["message"]["items"]]
    all_articles.extend(month_articles)
    print(f"Found {len(month_articles)} articles")

# Remove duplicates and sort by DOI
all_articles = list(set(all_articles))
all_articles.sort(key=lambda x: x[0])

# Print results
print(f"\nAll articles in The Review of Financial Studies, Year {year}:")
print(f"Total articles found: {len(all_articles)}")
for doi, title in all_articles:
    print(f"\nDOI: {doi}")
    print(f"Title: {title}")

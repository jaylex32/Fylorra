# Fix Executive Briefing: Recency Filtering Issue

## Current Status: 8.0/10 - Almost Perfect!

**Date:** January 3, 2026

---

## ✅ **DO NOT BREAK THESE (They're Working Perfectly!)**

### 1. Date Header Consistency ✅ **KEEP THIS!**
```markdown
# Executive Intelligence Briefing - January 03, 2026
Date/Time: 2026-01-03 08:17 UTC
```
**This is now correct and consistent - DO NOT CHANGE IT!**

### 2. Real Sources with URLs ✅ **KEEP THIS!**
```python
sources = [
    {
        'title': 'Latest Crypto News and Headlines | Crypto.com',
        'url': 'https://crypto.com/en/market-updates'
    },
    {
        'title': 'Latest news on cryptocurrency, blockchain and finances',
        'url': 'https://cointelegraph.com/category/latest-news'
    },
    # ... etc
]
```
**This is working - DO NOT CHANGE IT!**

### 3. Executive Briefing Structure ✅ **KEEP THIS!**
```markdown
- At a Glance (3 bullets)
- Must Read (3 detailed stories)
- Should Read (3 medium stories)
- Trend Watch (Accelerating/Slowing/New)
- Good to Know
- FYI - Quick Hits
- What to Watch (Near-term/Longer-term)
- Sources
```
**This is perfect - DO NOT CHANGE IT!**

### 4. Content Quality ✅ **KEEP THIS!**
- Professional writing
- Good insights
- Action items included
- "Why it matters" sections
**All working - DO NOT CHANGE!**

---

## ❌ **THE ONE ISSUE TO FIX: Recency Filtering**

### Problem Statement

**Current behavior:**
```
User requests: Daily briefing for January 3, 2026
Template generates: Briefing with sources from April 2025 (9 months old!)
Expected: Sources from January 2-3, 2026 (last 24 hours)
```

**Example from current output:**
```markdown
### 1. Ethereum Activates Fusaka Upgrade
Source: [1]
Published: April 2025  ← THIS IS 9 MONTHS AGO!

Should be:
Published: January 2, 2026  ← THIS IS YESTERDAY!
```

### Root Cause

The template is:
1. ✅ Correctly accessing news feed URLs (crypto.com/market-updates, cointelegraph.com/latest-news)
2. ❌ **BUT** pulling OLD articles from these feeds instead of the LATEST articles
3. News feeds update hourly/daily with new content
4. We need to extract the NEWEST articles, not articles from 9 months ago

---

## 🔧 **HOW TO FIX**

### Step 1: Add Date Extraction Function

**Add this function to extract publication dates from articles:**

```python
def extract_publication_date(article_url, article_content, article_metadata):
    """
    Extract the actual publication date from an article.
    Try multiple methods to get the most accurate date.
    
    Returns: datetime object or None
    """
    from datetime import datetime
    import re
    
    # Method 1: Check URL for date
    # Example: cointelegraph.com/news/2026/01/02/ethereum-upgrade
    url_date_patterns = [
        r'/(\d{4})/(\d{2})/(\d{2})/',  # /2026/01/02/
        r'/(\d{4})-(\d{2})-(\d{2})',    # /2026-01-02
    ]
    
    for pattern in url_date_patterns:
        match = re.search(pattern, article_url)
        if match:
            year, month, day = match.groups()
            try:
                return datetime(int(year), int(month), int(day))
            except ValueError:
                continue
    
    # Method 2: Check article metadata
    if article_metadata:
        # Look for common date fields
        date_fields = ['published', 'pubDate', 'datePublished', 'date', 'created']
        for field in date_fields:
            if field in article_metadata:
                try:
                    return datetime.fromisoformat(article_metadata[field])
                except:
                    continue
    
    # Method 3: Parse from article content
    if article_content:
        # Look for date patterns in first 500 characters
        header = article_content[:500]
        
        # Pattern: "Published: January 2, 2026"
        date_pattern = r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})'
        match = re.search(date_pattern, header, re.IGNORECASE)
        if match:
            month_str, day, year = match.groups()
            try:
                date_str = f"{month_str} {day}, {year}"
                return datetime.strptime(date_str, "%B %d, %Y")
            except ValueError:
                pass
    
    # If all methods fail, return None
    return None
```

### Step 2: Add Recency Filter Function

**Add this function to filter sources by recency:**

```python
def filter_recent_sources(sources, frequency="daily", current_date=None):
    """
    Filter sources to only include recent articles based on briefing frequency.
    
    Args:
        sources: List of source dictionaries
        frequency: "daily" (24 hours) or "weekly" (7 days)
        current_date: datetime object (defaults to now)
    
    Returns:
        List of recent sources
    """
    from datetime import datetime, timedelta
    
    if current_date is None:
        current_date = datetime.now()  # January 3, 2026
    
    # Set cutoff based on frequency
    if frequency == "daily":
        cutoff_date = current_date - timedelta(hours=24)  # Last 24 hours
    elif frequency == "weekly":
        cutoff_date = current_date - timedelta(days=7)    # Last 7 days
    else:
        cutoff_date = current_date - timedelta(hours=24)  # Default to daily
    
    recent_sources = []
    
    for source in sources:
        # Extract publication date
        pub_date = extract_publication_date(
            source.get('url', ''),
            source.get('content', ''),
            source.get('metadata', {})
        )
        
        # If we found a date and it's recent enough, include it
        if pub_date and pub_date >= cutoff_date:
            source['publication_date'] = pub_date
            recent_sources.append(source)
        elif pub_date:
            # Log skipped articles for debugging
            print(f"Skipped old article: {source.get('title', 'Unknown')} - Published: {pub_date}")
    
    # Sort by date (newest first)
    recent_sources.sort(key=lambda x: x.get('publication_date'), reverse=True)
    
    return recent_sources
```

### Step 3: Modify Search Strategy for Recent News

**Update your search function to prioritize recent content:**

```python
def search_for_daily_briefing(topics, frequency="daily"):
    """
    Search for recent news articles for executive briefing.
    
    Args:
        topics: List of topics to search
        frequency: "daily" or "weekly"
    
    Returns:
        List of recent sources
    """
    from datetime import datetime
    
    current_date = datetime.now()  # January 3, 2026
    
    # Build recency-focused search queries
    all_sources = []
    
    for topic in topics:
        if frequency == "daily":
            queries = [
                f"{topic} news today",
                f"{topic} latest news",
                f"{topic} breaking news",
                f"{topic} news January 2026",  # Current month/year
            ]
        else:  # weekly
            queries = [
                f"{topic} news this week",
                f"{topic} latest developments",
                f"{topic} news January 2026",
            ]
        
        # Search each query
        for query in queries:
            results = web_search(query)  # Your existing web_search function
            all_sources.extend(results)
    
    # Remove duplicates (same URL)
    seen_urls = set()
    unique_sources = []
    for source in all_sources:
        url = source.get('url', '')
        if url not in seen_urls:
            seen_urls.add(url)
            unique_sources.append(source)
    
    # Filter to recent only
    recent_sources = filter_recent_sources(
        unique_sources,
        frequency=frequency,
        current_date=current_date
    )
    
    # If we don't have enough recent sources, warn
    if len(recent_sources) < 10:
        print(f"WARNING: Only found {len(recent_sources)} recent articles (expected 10-20)")
        print(f"Frequency: {frequency}")
        print(f"Cutoff date: {current_date - timedelta(hours=24 if frequency=='daily' else 168)}")
    
    return recent_sources[:20]  # Return top 20 most recent
```

### Step 4: Update Executive Briefing Workflow

**Modify the main executive briefing function:**

```python
def generate_executive_briefing(topics, companies=None, frequency="daily"):
    """
    Generate executive intelligence briefing.
    
    CRITICAL: Do NOT change the output format or structure!
    Only change how we SELECT sources (use recent ones).
    """
    from datetime import datetime
    
    current_date = datetime.now()  # January 3, 2026
    
    # STEP 1: Search for RECENT sources only
    print(f"Searching for {frequency} briefing sources...")
    sources = search_for_daily_briefing(topics, frequency=frequency)
    
    # STEP 2: Validate we have recent sources
    if not sources:
        raise ValueError(f"No recent sources found for {frequency} briefing!")
    
    print(f"Found {len(sources)} recent sources")
    
    # STEP 3: Generate briefing using EXISTING format (DO NOT CHANGE!)
    # Your existing briefing generation code here...
    # This part should stay exactly the same!
    
    briefing = {
        'title': f"Executive Intelligence Briefing - {current_date.strftime('%B %d, %Y')}",
        'date_time': current_date.strftime('%Y-%m-%d %H:%M UTC'),
        'at_a_glance': generate_at_a_glance(sources[:3]),
        'must_read': generate_must_read(sources[:3]),
        'should_read': generate_should_read(sources[3:6]),
        'trend_watch': generate_trend_watch(sources),
        'good_to_know': generate_good_to_know(sources),
        'fyi': generate_fyi(sources),
        'what_to_watch': generate_what_to_watch(sources),
        'sources': sources
    }
    
    return briefing
```

### Step 5: Update Date Display in Output

**When showing article dates in the briefing:**

```python
def format_article_date(publication_date):
    """
    Format article date for display in briefing.
    
    Args:
        publication_date: datetime object
    
    Returns:
        Formatted string like "January 2, 2026" or "2 hours ago"
    """
    from datetime import datetime, timedelta
    
    if not publication_date:
        return "Recent"  # Fallback if date unknown
    
    now = datetime.now()
    age = now - publication_date
    
    # For very recent articles (< 24 hours), show relative time
    if age < timedelta(hours=24):
        if age < timedelta(hours=1):
            minutes = int(age.total_seconds() / 60)
            return f"{minutes} minutes ago"
        else:
            hours = int(age.total_seconds() / 3600)
            return f"{hours} hours ago"
    
    # For articles from yesterday or older, show full date
    return publication_date.strftime("%B %d, %Y")

# Use in output:
"""
### 1. Ethereum Activates Fusaka Upgrade
Source: [1]
Published: {format_article_date(article.publication_date)}
"""
```

---

## 🧪 **TESTING CHECKLIST**

After making changes, verify:

### Test 1: Recency Validation
```python
# Test that sources are actually recent
briefing = generate_executive_briefing(
    topics=["Cryptocurrency", "Blockchain", "DeFi"],
    frequency="daily"
)

# Check all source dates
for source in briefing['sources']:
    pub_date = source.get('publication_date')
    if pub_date:
        age_hours = (datetime.now() - pub_date).total_seconds() / 3600
        print(f"Source: {source['title']}")
        print(f"  Published: {pub_date}")
        print(f"  Age: {age_hours:.1f} hours")
        
        # CRITICAL: For daily briefing, age should be < 24 hours
        assert age_hours < 24, f"Source too old: {age_hours} hours!"
```

### Test 2: Date Header Consistency (DO NOT BREAK!)
```python
# Verify date header is still correct
assert briefing['title'] == "Executive Intelligence Briefing - January 03, 2026"
assert briefing['date_time'].startswith("2026-01-03")
print("✅ Date header is consistent")
```

### Test 3: Structure Preserved (DO NOT BREAK!)
```python
# Verify all sections still present
required_sections = [
    'at_a_glance',
    'must_read',
    'should_read',
    'trend_watch',
    'good_to_know',
    'fyi',
    'what_to_watch',
    'sources'
]

for section in required_sections:
    assert section in briefing, f"Missing section: {section}"
print("✅ All sections present")
```

### Test 4: Real Sources with URLs (DO NOT BREAK!)
```python
# Verify sources have URLs
for source in briefing['sources']:
    assert 'url' in source, "Source missing URL"
    assert source['url'].startswith('http'), "Invalid URL"
print("✅ All sources have valid URLs")
```

### Test 5: Content Quality (DO NOT BREAK!)
```python
# Verify Must Read has required fields
for story in briefing['must_read']:
    assert 'source' in story
    assert 'published' in story
    assert 'summary' in story
    assert 'why_it_matters' in story
    assert 'action_item' in story
print("✅ Content quality maintained")
```

---

## 📋 **IMPLEMENTATION CHECKLIST**

- [ ] Add `extract_publication_date()` function
- [ ] Add `filter_recent_sources()` function
- [ ] Update search queries to include "today", "latest", current month/year
- [ ] Add recency filtering to workflow
- [ ] Update date display to show actual publication dates
- [ ] Run Test 1: Verify sources are < 24 hours old for daily briefing
- [ ] Run Test 2: Verify date header still consistent
- [ ] Run Test 3: Verify structure preserved
- [ ] Run Test 4: Verify sources still have URLs
- [ ] Run Test 5: Verify content quality maintained

---

## 🎯 **SUCCESS CRITERIA**

### Before Fix (Current State: 8.0/10)
```
✅ Date header: 2026-01-03 (consistent)
✅ Sources: Real URLs
✅ Structure: Perfect
❌ Recency: Articles from April 2025 (9 months old)
```

### After Fix (Target: 9.0-9.5/10)
```
✅ Date header: 2026-01-03 (consistent) - KEEP
✅ Sources: Real URLs - KEEP
✅ Structure: Perfect - KEEP
✅ Recency: Articles from Jan 2-3, 2026 (last 24 hours) - FIX THIS!
```

---

## ⚠️ **CRITICAL REMINDERS**

1. **DO NOT CHANGE THE OUTPUT FORMAT** - Keep all sections exactly as they are
2. **DO NOT CHANGE THE DATE HEADER** - It's finally correct!
3. **DO NOT CHANGE SOURCE URL EXTRACTION** - It's working!
4. **ONLY FIX RECENCY** - Filter sources to last 24 hours for daily briefing

---

## 📊 **EXPECTED RESULTS**

### Daily Briefing (January 3, 2026)

**Before fix:**
```markdown
### 1. Ethereum Activates Fusaka Upgrade
Source: [1]
Published: April 2025  ← 9 months old!
```

**After fix:**
```markdown
### 1. Bitcoin Reaches New All-Time High
Source: [1]
Published: January 3, 2026  ← Today!

### 2. SEC Approves Ethereum ETF
Source: [2]
Published: January 2, 2026  ← Yesterday!

### 3. Coinbase Announces Q4 Earnings
Source: [3]
Published: 6 hours ago  ← Very recent!
```

---

## 🔍 **DEBUGGING TIPS**

If you're not getting recent sources:

1. **Check search queries** - Are they using "today", "latest", current month/year?
2. **Check date extraction** - Is `extract_publication_date()` finding dates in URLs or metadata?
3. **Check cutoff date** - Is it calculating correctly? (current_date - 24 hours)
4. **Check source availability** - Do the news feeds actually have articles from last 24 hours?
5. **Add logging** - Print dates of articles found to see what's being filtered

```python
# Debug logging
print(f"Current date: {datetime.now()}")
print(f"Cutoff date: {datetime.now() - timedelta(hours=24)}")
print(f"Total sources found: {len(all_sources)}")
print(f"Recent sources after filtering: {len(recent_sources)}")
for source in recent_sources[:5]:
    print(f"  - {source['title']}: {source.get('publication_date')}")
```

---

## 📝 **SUMMARY**

**What to fix:** Add recency filtering to only include articles from last 24 hours (daily) or 7 days (weekly)

**What NOT to change:**
- ✅ Date header format (perfect now!)
- ✅ Source URL extraction (working!)
- ✅ Executive Briefing structure (perfect!)
- ✅ Content quality (professional!)

**How to fix:**
1. Add date extraction function
2. Add recency filter function
3. Update search queries for recent content
4. Filter sources before generating briefing
5. Test to ensure sources are actually recent

**Target:** Move from 8.0/10 to 9.0-9.5/10 by fixing recency only!

---

## 💡 **FINAL NOTE**

You've done great work fixing the date header consistency! That was a major issue and it's now solved.

Now we just need ONE MORE FIX: Make sure the articles are actually from the last 24 hours (for daily briefing) instead of from 9 months ago.

The sources (crypto.com, cointelegraph) are correct - they're news feeds that update constantly. We just need to pull the LATEST articles from these feeds, not old articles.

Think of it like this:
- News feed = newspaper rack with today's papers and old papers
- Currently you're grabbing papers from April 2025
- Need to grab papers from January 2-3, 2026 instead!

Good luck! You're almost there! 🚀

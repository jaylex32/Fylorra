# New Workflow Templates Implementation Guide

## Overview

This document provides complete instructions for adding two new workflow templates to your automation system:

1. **Market Opportunity Analyzer** - Identify and evaluate new market opportunities
2. **Executive Intelligence Briefing** - Daily/weekly personalized intelligence digest

Both templates build on your existing **Research to Report** workflow (currently at 9.5/10 quality) and reuse much of the same infrastructure.

---

## Foundation: What to Reuse from Research to Report

### Core Components to Keep (Don't Rebuild):

✅ **Source Collection**
- 10 source collection with validation
- Source quality assessment
- Citation diversity logic
- Web search integration

✅ **Analysis Framework**
- Critical analysis structure
- Confidence scoring (80-90%, 60-75%, 40-55%)
- Dissenting perspectives
- "What We Don't Know" section
- Risk factors categorization

✅ **Output Quality**
- No boilerplate repetition
- Topic-appropriate content
- Complete structure
- Professional formatting

### What's Different for Each Template:

**Market Opportunity Analyzer:**
- Adds scoring/ranking system
- Adds financial modeling (market size, TAM/SAM/SOM)
- Adds competitive density assessment
- Adds go/no-go decision framework

**Executive Intelligence Briefing:**
- Adds recency weighting (last 24 hours/7 days)
- Adds personalization by user topics
- Adds scheduling/automation
- Shorter, digest format (500-1000 words vs. full report)
- Prioritization system (Need to Know vs. Good to Know)

---

# TEMPLATE 1: Market Opportunity Analyzer

## Purpose

Identify, evaluate, and rank new market opportunities using systematic scoring methodology.

**Business Value:**
- Prioritizes opportunities by potential ROI
- Reduces analysis time from days to minutes
- Provides quantitative decision framework
- Enables portfolio comparison

---

## Workflow Stages

### Stage 1: Market Discovery (Search & Collect)

**Purpose:** Find potential market opportunities

**Inputs:**
- Topic/industry (e.g., "AI healthcare applications")
- Geographic region (optional: "North America", "Global")
- Company context (optional: current capabilities, target customers)

**Process:**
```
Search Queries:
1. "{topic} market opportunities 2026"
2. "{topic} emerging markets"
3. "{topic} market gaps"
4. "{topic} growth segments"
5. "{topic} underserved markets"

Source Requirements:
- Minimum 7 sources
- Mix: market research (3), industry reports (2), news (2)
- Prioritize: authoritative market data (Gartner, IDC, McKinsey, etc.)
```

**Outputs:**
- List of 5-10 potential opportunities identified
- Market sizing data where available
- Growth trend indicators

---

### Stage 2: Opportunity Scoring (Quantitative Analysis)

**Purpose:** Score each opportunity across multiple dimensions

**Scoring Framework:**

```
Score each opportunity (0-10) across 5 dimensions:

1. Market Size (0-10)
   - 10: >$1B TAM
   - 7-9: $100M-$1B TAM
   - 4-6: $10M-$100M TAM
   - 1-3: <$10M TAM
   - 0: Unknown/too small

2. Growth Rate (0-10)
   - 10: >50% CAGR
   - 7-9: 20-50% CAGR
   - 4-6: 10-20% CAGR
   - 1-3: <10% CAGR
   - 0: Declining/flat

3. Competitive Intensity (0-10)
   - 10: No/minimal competition (blue ocean)
   - 7-9: Few competitors, fragmented
   - 4-6: Moderate competition
   - 1-3: Highly competitive
   - 0: Saturated market

4. Strategic Fit (0-10)
   - 10: Perfect fit with capabilities
   - 7-9: Strong fit, minor gaps
   - 4-6: Moderate fit, some new capabilities needed
   - 1-3: Weak fit, major gaps
   - 0: No fit

5. Barriers to Entry (0-10)
   - 10: Low barriers (easy to enter)
   - 7-9: Moderate barriers (surmountable)
   - 4-6: Significant barriers
   - 1-3: High barriers
   - 0: Prohibitive barriers

Overall Score: Average of 5 dimensions (0-10)
Weighted Score (optional): User can set weights for each dimension
```

**Calculation:**
```python
def calculate_opportunity_score(opportunity, weights=None):
    """
    Calculate opportunity score across 5 dimensions
    
    Args:
        opportunity: Opportunity data with scoring inputs
        weights: Optional dict of dimension weights (default: equal weight)
    
    Returns:
        dict with scores and overall rating
    """
    
    # Default equal weights
    if weights is None:
        weights = {
            'market_size': 0.20,
            'growth_rate': 0.25,
            'competitive_intensity': 0.20,
            'strategic_fit': 0.25,
            'barriers_to_entry': 0.10
        }
    
    # Extract scores for each dimension (0-10)
    scores = {
        'market_size': score_market_size(opportunity),
        'growth_rate': score_growth_rate(opportunity),
        'competitive_intensity': score_competitive_intensity(opportunity),
        'strategic_fit': score_strategic_fit(opportunity),
        'barriers_to_entry': score_barriers_to_entry(opportunity)
    }
    
    # Calculate weighted overall score
    overall_score = sum(scores[dim] * weights[dim] for dim in scores)
    
    # Convert to rating
    if overall_score >= 8.0:
        rating = "Excellent"
        recommendation = "High Priority - Pursue Immediately"
    elif overall_score >= 6.5:
        rating = "Good"
        recommendation = "Medium Priority - Evaluate Further"
    elif overall_score >= 5.0:
        rating = "Fair"
        recommendation = "Low Priority - Monitor"
    else:
        rating = "Poor"
        recommendation = "Do Not Pursue"
    
    return {
        'scores': scores,
        'overall_score': round(overall_score, 1),
        'rating': rating,
        'recommendation': recommendation,
        'confidence': assess_scoring_confidence(opportunity)
    }
```

**Output:**
- Scored opportunity list
- Ranking by overall score
- Confidence level for each score

---

### Stage 3: Feasibility Analysis (Detailed Assessment)

**Purpose:** Deep-dive into top 3-5 opportunities

**For each top opportunity, analyze:**

1. **Market Dynamics**
   - Customer segments and needs
   - Key buying criteria
   - Market trends and drivers
   - Potential market share (realistic estimate)

2. **Competitive Landscape**
   - Main competitors and their positioning
   - Competitive advantages/disadvantages
   - White space opportunities

3. **Required Capabilities**
   - Technical requirements
   - Operational requirements
   - Partnership/talent needs
   - Investment required

4. **Go-to-Market Strategy**
   - Distribution channels
   - Marketing approach
   - Sales model
   - Pricing strategy

5. **Financial Projections**
   - TAM/SAM/SOM estimates
   - Revenue potential (Year 1-3)
   - Investment required
   - Break-even timeline
   - ROI projection

6. **Risks & Barriers**
   - Technical risks
   - Market risks
   - Competitive risks
   - Regulatory risks
   - Execution risks

**Confidence Assessment:**
```
For each finding, assess confidence:

High Confidence (80-90%):
- Market size backed by multiple reputable sources
- Clear customer pain points validated
- Known competitive landscape

Medium Confidence (60-75%):
- Market size from single source or estimated
- Customer needs inferred from trends
- Emerging competitive landscape

Low Confidence (40-55%):
- Market size extrapolated or speculative
- Assumed customer needs
- Unclear competitive dynamics
```

---

### Stage 4: Decision Framework (Recommendations)

**Purpose:** Generate actionable go/no-go recommendations

**Output Format:**

```markdown
## Opportunity Ranking

### Tier 1: High Priority (Score 8.0+)

**Opportunity: [Name]**
- Overall Score: 8.5/10
- Market Size: $500M TAM, 35% CAGR
- Strategic Fit: Excellent - leverages existing capabilities
- Competition: Moderate - 3 main players, fragmented market

**Recommendation:** PURSUE - High Priority
- Expected Revenue (Y3): $15M-$25M
- Investment Required: $2M-$3M
- Time to Market: 12-18 months
- Break-even: Month 24

**Next Steps:**
1. Conduct customer discovery interviews (30 prospects)
2. Develop MVP prototype (3 months)
3. Pilot with 3-5 customers (6 months)
4. Scale if validation successful

**Key Risks:**
- Regulatory approval timeline uncertain (Medium Risk)
- Technical feasibility of key feature unproven (Medium Risk)

---

### Tier 2: Medium Priority (Score 6.5-7.9)

[Same format for medium priority opportunities]

---

### Tier 3: Monitor (Score 5.0-6.4)

[Same format - watch but don't pursue yet]

---

### Do Not Pursue (Score <5.0)

[Brief explanation of why rejected]
```

---

## Configuration Options

**User-Configurable Settings:**

```python
market_opportunity_config = {
    # Search parameters
    'topic': str,  # Required: "AI healthcare applications"
    'geography': str,  # Optional: "North America", "Global", "Europe"
    'timeframe': str,  # Default: "2026", Options: "2026", "2025-2027", "Next 5 years"
    
    # Source requirements
    'min_sources': int,  # Default: 7, Min: 5, Max: 15
    'source_types': list,  # Default: ['market_research', 'industry_reports', 'news']
    
    # Scoring weights (must sum to 1.0)
    'scoring_weights': {
        'market_size': float,  # Default: 0.20
        'growth_rate': float,  # Default: 0.25
        'competitive_intensity': float,  # Default: 0.20
        'strategic_fit': float,  # Default: 0.25
        'barriers_to_entry': float,  # Default: 0.10
    },
    
    # Company context (for strategic fit scoring)
    'company_context': {
        'current_capabilities': list,  # e.g., ["AI/ML", "Cloud infrastructure", "Healthcare domain"]
        'target_customers': list,  # e.g., ["Hospitals", "Health insurers"]
        'geographic_presence': list,  # e.g., ["North America", "Europe"]
    },
    
    # Analysis depth
    'top_n_opportunities': int,  # Default: 3, Options: 1-5 (how many to deep-dive)
    'include_financial_projections': bool,  # Default: True
    
    # Output format
    'output_format': str,  # Default: 'markdown', Options: 'markdown', 'pdf', 'docx'
    'include_visualization': bool,  # Default: True (opportunity comparison chart)
}
```

---

## Expected Output Structure

```markdown
# Market Opportunity Analysis: [Topic]

## Executive Summary

Analysis of [N] opportunities in [topic] space. Top opportunity: [name] 
with score of [X]/10 and projected revenue potential of $[Y]M by year 3. 
High confidence in market size and growth, medium confidence in competitive 
dynamics. Recommend pursuing top [N] opportunities with phased approach.

## Opportunity Overview

| Opportunity | Score | Market Size | Growth | Competition | Fit | Barriers | Recommendation |
|-------------|-------|-------------|--------|-------------|-----|----------|----------------|
| Opp A       | 8.5   | $500M       | 35%    | Moderate    | 9/10| Low      | HIGH PRIORITY  |
| Opp B       | 7.2   | $200M       | 45%    | High        | 7/10| Medium   | MEDIUM         |
| Opp C       | 6.8   | $800M       | 15%    | Very High   | 8/10| High     | MONITOR        |

## Detailed Analysis

### Opportunity 1: [Name]
**Overall Score: 8.5/10 - Excellent**

**Market Dynamics:**
[Market size, growth drivers, customer segments, trends]

**Competitive Landscape:**
[Key competitors, positioning, white space]

**Strategic Fit:**
[How it aligns with capabilities, what's needed]

**Financial Projections:**
- TAM: $500M
- SAM: $200M (addressable with current capabilities)
- SOM: $15-25M by Year 3 (realistic market share: 7-12%)
- Investment Required: $2-3M
- Break-even: Month 24
- ROI: 250% by Year 3

**Go-to-Market Strategy:**
[Distribution, marketing, sales, pricing]

**Risks:**
[Technical, market, competitive, regulatory, execution risks]

**Confidence Assessment:**
- Market Size: High (80%) - Multiple reputable sources
- Growth Rate: High (85%) - Historical data + analyst consensus
- Competitive Dynamics: Medium (65%) - Emerging landscape, some uncertainty
- Financial Projections: Medium (60%) - Based on assumptions about market share

**Recommendation: PURSUE - High Priority**

Next Steps:
1. Customer discovery (Month 1-2)
2. MVP development (Month 3-5)
3. Pilot program (Month 6-11)
4. Scale decision (Month 12)

---

[Repeat for each opportunity in Tier 1, then Tier 2, then Tier 3]

## Critical Analysis

**Assumptions:**
- Market growth continues at projected rates
- Regulatory environment remains stable
- Competitive landscape doesn't shift dramatically
- Company can acquire necessary capabilities

**Dependencies:**
- Access to target customer segments
- Ability to develop/acquire key technologies
- Sufficient investment capital
- Talent acquisition success

**Risks:**
- Market sizing estimates based on limited data
- Competitive responses not fully predictable
- Technology feasibility assumptions
- Regulatory changes

## What We Don't Know

- Exact customer willingness to pay
- Specific competitor product roadmaps
- Regulatory timeline and requirements
- Long-term market saturation point
- Technology development costs precision

## Recommendations by Priority

### High Priority - Pursue Now
[List with specific next steps]

### Medium Priority - Evaluate Further
[List with evaluation criteria]

### Low Priority - Monitor
[List with monitoring triggers]

## Sources

[1-15 sources with URLs]
```

---

## Implementation Checklist

### Phase 1: Core Functionality

- [ ] Add market opportunity template to template list
- [ ] Implement 4-stage workflow (Discovery → Scoring → Feasibility → Decision)
- [ ] Create scoring framework (5 dimensions, 0-10 scale)
- [ ] Add opportunity ranking logic
- [ ] Generate opportunity comparison table
- [ ] Reuse Research to Report analysis components

### Phase 2: Scoring Intelligence

- [ ] Implement market size scoring (extract TAM/SAM from sources)
- [ ] Implement growth rate scoring (extract CAGR, growth trends)
- [ ] Implement competitive intensity scoring (count competitors, assess concentration)
- [ ] Implement strategic fit scoring (match against company context)
- [ ] Implement barriers scoring (identify regulatory, technical, capital barriers)

### Phase 3: Financial Modeling

- [ ] Add TAM/SAM/SOM calculation
- [ ] Add revenue projection (Year 1-3)
- [ ] Add investment requirement estimation
- [ ] Add break-even calculation
- [ ] Add ROI projection

### Phase 4: Configuration & UI

- [ ] Add user configuration form (topic, weights, company context)
- [ ] Add output format options (MD, PDF, DOCX)
- [ ] Add opportunity comparison visualization
- [ ] Add export functionality

---

# TEMPLATE 2: Executive Intelligence Briefing

## Purpose

Generate personalized daily/weekly intelligence digests focused on user's topics of interest.

**Business Value:**
- Saves 1-2 hours daily reading news/reports
- Personalized to user interests
- Highlights actionable insights
- Tracks changes over time

---

## Workflow Stages

### Stage 1: Content Aggregation (Personalized Search)

**Purpose:** Gather recent, relevant content based on user interests

**Inputs:**
```python
user_profile = {
    'topics': [
        'AI regulation',
        'Electric vehicles', 
        'Semiconductor industry'
    ],
    'companies': [
        'NVIDIA',
        'Tesla',
        'OpenAI'
    ],
    'competitors': [
        'AMD',
        'Rivian',
        'Google DeepMind'
    ],
    'geographic_focus': [
        'North America',
        'Europe'
    ],
    'update_frequency': 'daily',  # or 'weekly'
    'briefing_time': '06:00 EST'
}
```

**Process:**
```
For DAILY briefing:
  Timeframe: Last 24 hours
  Recency weight: High (80% weight to <12 hrs old)

For WEEKLY briefing:
  Timeframe: Last 7 days
  Recency weight: Medium (60% weight to <3 days old)

Search Strategy:
1. For each topic:
   - "{topic} news today" (or "this week")
   - "{topic} latest developments"
   - "{topic} breaking news"

2. For each company:
   - "{company} news today"
   - "{company} announcement"
   - "{company} earnings" (if relevant timeframe)

3. For each competitor:
   - "{competitor} product launch"
   - "{competitor} partnership"

Source Requirements:
- Minimum: 10 sources
- Maximum: 20 sources (avoid information overload)
- Prioritize: Authoritative news (WSJ, Reuters, Bloomberg), industry publications
- Recency: All sources must be from timeframe (24 hrs or 7 days)
```

**Deduplication:**
- If multiple sources cover same story, keep most authoritative
- Flag related stories as "Also covered by [X], [Y]"

---

### Stage 2: Relevance Scoring & Prioritization

**Purpose:** Rank content by importance to user

**Scoring Criteria:**

```python
def calculate_relevance_score(article, user_profile):
    """
    Score article relevance (0-100)
    
    Factors:
    1. Topic match (0-40 points)
    2. Recency (0-20 points)
    3. Source authority (0-15 points)
    4. Impact/significance (0-15 points)
    5. Actionability (0-10 points)
    """
    
    score = 0
    
    # Topic match (0-40)
    topic_matches = count_topic_matches(article, user_profile['topics'])
    company_matches = count_company_matches(article, user_profile['companies'])
    competitor_matches = count_competitor_matches(article, user_profile['competitors'])
    
    score += min(40, topic_matches * 15 + company_matches * 20 + competitor_matches * 10)
    
    # Recency (0-20)
    hours_old = calculate_hours_since_publication(article)
    if hours_old < 6:
        score += 20
    elif hours_old < 12:
        score += 15
    elif hours_old < 24:
        score += 10
    else:
        score += 5
    
    # Source authority (0-15)
    if article.source in ['WSJ', 'Reuters', 'Bloomberg', 'FT']:
        score += 15
    elif article.source in ['TechCrunch', 'VentureBeat', 'The Verge']:
        score += 10
    else:
        score += 5
    
    # Impact/significance (0-15)
    significance_keywords = ['acquisition', 'merger', 'partnership', 'regulation', 'breakthrough', 'lawsuit']
    if any(keyword in article.title.lower() for keyword in significance_keywords):
        score += 15
    
    # Actionability (0-10)
    if contains_data_or_statistics(article):
        score += 5
    if contains_forward_looking_statements(article):
        score += 5
    
    return min(100, score)


def categorize_by_priority(articles):
    """
    Categorize articles into priority tiers
    """
    prioritized = {
        'must_read': [],      # Score 80-100
        'should_read': [],    # Score 60-79
        'good_to_know': [],   # Score 40-59
        'fyi': []            # Score <40
    }
    
    for article in articles:
        score = article.relevance_score
        if score >= 80:
            prioritized['must_read'].append(article)
        elif score >= 60:
            prioritized['should_read'].append(article)
        elif score >= 40:
            prioritized['good_to_know'].append(article)
        else:
            prioritized['fyi'].append(article)
    
    return prioritized
```

---

### Stage 3: Synthesis & Insight Generation

**Purpose:** Summarize key developments and extract insights

**For Each Priority Category:**

1. **At a Glance (Top 3 bullets)**
   - One-sentence summaries of most important developments
   - Focus on "what happened" and "why it matters"

2. **Key Themes**
   - Identify connections across stories
   - Spot emerging trends
   - Note contradictions or debates

3. **Detailed Summaries (Top 5-7 stories)**
   - 2-3 paragraph summary
   - Key facts and data points
   - "So what?" - implications for user
   - Action items (if applicable)

4. **Trend Watch**
   - What's accelerating
   - What's slowing down
   - What's new

**Synthesis Guidelines:**
```
For each story:
- Lead with the most important fact
- Include specific numbers, names, dates
- Explain "why this matters" to user
- Keep summaries under 150 words

For trends:
- Look for patterns across 3+ stories
- Note sentiment shifts (optimistic → cautious, etc.)
- Identify potential opportunities or threats
```

---

### Stage 4: Briefing Generation

**Purpose:** Format as email-ready digest

**Output Format:**

```markdown
# Your Daily Intelligence Briefing
[Date] | Prepared at [Time]

---

## 📍 At a Glance

The top 3 things you need to know today:

1. **[Topic]**: [One-sentence summary with key fact] - [Why it matters]
2. **[Topic]**: [One-sentence summary with key fact] - [Why it matters]
3. **[Topic]**: [One-sentence summary with key fact] - [Why it matters]

---

## 🔥 Must Read

### [Story Title]
**Source:** [Publication] | **Published:** [X hours ago]

[2-3 paragraph summary with key facts, numbers, quotes]

**Why This Matters:** [Implications for your interests]

**Action Item:** [If applicable - what you should do/consider]

[Link to full article]

---

### [Story Title 2]
[Same format]

---

## 📊 Should Read

### [Story Title]
**Source:** [Publication] | **Published:** [X hours ago]

[1-2 paragraph summary]

**Key Takeaway:** [Main point in one sentence]

[Link to full article]

---

[2-3 more stories in this category]

---

## 📈 Trend Watch

**What's Accelerating:**
- [Trend 1]: [Brief explanation with examples from stories]
- [Trend 2]: [Brief explanation]

**What's Slowing:**
- [Trend 1]: [Brief explanation]

**What's New:**
- [New development]: [Brief explanation]

---

## 💡 Good to Know

**[Topic Category]:**
- [Brief bullet summary of story 1] [[Link]]
- [Brief bullet summary of story 2] [[Link]]
- [Brief bullet summary of story 3] [[Link]]

**[Topic Category 2]:**
- [Brief bullet summaries]

---

## 🔔 FYI - Quick Hits

- [One-line summary] [[Link]]
- [One-line summary] [[Link]]
- [One-line summary] [[Link]]

---

## 📅 What to Watch

**This Week:**
- [Upcoming event/deadline based on today's news]
- [Expected announcement/decision]

**Longer Term:**
- [Developing situation to monitor]

---

**Next Briefing:** [Tomorrow at 6:00 AM EST / Next Monday at 6:00 AM EST]

---

_Sources: [Number] articles from [Number] publications including [Top 3 sources]_
_Topics covered: [User's topics]_
```

---

## Configuration Options

**User-Configurable Settings:**

```python
executive_briefing_config = {
    # Personalization
    'topics': list,  # Required: ["AI regulation", "Electric vehicles"]
    'companies': list,  # Optional: ["NVIDIA", "Tesla"]
    'competitors': list,  # Optional: ["AMD", "Rivian"]
    'geographic_focus': list,  # Optional: ["North America", "Europe"]
    
    # Scheduling
    'frequency': str,  # Required: 'daily' or 'weekly'
    'delivery_time': str,  # Required: "06:00 EST", "08:00 PST"
    'delivery_days': list,  # For weekly: ["Monday"], For daily: all weekdays
    
    # Content preferences
    'min_articles': int,  # Default: 10, Min: 5, Max: 20
    'max_articles': int,  # Default: 20, Min: 10, Max: 30
    'include_fyi_section': bool,  # Default: True
    'include_trend_watch': bool,  # Default: True
    'detail_level': str,  # Default: 'standard', Options: 'brief', 'standard', 'detailed'
    
    # Filtering
    'exclude_topics': list,  # Optional: topics to filter out
    'minimum_source_quality': str,  # Default: 'medium', Options: 'any', 'medium', 'high'
    'language': str,  # Default: 'en', Options: 'en', 'es', 'fr', etc.
    
    # Output format
    'output_format': str,  # Default: 'email_html', Options: 'email_html', 'markdown', 'pdf'
    'word_count_target': int,  # Default: 1000, Options: 500-2000
}
```

---

## Expected Output Structure

**Daily Briefing (500-1000 words):**
- At a Glance: 3 bullets
- Must Read: 2-3 stories (detailed)
- Should Read: 2-3 stories (medium detail)
- Trend Watch: 1 section
- Good to Know: 3-5 bullets
- FYI: 3-5 one-liners
- What to Watch: 2-3 forward-looking items

**Weekly Briefing (1000-1500 words):**
- At a Glance: 5 bullets (week's top stories)
- Must Read: 3-5 stories (detailed)
- Should Read: 3-5 stories (medium detail)
- Trend Watch: 1 section (week's patterns)
- Good to Know: 5-10 bullets
- Week Ahead: Upcoming events/decisions

---

## Implementation Checklist

### Phase 1: Core Functionality

- [ ] Add executive briefing template to template list
- [ ] Implement 4-stage workflow (Aggregation → Scoring → Synthesis → Generation)
- [ ] Add recency filtering (last 24 hrs / 7 days)
- [ ] Add relevance scoring (0-100)
- [ ] Add priority categorization (Must/Should/Good/FYI)
- [ ] Generate briefing in markdown format

### Phase 2: Personalization

- [ ] Add user profile configuration (topics, companies, competitors)
- [ ] Implement topic matching algorithm
- [ ] Implement company/competitor tracking
- [ ] Add geographic filtering
- [ ] Add exclude topics filter

### Phase 3: Intelligence Features

- [ ] Implement trend detection (patterns across stories)
- [ ] Add "What to Watch" forward-looking section
- [ ] Add "Why This Matters" insight generation
- [ ] Identify action items from stories
- [ ] Add change detection (new this period vs. continuing stories)

### Phase 4: Scheduling & Delivery

- [ ] Add scheduling system (daily/weekly at specified time)
- [ ] Add email delivery integration
- [ ] Add delivery confirmation
- [ ] Add "skip today" option
- [ ] Store briefing history

### Phase 5: Polish

- [ ] Add HTML email template (for email delivery)
- [ ] Add briefing statistics (sources used, topics covered)
- [ ] Add feedback mechanism (helpful/not helpful buttons)
- [ ] Add briefing archive/search

---

## Key Differences from Research to Report

### What's Similar:
- Source collection methodology
- Citation practices
- Quality validation
- Professional formatting

### What's Different:

**Executive Briefing:**
- Shorter output (500-1000 words vs. 3000+)
- Recency focus (last 24 hrs/7 days only)
- Multiple short items vs. one deep topic
- Prioritization/categorization (Must/Should/Good/FYI)
- Scheduled/automated execution
- Personalized to user interests
- No deep analysis (summaries only)
- No confidence scoring (news reporting, not predictions)
- No dissenting perspectives (just reporting what happened)

**Market Opportunity:**
- Quantitative scoring (0-10 across 5 dimensions)
- Financial modeling (TAM/SAM/SOM, ROI)
- Ranking/comparison across opportunities
- Go/no-go decision framework
- Longer, more analytical
- Still has confidence scoring (for projections)
- Still has dissenting perspectives (different market views)

---

## Code Structure Suggestions

### Template Architecture

```python
# Base class (existing Research to Report)
class ResearchWorkflowTemplate:
    def __init__(self, config):
        self.config = config
        self.sources = []
        self.report = {}
    
    def collect_sources(self):
        """Collect and validate sources"""
        pass
    
    def analyze(self):
        """Perform analysis"""
        pass
    
    def generate_report(self):
        """Generate formatted output"""
        pass


# Market Opportunity Analyzer (extends base)
class MarketOpportunityTemplate(ResearchWorkflowTemplate):
    def __init__(self, config):
        super().__init__(config)
        self.opportunities = []
        self.scores = {}
    
    def discover_opportunities(self):
        """Stage 1: Find opportunities"""
        self.collect_sources()
        self.opportunities = self.extract_opportunities_from_sources()
        return self.opportunities
    
    def score_opportunities(self):
        """Stage 2: Score each opportunity"""
        for opp in self.opportunities:
            self.scores[opp.name] = self.calculate_opportunity_score(opp)
        
        # Rank by score
        self.opportunities.sort(key=lambda x: self.scores[x.name]['overall_score'], reverse=True)
        return self.scores
    
    def analyze_top_opportunities(self):
        """Stage 3: Deep dive on top N"""
        top_n = self.config.get('top_n_opportunities', 3)
        top_opps = self.opportunities[:top_n]
        
        for opp in top_opps:
            opp.detailed_analysis = self.perform_feasibility_analysis(opp)
        
        return top_opps
    
    def generate_recommendations(self):
        """Stage 4: Decision framework"""
        recommendations = {
            'tier_1_high_priority': [],
            'tier_2_medium_priority': [],
            'tier_3_monitor': [],
            'do_not_pursue': []
        }
        
        for opp in self.opportunities:
            score = self.scores[opp.name]['overall_score']
            if score >= 8.0:
                recommendations['tier_1_high_priority'].append(opp)
            elif score >= 6.5:
                recommendations['tier_2_medium_priority'].append(opp)
            elif score >= 5.0:
                recommendations['tier_3_monitor'].append(opp)
            else:
                recommendations['do_not_pursue'].append(opp)
        
        return recommendations
    
    def generate_report(self):
        """Generate complete market opportunity report"""
        # Reuse base class formatting
        report = super().generate_report()
        
        # Add opportunity-specific sections
        report['opportunity_ranking'] = self.format_opportunity_table()
        report['detailed_analysis'] = self.format_opportunity_details()
        report['recommendations'] = self.format_recommendations()
        
        return report


# Executive Briefing (extends base)
class ExecutiveBriefingTemplate(ResearchWorkflowTemplate):
    def __init__(self, config):
        super().__init__(config)
        self.articles = []
        self.prioritized = {}
    
    def aggregate_content(self):
        """Stage 1: Personalized search"""
        # Apply recency filter
        timeframe = 24 if self.config['frequency'] == 'daily' else 168  # hours
        
        # Search based on user interests
        for topic in self.config['topics']:
            sources = self.search_recent_news(topic, timeframe)
            self.sources.extend(sources)
        
        for company in self.config.get('companies', []):
            sources = self.search_recent_news(company, timeframe)
            self.sources.extend(sources)
        
        # Deduplicate
        self.sources = self.deduplicate_sources(self.sources)
        
        return self.sources
    
    def prioritize_content(self):
        """Stage 2: Score and categorize"""
        for source in self.sources:
            source.relevance_score = self.calculate_relevance_score(source)
        
        # Sort by relevance
        self.sources.sort(key=lambda x: x.relevance_score, reverse=True)
        
        # Categorize
        self.prioritized = {
            'must_read': [s for s in self.sources if s.relevance_score >= 80],
            'should_read': [s for s in self.sources if 60 <= s.relevance_score < 80],
            'good_to_know': [s for s in self.sources if 40 <= s.relevance_score < 60],
            'fyi': [s for s in self.sources if s.relevance_score < 40]
        }
        
        return self.prioritized
    
    def synthesize_insights(self):
        """Stage 3: Generate summaries and trends"""
        insights = {
            'at_a_glance': self.generate_top_bullets(3),
            'detailed_summaries': self.generate_summaries(self.prioritized['must_read']),
            'trends': self.detect_trends(self.sources),
            'what_to_watch': self.generate_forward_looking()
        }
        
        return insights
    
    def generate_briefing(self):
        """Stage 4: Format as briefing"""
        briefing = self.format_briefing_template()
        
        # Populate sections
        briefing['at_a_glance'] = self.insights['at_a_glance']
        briefing['must_read'] = self.format_detailed_stories(self.prioritized['must_read'][:3])
        briefing['should_read'] = self.format_medium_stories(self.prioritized['should_read'][:3])
        briefing['trend_watch'] = self.insights['trends']
        briefing['good_to_know'] = self.format_bullet_stories(self.prioritized['good_to_know'][:5])
        briefing['fyi'] = self.format_one_liners(self.prioritized['fyi'][:5])
        briefing['what_to_watch'] = self.insights['what_to_watch']
        
        return briefing
```

---

## Testing & Validation

### Test Cases for Market Opportunity Analyzer

**Test 1: Scoring Accuracy**
```
Input: Topic "AI in healthcare"
Expected: 
- Find 5-10 opportunities
- Score each across 5 dimensions
- Overall scores between 0-10
- Top opportunity score > 7.0
```

**Test 2: Ranking Logic**
```
Input: Multiple opportunities with different scores
Expected:
- Opportunities ranked highest to lowest
- Tier 1 (>8.0), Tier 2 (6.5-8.0), Tier 3 (5.0-6.5)
- Correct categorization
```

**Test 3: Financial Modeling**
```
Input: Opportunity with market data
Expected:
- TAM/SAM/SOM calculated
- Revenue projections (Y1-Y3)
- Break-even timeline
- ROI estimate
```

### Test Cases for Executive Briefing

**Test 1: Recency Filtering**
```
Input: Daily briefing, topics ["AI", "EVs"]
Expected:
- All sources from last 24 hours
- No sources older than 24 hours
- Sources sorted by recency
```

**Test 2: Relevance Scoring**
```
Input: Articles on user's topics vs. unrelated topics
Expected:
- User's topics score 60-100
- Unrelated topics score <40
- Articles mentioning user's companies score higher
```

**Test 3: Prioritization**
```
Input: 20 articles with varied relevance
Expected:
- Must Read: 2-3 highest scored (>80)
- Should Read: 2-3 medium scored (60-79)
- Good to Know: 3-5 lower scored (40-59)
- FYI: Remaining (<40)
```

**Test 4: Briefing Length**
```
Input: Daily briefing with standard detail level
Expected:
- Total word count: 800-1200 words
- At a Glance: <100 words
- Must Read stories: 150-200 words each
- Should Read stories: 100-150 words each
```

---

## Deployment Steps

### Step 1: Add Templates to UI

```python
# In your template list
templates = [
    {
        'id': 'research_to_report',
        'name': 'Research to Report',
        'description': 'Generate professional research reports with 10 sources, confidence scoring, and critical analysis',
        'category': 'Research & Analysis',
        'stages': ['Research', 'Writing', 'Validation', 'Export'],
        'icon': '📊'
    },
    {
        'id': 'market_opportunity',  # NEW
        'name': 'Market Opportunity Analyzer',
        'description': 'Identify and rank market opportunities with quantitative scoring and financial projections',
        'category': 'Strategic Planning',
        'stages': ['Discovery', 'Scoring', 'Analysis', 'Recommendations'],
        'icon': '📈'
    },
    {
        'id': 'executive_briefing',  # NEW
        'name': 'Executive Intelligence Briefing',
        'description': 'Daily/weekly personalized intelligence digest with prioritized news and insights',
        'category': 'Monitoring & Alerts',
        'stages': ['Aggregation', 'Prioritization', 'Synthesis', 'Generation'],
        'icon': '📰'
    }
]
```

### Step 2: Configuration Forms

**Market Opportunity Analyzer Form:**
```
Fields:
- Topic/Industry (text input, required)
- Geography (dropdown: Global, North America, Europe, Asia, etc.)
- Company Capabilities (tags input, optional)
- Target Customers (tags input, optional)
- Scoring Weights (sliders, default: equal weight)
- Top N for Deep Dive (number, default: 3, range: 1-5)
- Output Format (dropdown: Markdown, PDF, DOCX)
```

**Executive Briefing Form:**
```
Fields:
- Topics (tags input, required)
- Companies to Track (tags input, optional)
- Competitors to Track (tags input, optional)
- Frequency (radio: Daily, Weekly)
- Delivery Time (time picker, default: 06:00)
- Detail Level (dropdown: Brief, Standard, Detailed)
- Output Format (dropdown: Email HTML, Markdown, PDF)
```

### Step 3: Test Each Template

1. Run Market Opportunity Analyzer on "AI in healthcare"
2. Verify scoring logic works
3. Check financial projections generate
4. Verify output format

5. Run Executive Briefing on test topics
6. Verify recency filtering works
7. Check prioritization logic
8. Verify briefing format

### Step 4: Production Deployment

- [ ] Deploy templates to production
- [ ] Set up scheduling for Executive Briefing
- [ ] Set up email delivery (if applicable)
- [ ] Create user documentation
- [ ] Monitor initial usage

---

## Success Criteria

### Market Opportunity Analyzer

✅ Finds 5-10 opportunities per topic
✅ Scores each opportunity across 5 dimensions
✅ Ranks opportunities correctly by overall score
✅ Generates financial projections (TAM/SAM/SOM, ROI)
✅ Produces tiered recommendations (High/Medium/Low priority)
✅ Maintains 9.0+ quality score (same standards as Research to Report)
✅ Complete output in <3 minutes

### Executive Briefing

✅ Collects 10-20 recent articles (last 24 hrs or 7 days)
✅ Scores relevance accurately (user topics score higher)
✅ Categorizes into Must/Should/Good/FYI correctly
✅ Generates briefing in 500-1000 words (daily) or 1000-1500 (weekly)
✅ Includes trend detection
✅ Includes forward-looking "What to Watch"
✅ Deliverable via email on schedule
✅ Complete generation in <2 minutes

---

## Summary

You now have complete instructions to implement:

1. **Market Opportunity Analyzer** - Scores and ranks opportunities with financial modeling
2. **Executive Intelligence Briefing** - Personalized daily/weekly intelligence digest

Both templates:
- Build on your Research to Report foundation (9.5/10 quality)
- Reuse source collection, analysis, and formatting infrastructure
- Add template-specific features (scoring, prioritization, scheduling)
- Maintain professional quality standards

**Estimated implementation time:**
- Market Opportunity Analyzer: 3-5 days
- Executive Intelligence Briefing: 2-4 days

**Total: 5-9 days for both templates**

Good luck with the implementation! 🚀

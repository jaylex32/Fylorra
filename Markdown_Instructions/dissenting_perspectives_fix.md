# Critical Fix: Dissenting Perspectives Logic + Minor Enhancements

## Overview

**Current Status:** Your workflow is performing excellently (8.5/10)!

**What's Working Well (DO NOT CHANGE):**
- ✅ Confidence percentages restored (80-85%, 70-75%, 65%)
- ✅ Boilerplate repetition eliminated
- ✅ Topic adaptation working well
- ✅ 10 sources consistently found
- ✅ All sections unique and relevant
- ✅ Complete structure with no truncation

**What Needs Fixing:**
- ❌ **CRITICAL**: Dissenting Perspectives logic is broken
- ⚠️ **MINOR**: Ethics section could be more specific

**IMPORTANT:** The fixes below are surgical - they target ONLY the broken parts while preserving everything that works.

---

## Priority 1: Fix Dissenting Perspectives Logic (CRITICAL)

### The Problem

**Current Output (Broken):**
```markdown
Dissenting Perspectives

EV Adoption in North America
• Mainstream: Sales down 1% in 2025 [2]
• Alternative: Sales UP 1% in 2025 [2]  ← Just negated the stat

EV Adoption in Europe
• Mainstream: Sales UP 33% [2]
• Alternative: Sales DOWN 33% [2]  ← Just negated the stat

EV Adoption in China
• Mainstream: China 62% of global sales [2]
• Alternative: China 62% of global sales [2]  ← IDENTICAL!
```

**What's wrong:**
1. "Alternative" views are just mechanically negating statistics (up→down)
2. Not finding actual dissenting perspectives from sources
3. China section has identical text for both views (copy-paste error)
4. These aren't real alternative viewpoints - just contradictory numbers

### What It Should Look Like

**Correct Output:**
```markdown
Dissenting Perspectives

EV Adoption Timeline
• Mainstream: 2026 is the "tipping point" for mass EV adoption, 
  driven by cost parity and infrastructure expansion [3]
• Alternative: Transition will take until 2030 or beyond; 
  infrastructure and cost barriers remain significant [8, 10]

Battery Technology Readiness
• Mainstream: Solid-state batteries will be mainstream by 2026, 
  enabling 800-1,000 km range [1]
• Alternative: Solid-state commercialization likely delayed 
  to 2028-2030 due to manufacturing challenges [6]

Infrastructure Adequacy
• Mainstream: Charging infrastructure is scaling adequately 
  to meet demand with 200,000+ ports in U.S. [3]
• Alternative: Infrastructure remains a critical bottleneck; 
  deployment is uneven and insufficient for mass adoption [8, 10]

Consumer Readiness
• Mainstream: 60% of consumers are leaning toward EVs, 
  showing strong market preference [1]
• Alternative: Consumer hesitation remains high due to 
  range anxiety, charging access, and upfront costs [8, 10]
```

**Notice the difference:**
- ✅ Each perspective comes from different sources
- ✅ Both are legitimate viewpoints found in research
- ✅ One is optimistic, one is cautious/skeptical
- ✅ No mechanical negation of statistics

---

## Root Cause Analysis

### Current Logic (What's Happening Now)

```python
# BROKEN APPROACH (what seems to be happening):
def generate_dissenting_perspectives(topic, sources):
    # Find a statistic in sources
    stat = find_statistic(sources)  # e.g., "Sales down 1%"
    
    # Mechanically negate it
    mainstream = stat
    alternative = negate_statistic(stat)  # "Sales UP 1%"
    
    # Return both
    return {
        'mainstream': mainstream,
        'alternative': alternative  # ❌ This is just negation, not a real perspective
    }
```

**Why this fails:**
- Negating a statistic doesn't create an alternative viewpoint
- It creates a contradictory claim from the same source
- Results in nonsensical "perspectives"

---

## Solution: Correct Implementation

### Step 1: Search for Contrarian Sources

```python
def find_dissenting_perspectives(topic, sources):
    """
    Find genuine alternative viewpoints by searching for contrarian sources
    and identifying actual debates in the literature
    """
    
    # Step 1: Identify key claims from mainstream sources
    mainstream_claims = extract_major_claims(sources)
    
    # Step 2: Search for contrarian perspectives
    contrarian_queries = generate_contrarian_queries(topic)
    contrarian_sources = search_for_contrarian_views(contrarian_queries)
    
    # Step 3: Match mainstream claims with genuine alternatives
    perspectives = match_perspectives(mainstream_claims, contrarian_sources, sources)
    
    return perspectives


def generate_contrarian_queries(topic):
    """
    Generate search queries to find skeptical/cautious perspectives
    """
    contrarian_keywords = [
        "challenges",
        "barriers", 
        "obstacles",
        "slower than expected",
        "overhyped",
        "skeptical",
        "limitations",
        "concerns",
        "criticism",
        "problems"
    ]
    
    queries = []
    for keyword in contrarian_keywords:
        queries.append(f"{topic} {keyword}")
    
    return queries[:3]  # Use top 3 to avoid too many searches


def extract_major_claims(sources):
    """
    Identify the key optimistic/mainstream claims in the topic
    """
    claims = []
    
    # Look for forward-looking, optimistic statements
    optimistic_markers = [
        "will accelerate",
        "expected to",
        "projected to",
        "is poised to",
        "tipping point",
        "mainstream by",
        "ready by"
    ]
    
    for source in sources:
        for marker in optimistic_markers:
            if marker in source.content.lower():
                # Extract the claim
                claim = extract_claim_around_marker(source, marker)
                claims.append({
                    'text': claim,
                    'source': source,
                    'type': 'optimistic'
                })
    
    return claims


def match_perspectives(mainstream_claims, contrarian_sources, all_sources):
    """
    Match mainstream claims with genuine alternative viewpoints
    """
    perspectives = []
    
    # Group claims by theme
    themes = categorize_claims_by_theme(mainstream_claims)
    # e.g., {'timeline': [...], 'technology': [...], 'infrastructure': [...]}
    
    for theme, claims in themes.items():
        # Find the strongest mainstream claim for this theme
        mainstream = select_representative_claim(claims)
        
        # Find contrarian view on same theme
        alternative = find_contrarian_view_for_theme(
            theme, 
            contrarian_sources, 
            all_sources
        )
        
        if mainstream and alternative:
            perspectives.append({
                'theme': theme,
                'mainstream': mainstream,
                'alternative': alternative
            })
    
    return perspectives


def find_contrarian_view_for_theme(theme, contrarian_sources, all_sources):
    """
    Find an actual skeptical/cautious viewpoint on the theme
    """
    # Search both contrarian sources AND main sources
    # (sometimes main sources include caveats/limitations)
    
    all_search_sources = contrarian_sources + all_sources
    
    cautious_markers = [
        "however",
        "but",
        "despite",
        "challenges remain",
        "barriers include",
        "not yet",
        "unlikely",
        "may not",
        "slower than",
        "delayed",
        "obstacles"
    ]
    
    for source in all_search_sources:
        if theme_keyword_in_source(theme, source):
            for marker in cautious_markers:
                if marker in source.content.lower():
                    # Extract the cautious/skeptical claim
                    claim = extract_claim_around_marker(source, marker)
                    if is_genuinely_contrarian(claim, theme):
                        return {
                            'text': claim,
                            'source': source,
                            'type': 'cautious'
                        }
    
    return None


def is_genuinely_contrarian(claim, theme):
    """
    Verify this is an actual alternative perspective, not just a negation
    """
    # Check if claim contains substantive reasoning
    substantive_markers = [
        "because",
        "due to",
        "given",
        "since",
        "as",
        "challenges include",
        "barriers are",
        "limitations"
    ]
    
    has_reasoning = any(marker in claim.lower() for marker in substantive_markers)
    
    # Check it's not just a negated statistic
    is_just_negation = is_statistical_negation(claim)
    
    return has_reasoning and not is_just_negation


def is_statistical_negation(claim):
    """
    Detect if this is just a negated statistic (which we want to avoid)
    """
    # Pattern: "up X%" vs "down X%" with same number
    # Pattern: "will" vs "will not" with no reasoning
    
    statistical_patterns = [
        r'\b\d+%\b',  # Has a percentage
        r'\bup\b.*\bdown\b',  # Contains both up and down
        r'\bwill\b.*\bwill not\b'  # Simple negation
    ]
    
    for pattern in statistical_patterns:
        if re.search(pattern, claim.lower()):
            # Check if it's ONLY a negation with no reasoning
            if len(claim.split()) < 15:  # Very short = likely just negation
                return True
    
    return False
```

---

## Implementation Guide

### Step-by-Step Integration

**IMPORTANT:** Only modify the dissenting perspectives generation. Do NOT change:
- Source collection logic (working perfectly)
- Confidence scoring (fixed and working)
- Risk factors generation (fixed and working)
- Any other sections

### Phase 1: Add Contrarian Source Search (New Function)

```python
def collect_contrarian_sources(topic):
    """
    Search specifically for skeptical/cautious perspectives on the topic
    
    This is IN ADDITION to regular source collection
    """
    contrarian_queries = [
        f"{topic} challenges",
        f"{topic} barriers",
        f"{topic} limitations"
    ]
    
    contrarian_sources = []
    
    for query in contrarian_queries:
        results = web_search(query)
        contrarian_sources.extend(results[:2])  # Take top 2 from each query
    
    # Remove duplicates
    unique_contrarian = deduplicate_sources(contrarian_sources)
    
    return unique_contrarian[:3]  # Return top 3 contrarian sources
```

### Phase 2: Update Dissenting Perspectives Generation

```python
def generate_dissenting_perspectives_section(topic, main_sources):
    """
    Generate dissenting perspectives by finding genuine alternative viewpoints
    
    REPLACES the current broken logic
    """
    
    # Collect contrarian sources (in addition to main sources)
    contrarian_sources = collect_contrarian_sources(topic)
    
    # Combine for perspective matching
    all_sources_for_perspectives = main_sources + contrarian_sources
    
    # Extract mainstream (optimistic) claims from main sources
    mainstream_claims = extract_optimistic_claims(main_sources)
    
    # Find genuine alternatives (from contrarian sources OR caveats in main sources)
    perspectives = []
    
    for claim in mainstream_claims[:4]:  # Top 4 themes
        theme = identify_theme(claim)
        
        # Find a contrarian view on the same theme
        alternative = find_alternative_view(
            theme=theme,
            mainstream_claim=claim,
            sources=all_sources_for_perspectives
        )
        
        if alternative:
            perspectives.append({
                'theme': format_theme_name(theme),
                'mainstream': {
                    'text': claim['text'],
                    'source': claim['source_citation']
                },
                'alternative': {
                    'text': alternative['text'],
                    'source': alternative['source_citation']
                }
            })
    
    return format_perspectives_section(perspectives)


def extract_optimistic_claims(sources):
    """
    Find forward-looking, optimistic claims in sources
    """
    optimistic_indicators = [
        "will accelerate",
        "expected to",
        "projected to",
        "poised to",
        "tipping point",
        "by 2026",
        "ready by",
        "mainstream"
    ]
    
    claims = []
    
    for source in sources:
        content = source.get('content', '')
        
        for indicator in optimistic_indicators:
            if indicator in content.lower():
                # Extract sentence containing this indicator
                claim_text = extract_sentence_with_phrase(content, indicator)
                
                if claim_text and len(claim_text.split()) > 10:  # Substantive claim
                    claims.append({
                        'text': claim_text,
                        'source_citation': source.get('citation', '[?]'),
                        'theme': infer_theme(claim_text)
                    })
    
    return claims


def find_alternative_view(theme, mainstream_claim, sources):
    """
    Find a genuine alternative perspective on the same theme
    """
    cautious_indicators = [
        "however",
        "but",
        "challenges",
        "barriers",
        "obstacles",
        "limitations",
        "concerns",
        "slower",
        "delayed",
        "not yet",
        "unlikely"
    ]
    
    theme_keywords = get_theme_keywords(theme)
    
    for source in sources:
        content = source.get('content', '')
        
        # Check if this source discusses the same theme
        discusses_theme = any(keyword in content.lower() for keyword in theme_keywords)
        
        if discusses_theme:
            # Look for cautious/skeptical statements
            for indicator in cautious_indicators:
                if indicator in content.lower():
                    alt_text = extract_sentence_with_phrase(content, indicator)
                    
                    # Verify it's substantive and not just statistical negation
                    if alt_text and is_substantive_alternative(alt_text, mainstream_claim['text']):
                        return {
                            'text': alt_text,
                            'source_citation': source.get('citation', '[?]')
                        }
    
    return None


def is_substantive_alternative(alternative_text, mainstream_text):
    """
    Check if the alternative is genuinely different (not just negation)
    """
    # Must have reasoning words
    reasoning_words = ['because', 'due to', 'given', 'since', 'as', 'while']
    has_reasoning = any(word in alternative_text.lower() for word in reasoning_words)
    
    # Must not be too similar to mainstream
    similarity = calculate_text_similarity(alternative_text, mainstream_text)
    
    # Must not just negate a statistic
    is_negation = is_simple_statistical_negation(alternative_text, mainstream_text)
    
    return has_reasoning and similarity < 0.5 and not is_negation


def is_simple_statistical_negation(text1, text2):
    """
    Detect if text2 is just text1 with "up" changed to "down" or similar
    """
    # Extract numbers from both
    numbers1 = re.findall(r'\d+', text1)
    numbers2 = re.findall(r'\d+', text2)
    
    # If they have the same numbers but opposite directions (up/down)
    if numbers1 == numbers2:
        has_up_down = ('up' in text1.lower() and 'down' in text2.lower()) or \
                      ('down' in text1.lower() and 'up' in text2.lower())
        if has_up_down:
            return True
    
    return False


def get_theme_keywords(theme):
    """
    Get keywords to identify if a source discusses a theme
    """
    theme_keyword_map = {
        'timeline': ['2026', '2030', 'years', 'decade', 'timeline', 'when'],
        'technology': ['battery', 'charging', 'range', 'solid-state', 'technology'],
        'infrastructure': ['charging stations', 'infrastructure', 'grid', 'ports'],
        'consumer': ['adoption', 'consumers', 'buyers', 'demand', 'preference'],
        'cost': ['price', 'cost', 'affordable', 'expensive', 'cheap'],
        'policy': ['regulation', 'policy', 'government', 'mandate', 'incentive']
    }
    
    return theme_keyword_map.get(theme, [theme])


def infer_theme(claim_text):
    """
    Determine which theme this claim relates to
    """
    claim_lower = claim_text.lower()
    
    if any(word in claim_lower for word in ['2026', '2030', 'tipping point', 'timeline']):
        return 'timeline'
    elif any(word in claim_lower for word in ['battery', 'solid-state', 'charging', 'range']):
        return 'technology'
    elif any(word in claim_lower for word in ['infrastructure', 'charging stations', 'grid']):
        return 'infrastructure'
    elif any(word in claim_lower for word in ['consumer', 'adoption', 'buyers', 'demand']):
        return 'consumer'
    elif any(word in claim_lower for word in ['cost', 'price', 'affordable']):
        return 'cost'
    elif any(word in claim_lower for word in ['policy', 'regulation', 'government']):
        return 'policy'
    else:
        return 'general'


def format_perspectives_section(perspectives):
    """
    Format the perspectives for the report
    """
    if not perspectives:
        return "No significant dissenting perspectives found in sources."
    
    output = ""
    
    for p in perspectives:
        output += f"\n### {p['theme']}\n\n"
        output += f"**Mainstream View:**\n"
        output += f"{p['mainstream']['text']} {p['mainstream']['source']}\n\n"
        output += f"**Alternative View:**\n"
        output += f"{p['alternative']['text']} {p['alternative']['source']}\n\n"
    
    return output
```

---

## Testing the Fix

### Test Cases

**Run these tests to verify the fix works:**

```python
def test_dissenting_perspectives():
    """
    Test that dissenting perspectives are genuine alternatives, not negations
    """
    
    # Test Case 1: Should NOT accept statistical negation
    mainstream = "EV sales up 33% in Europe"
    alternative_bad = "EV sales down 33% in Europe"
    
    assert is_simple_statistical_negation(mainstream, alternative_bad) == True
    print("✓ Test 1 passed: Rejects statistical negation")
    
    # Test Case 2: Should accept substantive alternative
    mainstream = "EVs will reach cost parity with ICE vehicles by 2026"
    alternative_good = "Cost parity unlikely before 2028 due to battery supply chain constraints"
    
    assert is_substantive_alternative(alternative_good, mainstream) == True
    print("✓ Test 2 passed: Accepts substantive alternative")
    
    # Test Case 3: Verify contrarian sources are found
    topic = "electric vehicle adoption 2026"
    contrarian_sources = collect_contrarian_sources(topic)
    
    assert len(contrarian_sources) > 0
    print(f"✓ Test 3 passed: Found {len(contrarian_sources)} contrarian sources")
    
    # Test Case 4: Verify perspectives have different sources
    perspectives = generate_dissenting_perspectives_section(topic, main_sources)
    
    for p in perspectives:
        mainstream_source = p['mainstream']['source']
        alternative_source = p['alternative']['source']
        
        # Should not be identical
        assert mainstream_source != alternative_source or \
               p['mainstream']['text'] != p['alternative']['text']
    
    print("✓ Test 4 passed: Perspectives have different sources/content")
    
    print("\n✅ All tests passed!")
```

---

## Expected Output After Fix

### Before (Broken):
```markdown
Dissenting Perspectives

EV Adoption in North America
• Mainstream: Sales down 1% in 2025 [2]
• Alternative: Sales UP 1% in 2025 [2]  ❌
```

### After (Fixed):
```markdown
Dissenting Perspectives

### EV Adoption Timeline

**Mainstream View:**
2026 is projected as the "tipping point" where EVs become 
mainstream due to cost parity and infrastructure expansion [3]

**Alternative View:**
Significant barriers remain including charging infrastructure 
gaps and range limitations; mass adoption more likely 2028-2030 [8, 10]

### Battery Technology Readiness

**Mainstream View:**
Solid-state batteries will enable 800-1,000 km range and become 
commercially available by 2026 [1]

**Alternative View:**
Solid-state battery commercialization faces manufacturing 
challenges and is unlikely before 2028 [6]

### Infrastructure Adequacy

**Mainstream View:**
Charging infrastructure is scaling adequately with 200,000+ 
public ports in the U.S. and plans for ultra-fast hubs [3]

**Alternative View:**
Infrastructure deployment remains uneven and insufficient; 
rural areas severely underserved; grid capacity concerns [8, 10]
```

---

## Priority 2: Enhance Ethics Section (Optional)

### Current Output (Weak):
```markdown
Ethics
Ethics are not a major concern for EV adoption, with most 
sources focusing on technological advancements and policy 
support [1, 3]. Ethical considerations such as supply chain 
transparency and labor practices are emerging but are not 
currently a primary barrier.
```

### Enhanced Output (Better):

```markdown
Ethics

While technological and economic factors dominate EV discussions, 
several ethical concerns warrant attention:

**Supply Chain Ethics:**
• Cobalt mining in Democratic Republic of Congo involves 
  significant human rights concerns, including child labor
• Lithium extraction in Chile and Argentina raises water 
  rights issues affecting indigenous communities

**Environmental Justice:**
• EV benefits (air quality, climate) accrue primarily to 
  wealthy consumers who can afford EVs
• Environmental costs (mining, battery production) often 
  borne by communities in developing nations

**Labor Transition:**
• Traditional automotive jobs may be displaced by EV 
  manufacturing shift
• Need for "just transition" programs for affected workers

**Recycling and End-of-Life:**
• Battery recycling infrastructure still underdeveloped
• Questions about long-term disposal and environmental impact

These ethical considerations are emerging as important factors 
but have not yet significantly slowed EV adoption [1, 3].
```

### Implementation (Optional Enhancement)

```python
def generate_ethics_section(topic, sources):
    """
    Generate topic-specific ethics content
    """
    
    # Detect topic category
    topic_lower = topic.lower()
    
    if any(word in topic_lower for word in ['vehicle', 'ev', 'electric car', 'automotive']):
        return generate_ev_ethics_section(sources)
    
    elif any(word in topic_lower for word in ['health', 'medical', 'drug', 'cannabis', 'marijuana']):
        return generate_health_ethics_section(sources)
    
    elif any(word in topic_lower for word in ['ai', 'artificial intelligence', 'machine learning']):
        return generate_ai_ethics_section(sources)
    
    else:
        return generate_general_ethics_section(topic, sources)


def generate_ev_ethics_section(sources):
    """
    EV-specific ethics content
    """
    return """
While technological and economic factors dominate EV discussions, 
several ethical concerns warrant attention:

**Supply Chain Ethics:**
• Cobalt mining involves human rights concerns in producing regions
• Lithium extraction raises indigenous land and water rights issues

**Environmental Justice:**
• EV benefits accrue primarily to consumers who can afford them
• Environmental costs of mining often borne by developing nations

**Labor Transition:**
• Traditional automotive jobs may be displaced
• Need for just transition programs for affected workers

**Recycling and End-of-Life:**
• Battery recycling infrastructure still developing
• Long-term environmental impact questions remain

These considerations are emerging but have not yet significantly 
impacted adoption decisions.
    """
```

**NOTE:** This is optional. The current ethics section is acceptable, just could be deeper.

---

## Implementation Checklist

### Critical (Must Implement):

- [ ] Add `collect_contrarian_sources()` function
- [ ] Replace dissenting perspectives generation with new logic
- [ ] Add `is_simple_statistical_negation()` check
- [ ] Add `is_substantive_alternative()` validation
- [ ] Test with EV topic to verify fix works
- [ ] Test with AI trends topic to verify no regression
- [ ] Test with marijuana topic to verify consistency

### Optional (Nice to Have):

- [ ] Add topic-specific ethics section enhancement
- [ ] Add more granular confidence scores (82% vs 80-85%)
- [ ] Add source quality tier assessment to reports

---

## Testing Plan

### Phase 1: Verify Fix on EV Topic

```bash
# Re-run EV topic with fixed code
topic = "Electric Vehicle Adoption Projections for 2026"
report = generate_report(topic)

# Check dissenting perspectives section
perspectives = report.sections['dissenting_perspectives']

# Verify:
assert 'up' and 'down' with same number NOT in perspectives
assert perspectives contains reasoning words
assert perspectives has different sources for mainstream vs alternative
```

### Phase 2: Regression Test on Previous Topics

```bash
# Test on AI trends (Report 8)
report_ai = generate_report("AI Trends 2026")
assert report_ai has valid dissenting perspectives

# Test on marijuana (Report 9)  
report_mj = generate_report("Marijuana Health Effects")
assert report_mj has valid dissenting perspectives
```

### Phase 3: Test on New Topic

```bash
# Test on completely new topic
report_new = generate_report("Social Media Regulation")
assert report_new has valid dissenting perspectives
```

---

## What NOT to Change

**CRITICAL:** Do not modify these working components:

❌ **DO NOT CHANGE:**
- Source collection logic (10 sources working perfectly)
- Confidence scoring format (percentages restored and working)
- Risk factors generation (boilerplate eliminated, working well)
- Challenges & Considerations sections (adapted well to topics)
- Recommendations tiering (working correctly)
- Any core report structure

✅ **ONLY CHANGE:**
- Dissenting perspectives generation logic
- (Optional) Ethics section content for specific topics

---

## Success Criteria

### After implementing this fix, verify:

✅ **Dissenting Perspectives Section:**
- No statistical negations (up 33% vs down 33%)
- Each perspective has substantive reasoning
- Mainstream and alternative views cite different sources or different parts of sources
- Perspectives represent genuine debates in the literature
- No identical mainstream/alternative text

✅ **No Regressions:**
- Confidence scores still have percentages (80-85%, etc.)
- No boilerplate repetition anywhere
- All 10 sources still collected
- All sections still complete
- Report quality maintained or improved

✅ **Overall Quality:**
- Reports remain 8.5-9.5/10 quality
- Fix elevates EV report from 8.5 to 9.0/10
- Consistent quality across all topics

---

## Rollback Plan

If the fix causes problems:

```python
# Keep old code commented out as backup:

# OLD CODE (BROKEN but safe):
# def generate_dissenting_perspectives_old(topic, sources):
#     ... old logic ...

# NEW CODE (FIXED):
def generate_dissenting_perspectives(topic, sources):
    try:
        # New logic here
        return new_perspectives
    except Exception as e:
        # If new logic fails, fall back to old
        logger.warning(f"Dissenting perspectives fix failed: {e}")
        return generate_dissenting_perspectives_old(topic, sources)
```

---

## Timeline

**Estimated Implementation Time:**
- Phase 1 (Critical fix): 2-3 hours
- Phase 2 (Testing): 1 hour
- Phase 3 (Optional ethics): 30 minutes

**Total:** 3-4 hours for complete implementation and testing

---

## Questions or Issues?

If you encounter problems:

1. **Test the individual functions first:**
   - `collect_contrarian_sources()` - does it find sources?
   - `is_simple_statistical_negation()` - does it detect negations?
   - `is_substantive_alternative()` - does it validate alternatives?

2. **Check the logs:**
   - Are contrarian sources being found?
   - Are themes being identified correctly?
   - Are alternatives being matched to mainstream claims?

3. **Compare before/after:**
   - Run same topic before and after fix
   - Verify dissenting perspectives improve
   - Ensure no other sections break

---

## Bottom Line

**This is a surgical fix:**
- Targets ONLY the broken dissenting perspectives logic
- Preserves all working improvements (confidence %, no boilerplate, etc.)
- Should elevate reports from 8.5/10 to 9.0/10
- Low risk of breaking existing functionality

**The fix works by:**
1. Searching for actual contrarian sources (not just negating stats)
2. Matching genuine alternative viewpoints to mainstream claims
3. Validating that alternatives have reasoning (not just negation)
4. Ensuring different sources or substantive differences

**Expected result:**
```
Current: Mainstream: up 33%, Alternative: down 33% ❌
Fixed: Meaningful debate between optimistic and skeptical views ✅
```

Good luck with the implementation! The workflow is already excellent - this fix will make it even better! 🚀

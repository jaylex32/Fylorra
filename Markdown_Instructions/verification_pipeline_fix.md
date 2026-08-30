# Verification Pipeline Fix: Handling Predictions vs Facts

## Issue Overview

The current verification pipeline is flagging **all predictions as "unverified"** because it's treating future predictions like factual claims. This is causing false positives in the validation step.

### Current Behavior (❌ Incorrect):
```
Issues:
- Unverified claims:
  - Agentic AI will evolve into digital coworkers...
  - Quantum computing is projected to outperform...
  - Continual learning will become a standard feature...
  - World models will enable AI systems...
  [etc.]
```

**Why this is wrong**: These are all forward-looking predictions that CANNOT be verified as true/false (they're about the future). What we CAN verify is that a credible source made these predictions.

### Expected Behavior (✅ Correct):
```
## Verification Report

### ✅ Properly Verified Claims (5)
- "Continual learning will become a standard feature..."
  - Type: PREDICTION
  - Source: VentureBeat [2] ✓
  - Attribution: Clear ✓
  - Caveats: Present in report ✓

### ⚠️ Claims Needing Attribution (2)
- "Agentic AI will evolve into digital coworkers..."
  - Type: PREDICTION
  - Found in: Microsoft [3]
  - Fix: Add "According to Microsoft [3]," to make attribution explicit

### ❌ Unverifiable Claims (0)
- None found (all predictions trace back to sources)
```

---

## The Core Problem

### What the Pipeline is Currently Doing:
```python
# WRONG APPROACH:
def verify_claim(claim):
    search_results = web_search(claim)
    if claim_text_found_in_results(search_results):
        return "VERIFIED"
    else:
        return "UNVERIFIED"  # ❌ False positive for predictions!
```

This fails because:
- ❌ You can't verify "Quantum computing WILL outperform in 2026" (it's 2026, this hasn't happened yet)
- ❌ Searching the web won't confirm future events
- ❌ All forward-looking predictions get flagged as "unverified"

### What the Pipeline SHOULD Do:
```python
# CORRECT APPROACH:
def verify_claim(claim, sources):
    # Step 1: Classify claim type
    if is_prediction(claim):
        return verify_prediction_attribution(claim, sources)
    elif is_historical_fact(claim):
        return verify_historical_fact(claim)
    elif is_current_state(claim):
        return verify_current_state(claim)
```

For predictions, we verify:
- ✅ A credible source made this prediction
- ✅ The prediction is accurately represented from source
- ✅ Source caveats are included in report
- ❌ NOT whether the prediction will come true (impossible to verify)

---

## Solution: Enhanced Verification Logic

### Step 1: Classify Claim Types

```python
def classify_claim_type(claim):
    """
    Determine if claim is a fact, prediction, or trend
    """
    
    # Prediction markers
    prediction_markers = [
        'will', 'is projected to', 'is expected to', 
        'may', 'could', 'might', 'would',
        'by 2026', 'in 2026', 'by 2027',
        'are predicted to', 'is forecasted to',
        'likely to', 'poised to', 'set to'
    ]
    
    # Historical fact markers
    fact_markers = [
        'has achieved', 'was', 'were',
        'have been', 'had', 'did',
        'currently is', 'exists', 'exists today'
    ]
    
    # Trend markers
    trend_markers = [
        'is increasing', 'is growing', 'is declining',
        'has been rising', 'adoption is accelerating'
    ]
    
    claim_lower = claim.lower()
    
    # Check for prediction markers
    if any(marker in claim_lower for marker in prediction_markers):
        return "PREDICTION"
    
    # Check for historical fact markers
    elif any(marker in claim_lower for marker in fact_markers):
        return "HISTORICAL_FACT"
    
    # Check for trend markers
    elif any(marker in claim_lower for marker in trend_markers):
        return "TREND"
    
    # Default to general claim
    else:
        return "GENERAL"

# Examples:
classify_claim_type("Quantum computing will outperform in 2026")
# Returns: "PREDICTION"

classify_claim_type("Google achieved quantum supremacy in 2019")
# Returns: "HISTORICAL_FACT"

classify_claim_type("AI adoption is accelerating across industries")
# Returns: "TREND"
```

### Step 2: Verify Based on Claim Type

```python
def verify_claim(claim, sources):
    """
    Enhanced verification that handles different claim types appropriately
    """
    
    # Classify the claim
    claim_type = classify_claim_type(claim)
    
    # Route to appropriate verification method
    if claim_type == "PREDICTION":
        return verify_prediction_attribution(claim, sources)
    
    elif claim_type == "HISTORICAL_FACT":
        return verify_historical_fact(claim)
    
    elif claim_type == "TREND":
        return verify_trend_evidence(claim, sources)
    
    else:
        return verify_general_claim(claim, sources)
```

### Step 3: Prediction-Specific Verification

```python
def verify_prediction_attribution(claim, sources):
    """
    For predictions, verify that the SOURCE made this prediction,
    not that the prediction is true (which is impossible for future events)
    """
    
    verification = {
        'claim': claim,
        'type': 'PREDICTION',
        'verification_criteria': 'Source attribution, not truth value'
    }
    
    # Step 3.1: Check if any source made this prediction
    source_match = find_prediction_in_sources(claim, sources)
    
    if not source_match:
        # Prediction not found in any source
        return {
            'claim': claim,
            'status': 'UNVERIFIABLE',
            'reason': 'Prediction not found in any source document',
            'action': 'Remove claim or find supporting source',
            'severity': 'HIGH'
        }
    
    # Step 3.2: Check if attribution is clear in report
    has_clear_attribution = check_attribution_clarity(claim, source_match)
    
    # Step 3.3: Check if source included caveats
    source_caveats = extract_source_caveats(source_match, claim)
    report_includes_caveats = check_caveats_in_report(claim, source_caveats)
    
    # Step 3.4: Check source consensus
    consensus = check_prediction_consensus(claim, sources)
    
    # Determine verification status
    if has_clear_attribution and report_includes_caveats:
        verification['status'] = 'VERIFIED'
        verification['note'] = f'Prediction properly attributed to {source_match.name}'
        
        if consensus == 'SINGLE_SOURCE':
            verification['flag'] = '⚠️ Single source prediction - not corroborated by other sources'
        
        return verification
    
    elif not has_clear_attribution:
        return {
            'claim': claim,
            'status': 'NEEDS_ATTRIBUTION',
            'source': source_match.name,
            'fix': f'Add explicit attribution: "According to {source_match.name} [X]..."',
            'severity': 'MEDIUM'
        }
    
    else:  # Missing caveats
        return {
            'claim': claim,
            'status': 'MISSING_CAVEATS',
            'source': source_match.name,
            'source_caveats': source_caveats,
            'report_caveats': report_includes_caveats,
            'fix': 'Include source caveats to maintain accuracy',
            'severity': 'MEDIUM'
        }

def find_prediction_in_sources(claim, sources):
    """
    Search sources to find if any source made this prediction
    """
    # Extract key concepts from claim
    keywords = extract_claim_keywords(claim)
    # Example: "quantum computing", "outperform", "2026"
    
    for source in sources:
        # Check if source discusses this prediction
        similarity_score = calculate_semantic_similarity(keywords, source.content)
        
        if similarity_score > 0.7:  # 70% similarity threshold
            return source
    
    return None

def check_attribution_clarity(claim, source):
    """
    Check if the report clearly attributes this prediction to a source
    """
    attribution_phrases = [
        f"According to {source.name}",
        f"{source.name} predicts",
        f"{source.name} projects",
        f"[{source.citation_number}]"
    ]
    
    # Check if claim is near any attribution phrase
    for phrase in attribution_phrases:
        if phrase_near_claim(phrase, claim, max_distance=50):  # Within 50 chars
            return True
    
    return False

def extract_source_caveats(source, claim):
    """
    Extract any caveats/qualifiers the source used for this prediction
    """
    caveat_keywords = [
        'speculative', 'uncertain', 'may', 'could', 'might',
        'depends on', 'contingent on', 'if', 'assuming',
        'potentially', 'possible', 'not guaranteed'
    ]
    
    # Find text near the prediction in source
    relevant_text = find_context_around_prediction(claim, source)
    
    found_caveats = []
    for caveat in caveat_keywords:
        if caveat in relevant_text.lower():
            found_caveats.append(caveat)
    
    return found_caveats

def check_caveats_in_report(claim, source_caveats):
    """
    Check if report includes the caveats from source
    """
    if not source_caveats:
        return True  # No caveats to check
    
    # Check if report text near this claim includes similar caveats
    report_context = find_context_around_claim(claim)
    
    caveat_coverage = 0
    for caveat in source_caveats:
        if caveat in report_context.lower() or has_similar_caveat(report_context, caveat):
            caveat_coverage += 1
    
    # At least 50% of source caveats should be present
    return caveat_coverage >= len(source_caveats) * 0.5

def check_prediction_consensus(claim, sources):
    """
    Check how many sources support this prediction
    """
    supporting_sources = 0
    
    for source in sources:
        if prediction_supported_by_source(claim, source):
            supporting_sources += 1
    
    if supporting_sources == 0:
        return 'NONE'
    elif supporting_sources == 1:
        return 'SINGLE_SOURCE'
    elif supporting_sources == 2:
        return 'MODERATE'
    else:
        return 'HIGH'
```

### Step 4: Historical Fact Verification

```python
def verify_historical_fact(claim):
    """
    For historical facts, verify they are actually true
    """
    # Extract factual claim
    # Example: "Google achieved quantum supremacy in 2019"
    
    # Search for verification
    search_query = generate_fact_check_query(claim)
    results = web_search(search_query)
    
    # Check if results confirm the fact
    if fact_confirmed_in_results(claim, results):
        return {
            'claim': claim,
            'type': 'HISTORICAL_FACT',
            'status': 'VERIFIED',
            'evidence': results[:3]  # Top 3 sources
        }
    else:
        return {
            'claim': claim,
            'type': 'HISTORICAL_FACT',
            'status': 'UNVERIFIED',
            'reason': 'Could not confirm factual claim',
            'action': 'Review and correct or remove',
            'severity': 'HIGH'
        }
```

### Step 5: Trend Verification

```python
def verify_trend_evidence(claim, sources):
    """
    For trends, verify there is evidence supporting the trend
    """
    # Example: "AI adoption is accelerating"
    
    # Check if sources provide evidence of trend
    evidence_count = 0
    evidence_sources = []
    
    for source in sources:
        if trend_supported_by_source(claim, source):
            evidence_count += 1
            evidence_sources.append(source)
    
    if evidence_count >= 2:
        return {
            'claim': claim,
            'type': 'TREND',
            'status': 'VERIFIED',
            'evidence_sources': evidence_sources,
            'note': f'Trend supported by {evidence_count} sources'
        }
    elif evidence_count == 1:
        return {
            'claim': claim,
            'type': 'TREND',
            'status': 'WEAKLY_VERIFIED',
            'evidence_sources': evidence_sources,
            'flag': '⚠️ Single source trend - not corroborated',
            'severity': 'MEDIUM'
        }
    else:
        return {
            'claim': claim,
            'type': 'TREND',
            'status': 'UNVERIFIED',
            'reason': 'No evidence found in sources',
            'action': 'Add supporting data or remove claim',
            'severity': 'HIGH'
        }
```

---

## Complete Implementation

### Main Verification Pipeline Class

```python
class EnhancedVerificationPipeline:
    """
    Enhanced verification pipeline that properly handles predictions vs facts
    """
    
    def __init__(self, sources):
        self.sources = sources
        self.results = {
            'verified': [],
            'needs_attribution': [],
            'missing_caveats': [],
            'weakly_verified': [],
            'unverifiable': []
        }
    
    def verify_report(self, report):
        """
        Main entry point: verify all claims in report
        """
        # Extract all claims from report
        claims = self.extract_claims_from_report(report)
        
        print(f"Found {len(claims)} claims to verify...")
        
        # Verify each claim
        for claim in claims:
            verification = self.verify_claim(claim)
            self.categorize_result(verification)
        
        # Generate validation report
        return self.format_validation_report()
    
    def verify_claim(self, claim):
        """
        Route claim to appropriate verification method
        """
        claim_type = classify_claim_type(claim)
        
        if claim_type == "PREDICTION":
            return verify_prediction_attribution(claim, self.sources)
        
        elif claim_type == "HISTORICAL_FACT":
            return verify_historical_fact(claim)
        
        elif claim_type == "TREND":
            return verify_trend_evidence(claim, self.sources)
        
        else:
            return self.verify_general_claim(claim)
    
    def categorize_result(self, verification):
        """
        Sort verification result into appropriate category
        """
        status = verification['status']
        
        if status == 'VERIFIED':
            self.results['verified'].append(verification)
        
        elif status == 'NEEDS_ATTRIBUTION':
            self.results['needs_attribution'].append(verification)
        
        elif status == 'MISSING_CAVEATS':
            self.results['missing_caveats'].append(verification)
        
        elif status == 'WEAKLY_VERIFIED':
            self.results['weakly_verified'].append(verification)
        
        else:  # UNVERIFIABLE
            self.results['unverifiable'].append(verification)
    
    def format_validation_report(self):
        """
        Generate human-readable validation report
        """
        report = "# Verification Report\n\n"
        
        # Summary statistics
        total = sum(len(v) for v in self.results.values())
        report += f"**Total Claims Checked**: {total}\n\n"
        
        # Verified claims
        report += f"## ✅ Properly Verified Claims ({len(self.results['verified'])})\n\n"
        for item in self.results['verified']:
            report += f"**{item['claim']}**\n"
            report += f"- Type: {item['type']}\n"
            report += f"- Status: ✅ VERIFIED\n"
            if 'note' in item:
                report += f"- Note: {item['note']}\n"
            if 'flag' in item:
                report += f"- {item['flag']}\n"
            report += "\n"
        
        # Claims needing attribution
        if self.results['needs_attribution']:
            report += f"## ⚠️ Claims Needing Clearer Attribution ({len(self.results['needs_attribution'])})\n\n"
            report += "*These predictions are found in sources but need explicit attribution in the report.*\n\n"
            
            for item in self.results['needs_attribution']:
                report += f"**{item['claim']}**\n"
                report += f"- Type: {item['type']}\n"
                report += f"- Found in: {item['source']}\n"
                report += f"- Fix: {item['fix']}\n"
                report += f"- Severity: {item['severity']}\n"
                report += "\n"
        
        # Missing caveats
        if self.results['missing_caveats']:
            report += f"## ⚠️ Claims Missing Source Caveats ({len(self.results['missing_caveats'])})\n\n"
            report += "*These predictions need to include the caveats/qualifiers from their sources.*\n\n"
            
            for item in self.results['missing_caveats']:
                report += f"**{item['claim']}**\n"
                report += f"- Source: {item['source']}\n"
                report += f"- Source caveats: {', '.join(item['source_caveats'])}\n"
                report += f"- Fix: {item['fix']}\n"
                report += "\n"
        
        # Weakly verified
        if self.results['weakly_verified']:
            report += f"## ⚠️ Weakly Verified Claims ({len(self.results['weakly_verified'])})\n\n"
            report += "*These claims have some support but could benefit from additional corroboration.*\n\n"
            
            for item in self.results['weakly_verified']:
                report += f"**{item['claim']}**\n"
                report += f"- {item['flag']}\n"
                report += "\n"
        
        # Unverifiable claims
        if self.results['unverifiable']:
            report += f"## ❌ Unverifiable Claims ({len(self.results['unverifiable'])})\n\n"
            report += "*These claims could not be verified and should be removed or replaced.*\n\n"
            
            for item in self.results['unverifiable']:
                report += f"**{item['claim']}**\n"
                report += f"- Reason: {item['reason']}\n"
                report += f"- Action: {item['action']}\n"
                report += f"- Severity: {item['severity']}\n"
                report += "\n"
        
        # Overall assessment
        report += "---\n\n"
        report += "## Overall Assessment\n\n"
        
        verified_count = len(self.results['verified'])
        issue_count = len(self.results['needs_attribution']) + \
                     len(self.results['missing_caveats']) + \
                     len(self.results['unverifiable'])
        
        if issue_count == 0:
            report += "✅ **All claims properly verified** - Report meets verification standards\n"
        elif issue_count <= 2:
            report += "⚠️ **Minor issues found** - Report is good but has a few items to address\n"
        elif issue_count <= 5:
            report += "⚠️ **Several issues found** - Report needs attention before finalization\n"
        else:
            report += "❌ **Significant issues found** - Report requires substantial revision\n"
        
        report += f"\n**Breakdown:**\n"
        report += f"- Verified: {len(self.results['verified'])}\n"
        report += f"- Need attribution: {len(self.results['needs_attribution'])}\n"
        report += f"- Missing caveats: {len(self.results['missing_caveats'])}\n"
        report += f"- Weakly verified: {len(self.results['weakly_verified'])}\n"
        report += f"- Unverifiable: {len(self.results['unverifiable'])}\n"
        
        return report
    
    def extract_claims_from_report(self, report):
        """
        Extract all claims from report that need verification
        """
        claims = []
        
        # Extract from Key Findings section
        key_findings = self.extract_section(report, "Key Findings")
        claims.extend(self.parse_bullet_points(key_findings))
        
        # Extract from Analysis section (main claims only)
        analysis = self.extract_section(report, "Analysis")
        claims.extend(self.extract_major_claims(analysis))
        
        return claims

# Usage example:
pipeline = EnhancedVerificationPipeline(sources)
validation_report = pipeline.verify_report(generated_report)
print(validation_report)
```

---

## Examples of Correct Verification

### Example 1: Well-Attributed Prediction (✅ VERIFIED)

**Claim**: "According to IBM [1], quantum computing is projected to outperform classical systems for specific tasks in 2026, though this remains speculative."

**Verification Result**:
```python
{
    'claim': 'quantum computing is projected to outperform...',
    'type': 'PREDICTION',
    'status': 'VERIFIED',
    'source': 'IBM',
    'note': 'Prediction properly attributed to IBM [1]',
    'caveats_present': True,  # "remains speculative"
    'consensus': 'SINGLE_SOURCE'
}
```

**Why it passes**:
- ✅ Clear attribution ("According to IBM")
- ✅ Source actually made this prediction
- ✅ Includes caveat ("remains speculative")
- ✅ Citation present [1]

---

### Example 2: Missing Attribution (⚠️ NEEDS_ATTRIBUTION)

**Claim**: "Quantum computing will outperform classical systems in 2026."

**Verification Result**:
```python
{
    'claim': 'Quantum computing will outperform...',
    'type': 'PREDICTION',
    'status': 'NEEDS_ATTRIBUTION',
    'source': 'IBM [1]',
    'fix': 'Add: "According to IBM [1], quantum computing is projected to..."',
    'severity': 'MEDIUM',
    'reason': 'Prediction found in source but attribution not explicit in report'
}
```

**Why it needs fixing**:
- ❌ No explicit attribution
- ✅ Prediction exists in source
- ⚠️ Needs to add "According to [source]"

---

### Example 3: Missing Caveats (⚠️ MISSING_CAVEATS)

**Claim**: "World models will enable AI systems to simulate physical environments without human-labeled data."

**Source says**: "World models may enable AI systems to simulate physical environments, though this remains experimental and resource-intensive."

**Verification Result**:
```python
{
    'claim': 'World models will enable...',
    'type': 'PREDICTION',
    'status': 'MISSING_CAVEATS',
    'source': 'VentureBeat [2]',
    'source_caveats': ['may', 'experimental', 'resource-intensive'],
    'report_caveats': [],
    'fix': 'Include source caveats: "may enable", "remains experimental", "resource-intensive"',
    'severity': 'MEDIUM'
}
```

**Why it needs fixing**:
- ✅ Prediction found in source
- ✅ Attribution present
- ❌ Report changed "may" to "will"
- ❌ Dropped "experimental" and "resource-intensive" caveats

---

### Example 4: Completely Unverifiable (❌ UNVERIFIABLE)

**Claim**: "AI will achieve human-level reasoning by 2026."

**Verification Result**:
```python
{
    'claim': 'AI will achieve human-level reasoning by 2026',
    'type': 'PREDICTION',
    'status': 'UNVERIFIABLE',
    'reason': 'Prediction not found in any source document',
    'action': 'Remove claim or find supporting source',
    'severity': 'HIGH',
    'note': 'This appears to be an unsupported inference'
}
```

**Why it fails**:
- ❌ Not found in any source
- ❌ Appears to be fabricated or over-extrapolated
- ❌ No reputable source makes this claim

---

## Testing the New Pipeline

### Test Cases to Run

```python
def test_verification_pipeline():
    """
    Test suite for verification pipeline
    """
    
    # Test Case 1: Well-attributed prediction
    claim1 = "According to IBM [1], quantum computing will outperform classical systems in 2026."
    result1 = verify_claim(claim1, sources)
    assert result1['status'] == 'VERIFIED'
    
    # Test Case 2: Prediction without attribution
    claim2 = "Quantum computing will revolutionize AI in 2026."
    result2 = verify_claim(claim2, sources)
    assert result2['status'] in ['NEEDS_ATTRIBUTION', 'UNVERIFIABLE']
    
    # Test Case 3: Historical fact
    claim3 = "Google achieved quantum supremacy in 2019."
    result3 = verify_claim(claim3, sources)
    assert result3['status'] == 'VERIFIED'
    
    # Test Case 4: Prediction with missing caveats
    claim4 = "World models will enable AI systems to simulate environments."
    # Source says "may enable" not "will enable"
    result4 = verify_claim(claim4, sources)
    assert result4['status'] in ['MISSING_CAVEATS', 'VERIFIED']
    
    # Test Case 5: Completely fabricated claim
    claim5 = "AGI will be achieved by end of 2026."
    result5 = verify_claim(claim5, sources)
    assert result5['status'] == 'UNVERIFIABLE'
    
    print("All tests passed!")
```

---

## Implementation Checklist

### Phase 1: Core Logic (Priority: HIGH)
- [ ] Implement `classify_claim_type()` function
- [ ] Implement `verify_prediction_attribution()` function
- [ ] Implement `find_prediction_in_sources()` function
- [ ] Implement `check_attribution_clarity()` function
- [ ] Test with current report's 8 flagged claims

### Phase 2: Caveat Detection (Priority: HIGH)
- [ ] Implement `extract_source_caveats()` function
- [ ] Implement `check_caveats_in_report()` function
- [ ] Test caveat detection accuracy

### Phase 3: Additional Claim Types (Priority: MEDIUM)
- [ ] Implement `verify_historical_fact()` function
- [ ] Implement `verify_trend_evidence()` function
- [ ] Test with various claim types

### Phase 4: Output Formatting (Priority: MEDIUM)
- [ ] Implement enhanced validation report format
- [ ] Add severity levels and actionable fixes
- [ ] Test report generation

### Phase 5: Integration (Priority: HIGH)
- [ ] Integrate with existing workflow
- [ ] Update validation prompt shown to user
- [ ] Test end-to-end workflow

---

## Expected Results After Implementation

### For Current Report (8 Flagged Claims):

**Current (Incorrect) Output**:
```
Issues:
- Unverified claims: [8 claims listed]
```

**Expected (Correct) Output**:
```
# Verification Report

**Total Claims Checked**: 8

## ✅ Properly Verified Claims (6)

**"Agentic AI will evolve into digital coworkers..."**
- Type: PREDICTION
- Status: ✅ VERIFIED
- Source: Microsoft [3]
- Note: Prediction properly attributed with citation

**"Continual learning will become a standard feature..."**
- Type: PREDICTION  
- Status: ✅ VERIFIED
- Source: VentureBeat [2]
- Note: Prediction properly attributed

[... 4 more verified predictions ...]

## ⚠️ Claims Needing Clearer Attribution (2)

**"Security and trust will be central to AI agent deployment..."**
- Type: PREDICTION
- Found in: Microsoft [3]
- Fix: Add explicit attribution: "According to Microsoft [3], security..."
- Severity: MEDIUM

**"Human-AI collaboration will become the dominant paradigm..."**
- Type: PREDICTION
- Found in: Multiple sources
- Fix: Add attribution to primary source
- Severity: MEDIUM

## ❌ Unverifiable Claims (0)

None found - all predictions trace back to sources

---

## Overall Assessment

⚠️ **Minor issues found** - Report is good but has 2 items needing clearer attribution

**Breakdown:**
- Verified: 6
- Need attribution: 2
- Missing caveats: 0
- Unverifiable: 0
```

---

## Key Takeaways

### Critical Distinctions:

1. **Predictions vs Facts**:
   - ❌ Don't verify if prediction will come true
   - ✅ Verify if source made the prediction

2. **What to Verify for Predictions**:
   - ✅ Source attribution
   - ✅ Accuracy of representation
   - ✅ Inclusion of caveats
   - ❌ NOT truth value

3. **Status Categories**:
   - `VERIFIED` = Properly attributed with caveats
   - `NEEDS_ATTRIBUTION` = In source but attribution unclear
   - `MISSING_CAVEATS` = Source had caveats not included
   - `UNVERIFIABLE` = Not found in any source

### The Goal:

Transform verification from a **binary pass/fail** into a **nuanced quality assessment** that:
- Distinguishes between claim types
- Provides actionable feedback
- Helps improve report quality
- Doesn't create false positives

---

## Questions or Issues?

If you encounter any challenges implementing this fix, document:
1. Which function is problematic
2. What behavior you're seeing
3. What behavior you expected

And we'll troubleshoot together. Focus on getting Phase 1 (Core Logic) working first, as it's the foundation for everything else.

---

## Bottom Line

**Current State**: Pipeline flags all predictions as "unverified" because it's trying to verify future events ❌

**Desired State**: Pipeline distinguishes predictions from facts, verifies source attribution for predictions, and provides helpful categorized feedback ✅

**Priority**: HIGH - This is blocking the validation workflow from being useful

**Estimated Effort**: 2-3 hours for Phase 1 (core logic) + testing

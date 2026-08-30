# Critical Issue: Zero-Source Report Generation

## Evaluation of Report with No Sources

**Overall Quality: 4/10** ⚠️ **CRITICAL ISSUE: Zero Sources**

This report demonstrates **excellent transparency** about its limitations, but it **should not have been generated at all** without sources.

---

## What This Report Gets RIGHT ✅

### 1. Radical Transparency (10/10) ⭐

The report is completely honest about its limitations:

```
"Due to the absence of verifiable sources, all claims are speculative"
"No empirical data supports these projections"
"All findings are speculative and based on extrapolation"
"This report is preliminary and should be treated as indicative"
```

**This is exemplary honesty!** The report doesn't pretend to have sources when it doesn't.

### 2. Proper Structure Maintained (7/10)

- Still includes all required sections
- Confidence assessments present
- Risk factors identified
- Critical analysis included
- Proper formatting

### 3. Appropriate Caveats Throughout (9/10)

- "will become" → qualified with uncertainty
- Confidence tiers properly labeled
- "should be treated as indicative rather than definitive"
- Clear about assumptions and dependencies

### 4. No Citation Fraud (10/10)

- Doesn't fabricate sources
- Explicitly states "No citations are available"
- [1], [2] markers appear but are acknowledged as unsupported
- Honest about the absence of verification

---

## What's CRITICALLY WRONG ❌

### 1. The Report Exists At All (Critical Flaw)

**The workflow should STOP and return an error instead:**

```
╔════════════════════════════════════════════════════════╗
║  ❌ CANNOT GENERATE REPORT - NO SOURCES FOUND          ║
╚════════════════════════════════════════════════════════╝

**Reason**: No sources found for topic "AI Trends in 2026"

**Required Action**: 
- Provide at least 3 sources to proceed
- OR modify search parameters
- OR select different topic

**Current State**: 0 sources found (minimum: 3)

Do you want to:
1. Retry with different search terms?
2. Manually provide sources?
3. Cancel report generation?
```

### 2. Content is Pure Speculation (1/10)

Without sources, all claims are just educated guesses:

- ❌ "Multimodal AI will become mainstream" - Based on what data?
- ❌ "AI-Augmented Workflows will be embedded" - Says who?
- ❌ "AI Talent Gap will persist" - What's the source?
- ❌ "Generative AI will continue to evolve" - Evidence?

**This is the AI making predictions, not synthesizing research.**

### 3. False Sense of Analysis (3/10)

The report has all the trappings of analysis:
- Critical analysis section ✓
- Risk factors ✓
- Confidence assessment ✓
- Professional formatting ✓

**But it's analyzing... nothing.** It's just well-formatted speculation with no factual foundation.

### 4. Could Mislead Users (High Risk)

A busy executive might:
- See professional formatting ✓
- See confidence scores ✓
- See structured sections ✓
- Skim past the warnings
- **Assume it's based on research** ❌

The warnings ARE there, but they could easily be missed or underestimated.

---

## Comparison Across All Four Reports

| Aspect | Report 1 | Report 2 | Report 3 | Report 4 (No Sources) |
|--------|----------|----------|----------|----------------------|
| **Source Count** | 2 | 2 | 3 | **0** ❌ |
| **Confidence Scores** | ❌ | ❌ | ✅ | ✅ |
| **Critical Analysis** | Minimal | None | ✅ | ✅ (but baseless) |
| **Transparency** | Low | Low | Good | **Excellent** ✅ |
| **Fact-Based?** | Partially | Partially | Yes | **NO** ❌ |
| **Should Exist?** | Yes | Yes | Yes | **NO** ❌ |
| **Overall Quality** | 7.5/10 | 6.5/10 | 8.5/10 | **4/10** |

---

## The Core Problem

### What's Happening Now (WRONG):

```python
def generate_report(topic, sources):
    if len(sources) == 0:
        # Generate report anyway with heavy disclaimers
        report = generate_speculative_report(topic)
        report.add_disclaimer("⚠️ No sources available - all claims speculative")
        return report  # ❌ Should NOT return a report
```

### What Should Happen (CORRECT):

```python
def generate_report(topic, sources):
    if len(sources) == 0:
        error_message = format_no_sources_error(topic)
        raise InsufficientSourcesError(error_message)
        # ✅ NO REPORT GENERATED
    
    elif len(sources) < MINIMUM_SOURCES:
        # Warn user and let them decide
        handle_insufficient_sources(sources, topic)
    
    # Only proceed with adequate sources
    return generate_research_report(topic, sources)
```

---

## Implementation: Source Count Validation

### Priority 0: Source Count Gate (CRITICAL - IMPLEMENT FIRST)

This must be the **first check** before any report generation begins.

```python
class SourceValidation:
    """
    Validate source requirements before allowing report generation
    """
    
    # Configuration
    MINIMUM_SOURCES = 3
    RECOMMENDED_SOURCES = 5
    OPTIMAL_SOURCES = 7
    
    def __init__(self):
        self.validation_results = {
            'status': None,
            'proceed': False,
            'message': None,
            'source_count': 0,
            'suggestions': []
        }
    
    def validate_sources(self, sources, topic):
        """
        Check if sufficient sources exist to generate a credible report
        
        Returns validation result with status:
        - CRITICAL_ERROR: No sources (0)
        - INSUFFICIENT: Under minimum (1-2)
        - MINIMAL: At minimum (3-4)
        - ADEQUATE: Good count (5-6)
        - OPTIMAL: Excellent count (7+)
        """
        source_count = len(sources)
        
        # CRITICAL: Block report generation if no sources
        if source_count == 0:
            return self.handle_zero_sources(topic)
        
        # INSUFFICIENT: Strong warning, let user decide
        elif source_count < self.MINIMUM_SOURCES:
            return self.handle_insufficient_sources(sources, topic)
        
        # MINIMAL: Warning, but acceptable
        elif source_count < self.RECOMMENDED_SOURCES:
            return self.handle_minimal_sources(sources, topic)
        
        # ADEQUATE: Good to proceed
        elif source_count < self.OPTIMAL_SOURCES:
            return self.handle_adequate_sources(sources, topic)
        
        # OPTIMAL: Excellent source count
        else:
            return self.handle_optimal_sources(sources, topic)
    
    def handle_zero_sources(self, topic):
        """
        CRITICAL ERROR: No sources found - MUST NOT generate report
        """
        return {
            'status': 'CRITICAL_ERROR',
            'proceed': False,
            'source_count': 0,
            'error_type': 'NO_SOURCES',
            'severity': 'BLOCKING',
            'message': self.format_zero_sources_message(topic),
            'suggestions': self.suggest_alternative_queries(topic)
        }
    
    def handle_insufficient_sources(self, sources, topic):
        """
        INSUFFICIENT: Under minimum - strong warning, user choice
        """
        return {
            'status': 'INSUFFICIENT',
            'proceed': 'USER_CHOICE',
            'source_count': len(sources),
            'severity': 'HIGH',
            'message': self.format_insufficient_sources_message(sources, topic),
            'sources': sources,
            'suggestions': self.suggest_additional_searches(topic)
        }
    
    def handle_minimal_sources(self, sources, topic):
        """
        MINIMAL: At minimum threshold - advisory warning
        """
        return {
            'status': 'MINIMAL',
            'proceed': True,
            'source_count': len(sources),
            'severity': 'MEDIUM',
            'message': self.format_minimal_sources_message(sources, topic),
            'sources': sources,
            'note': 'Consider adding more sources for better quality'
        }
    
    def handle_adequate_sources(self, sources, topic):
        """
        ADEQUATE: Good source count - minor advisory
        """
        return {
            'status': 'ADEQUATE',
            'proceed': True,
            'source_count': len(sources),
            'severity': 'LOW',
            'message': f"✓ {len(sources)} sources found - good coverage",
            'sources': sources
        }
    
    def handle_optimal_sources(self, sources, topic):
        """
        OPTIMAL: Excellent source count
        """
        return {
            'status': 'OPTIMAL',
            'proceed': True,
            'source_count': len(sources),
            'severity': 'NONE',
            'message': f"✓ {len(sources)} sources found - excellent coverage",
            'sources': sources
        }
    
    def format_zero_sources_message(self, topic):
        """
        Format error message for zero sources
        """
        return f"""
╔════════════════════════════════════════════════════════════════╗
║              ❌ CANNOT GENERATE REPORT                          ║
║              NO SOURCES FOUND                                  ║
╚════════════════════════════════════════════════════════════════╝

Topic: "{topic}"

═══════════════════════════════════════════════════════════════

PROBLEM:
  • 0 sources found for this topic
  • Cannot generate research report without source material
  • Proceeding would produce pure speculation with no factual basis

REQUIREMENTS:
  • Minimum: {self.MINIMUM_SOURCES} credible sources
  • Recommended: {self.RECOMMENDED_SOURCES}-{self.OPTIMAL_SOURCES} sources for comprehensive coverage
  • Sources should include diverse perspectives

═══════════════════════════════════════════════════════════════

SUGGESTED ACTIONS:

1. 🔍 RETRY WITH BROADER SEARCH TERMS
   Current topic: "{topic}"
   
   Try these alternatives:
   {self._format_suggestions(self.suggest_alternative_queries(topic))}

2. 🌐 VERIFY SEARCH CONFIGURATION
   • Check internet connectivity
   • Verify web search tool is enabled
   • Check for network restrictions
   • Ensure search API is functioning

3. 📝 PROVIDE SOURCES MANUALLY
   • Add URLs or documents directly
   • Upload research papers or industry reports
   • Reference specific publications

4. 🎯 REFINE OR CHANGE TOPIC
   • Topic may be too niche or futuristic
   • Try related but broader topics
   • Consider topics with more available research

═══════════════════════════════════════════════════════════════

⚠️  CRITICAL: DO NOT PROCEED WITHOUT SOURCES
⚠️  Any generated content would be unreliable speculation
⚠️  Research reports REQUIRE research

═══════════════════════════════════════════════════════════════
        """
    
    def format_insufficient_sources_message(self, sources, topic):
        """
        Format warning message for insufficient sources
        """
        source_list = self._format_source_list(sources)
        
        return f"""
╔════════════════════════════════════════════════════════════════╗
║              ⚠️  INSUFFICIENT SOURCES WARNING                   ║
╚════════════════════════════════════════════════════════════════╝

Topic: "{topic}"
Sources found: {len(sources)} (Minimum recommended: {self.MINIMUM_SOURCES})

═══════════════════════════════════════════════════════════════

⚠️  QUALITY RISKS WITH <{self.MINIMUM_SOURCES} SOURCES:

  • Cannot effectively cross-reference claims
  • Cannot verify consensus or identify disagreements
  • Limited perspective diversity
  • Higher risk of source bias
  • Reduced confidence in findings
  • May miss important counterarguments

═══════════════════════════════════════════════════════════════

CURRENT SOURCES:
{source_list}

═══════════════════════════════════════════════════════════════

YOUR OPTIONS:

1. ⏸️  RETRY SEARCH (Strongly Recommended)
   • Try broader search terms
   • Add related keywords
   • Search different time periods
   • Look for industry reports, academic papers
   
   Suggested searches:
   {self._format_suggestions(self.suggest_additional_searches(topic))}

2. ⚠️  PROCEED ANYWAY (Not Recommended)
   If you proceed with only {len(sources)} source{'s' if len(sources) != 1 else ''}:
   • Report will include prominent warning banner
   • All confidence scores will be marked as "Limited Sources"
   • Every claim will be flagged as "Insufficient Verification"
   • Report quality will be significantly compromised

3. ❌ CANCEL
   • Abort report generation
   • Try a different topic or approach

═══════════════════════════════════════════════════════════════

What would you like to do?
(Enter: retry / proceed / cancel)
        """
    
    def format_minimal_sources_message(self, sources, topic):
        """
        Format advisory message for minimal sources
        """
        source_list = self._format_source_list(sources)
        
        return f"""
╔════════════════════════════════════════════════════════════════╗
║              ℹ️  SOURCE COUNT ADVISORY                          ║
╚════════════════════════════════════════════════════════════════╝

Topic: "{topic}"
Sources found: {len(sources)} (Recommended: {self.RECOMMENDED_SOURCES}+)

═══════════════════════════════════════════════════════════════

CURRENT SOURCES:
{source_list}

═══════════════════════════════════════════════════════════════

ℹ️  ADVISORY:

You have met the minimum source requirement ({self.MINIMUM_SOURCES}), but 
additional sources would improve:
  • Claim verification and cross-referencing
  • Perspective diversity
  • Confidence in findings
  • Detection of source disagreements

Consider searching for {self.RECOMMENDED_SOURCES - len(sources)} more source{'s' if self.RECOMMENDED_SOURCES - len(sources) != 1 else ''}.

═══════════════════════════════════════════════════════════════

Proceeding with {len(sources)} sources...
        """
    
    def suggest_alternative_queries(self, topic):
        """
        Suggest alternative, broader search queries
        """
        # Extract key terms from topic
        key_terms = self._extract_key_terms(topic)
        
        suggestions = []
        
        if key_terms:
            main_term = key_terms[0]
            suggestions = [
                f"{main_term} trends",
                f"{main_term} predictions",
                f"{main_term} forecast 2025 2026",
                f"{main_term} industry analysis",
                f"{main_term} market research",
                f"{main_term} technology outlook"
            ]
        else:
            # Generic suggestions
            suggestions = [
                f"{topic} overview",
                f"{topic} current state",
                f"{topic} recent developments"
            ]
        
        return suggestions[:5]  # Return top 5
    
    def suggest_additional_searches(self, topic):
        """
        Suggest additional searches to complement existing sources
        """
        suggestions = [
            f"{topic} academic research",
            f"{topic} industry reports",
            f"{topic} expert analysis",
            f"{topic} case studies",
            f"{topic} white papers"
        ]
        
        return suggestions
    
    def _extract_key_terms(self, topic):
        """
        Extract key terms from topic for search suggestions
        """
        # Remove common words
        stop_words = ['in', 'the', 'a', 'an', 'and', 'or', 'but', 'for', 'on', 'at', 'to', 'from']
        
        words = topic.lower().split()
        key_terms = [w for w in words if w not in stop_words and len(w) > 3]
        
        return key_terms
    
    def _format_source_list(self, sources):
        """
        Format sources for display in messages
        """
        if not sources:
            return "   (No sources)"
        
        formatted = []
        for i, source in enumerate(sources, 1):
            source_type = getattr(source, 'type', 'unknown')
            source_title = getattr(source, 'title', 'Untitled')
            source_url = getattr(source, 'url', '')
            
            formatted.append(f"   {i}. [{source_type}] {source_title}")
            if source_url:
                formatted.append(f"      {source_url}")
        
        return "\n".join(formatted)
    
    def _format_suggestions(self, suggestions):
        """
        Format suggestions for display
        """
        if not suggestions:
            return "   (No suggestions available)"
        
        formatted = []
        for i, suggestion in enumerate(suggestions, 1):
            formatted.append(f"   {i}. \"{suggestion}\"")
        
        return "\n".join(formatted)


class InsufficientSourcesError(Exception):
    """
    Custom exception for insufficient sources
    """
    pass
```

---

## Integration into Main Workflow

### Updated Report Generation Flow

```python
def generate_report(topic, user_config):
    """
    Main report generation with mandatory source validation gate
    """
    
    print(f"Generating report for: {topic}")
    print(f"Configured to collect up to {user_config.get('source_count', 5)} sources...\n")
    
    # ═══════════════════════════════════════════════════════════
    # STAGE 1: COLLECT SOURCES
    # ═══════════════════════════════════════════════════════════
    
    print("Stage 1: Searching for sources...")
    sources = collect_sources(topic, user_config)
    print(f"Found {len(sources)} source{'s' if len(sources) != 1 else ''}\n")
    
    # ═══════════════════════════════════════════════════════════
    # STAGE 2: VALIDATE SOURCES (CRITICAL GATE - CANNOT SKIP)
    # ═══════════════════════════════════════════════════════════
    
    print("Stage 2: Validating source count...")
    validator = SourceValidation()
    validation = validator.validate_sources(sources, topic)
    
    # Handle validation result
    if validation['status'] == 'CRITICAL_ERROR':
        # BLOCKING ERROR - Cannot proceed
        print("\n" + validation['message'])
        
        # Show suggestions
        if validation.get('suggestions'):
            print("\n🔍 Try these search terms:")
            for suggestion in validation['suggestions'][:3]:
                print(f"   • {suggestion}")
        
        # Raise exception to stop execution
        raise InsufficientSourcesError(
            f"Cannot generate report without sources. Topic: {topic}"
        )
    
    elif validation['status'] == 'INSUFFICIENT':
        # WARNING - Let user decide
        print("\n" + validation['message'])
        
        # Get user input
        while True:
            user_choice = input("\nYour choice (retry/proceed/cancel): ").strip().lower()
            
            if user_choice == 'retry':
                print("\nRetrying with suggested search terms...")
                return retry_with_suggestions(topic, validation['suggestions'], user_config)
            
            elif user_choice == 'proceed':
                print("\n⚠️  Proceeding with limited sources...")
                print("⚠️  Report quality will be compromised\n")
                
                # Set warning flag for report
                user_config['limited_sources_warning'] = True
                user_config['actual_source_count'] = len(sources)
                break
            
            elif user_choice == 'cancel':
                print("\nReport generation cancelled.")
                return None
            
            else:
                print("Invalid choice. Please enter 'retry', 'proceed', or 'cancel'.")
    
    elif validation['status'] == 'MINIMAL':
        # ADVISORY - Proceed with note
        print(validation['message'])
        user_config['minimal_sources_note'] = True
        user_config['actual_source_count'] = len(sources)
    
    else:  # ADEQUATE or OPTIMAL
        # Good to go
        print(validation['message'])
        user_config['actual_source_count'] = len(sources)
    
    # ═══════════════════════════════════════════════════════════
    # STAGE 3: ASSESS SOURCE DIVERSITY
    # ═══════════════════════════════════════════════════════════
    
    print("\nStage 3: Assessing source diversity...")
    diversity_assessment = assess_source_diversity(sources)
    
    if diversity_assessment['score'] < 0.3:
        print(f"⚠️  Warning: Low source diversity (score: {diversity_assessment['score']:.2f})")
        print(f"   All sources are: {diversity_assessment['dominant_type']}")
        print(f"   Consider adding: {', '.join(diversity_assessment['missing_types'])}")
        user_config['low_diversity_warning'] = True
    else:
        print(f"✓ Source diversity: {diversity_assessment['score']:.2f}")
    
    # ═══════════════════════════════════════════════════════════
    # STAGE 4+: PROCEED WITH REPORT GENERATION
    # ═══════════════════════════════════════════════════════════
    
    print("\nStage 4: Extracting and verifying claims...")
    # ... rest of workflow continues ...
    
    return generate_full_report(topic, sources, user_config)


def retry_with_suggestions(topic, suggestions, user_config):
    """
    Retry source collection with suggested search terms
    """
    print(f"\nTrying alternative search strategies...")
    
    all_sources = []
    
    for suggestion in suggestions[:3]:  # Try top 3 suggestions
        print(f"\nSearching: {suggestion}")
        new_sources = search_for_sources(suggestion, user_config)
        
        if new_sources:
            all_sources.extend(new_sources)
            print(f"  Found {len(new_sources)} additional source{'s' if len(new_sources) != 1 else ''}")
        else:
            print(f"  No sources found")
        
        # Stop if we have enough
        if len(all_sources) >= SourceValidation.RECOMMENDED_SOURCES:
            break
    
    # Remove duplicates
    unique_sources = deduplicate_sources(all_sources)
    
    print(f"\nTotal unique sources found: {len(unique_sources)}")
    
    if len(unique_sources) >= SourceValidation.MINIMUM_SOURCES:
        print("✓ Sufficient sources found!")
        return generate_report(topic, user_config)
    else:
        print(f"⚠️  Still insufficient sources ({len(unique_sources)} found)")
        return generate_report(topic, user_config)  # Will hit validation again


def assess_source_diversity(sources):
    """
    Assess diversity of source types
    """
    if not sources:
        return {'score': 0, 'dominant_type': 'none', 'missing_types': []}
    
    # Count source types
    type_counts = {}
    for source in sources:
        source_type = getattr(source, 'type', 'unknown')
        type_counts[source_type] = type_counts.get(source_type, 0) + 1
    
    # Calculate diversity score (0-1)
    # Higher score = more diverse
    num_types = len(type_counts)
    total_sources = len(sources)
    
    # Simpson's Diversity Index
    diversity_score = 1 - sum((count/total_sources)**2 for count in type_counts.values())
    
    # Identify dominant type
    dominant_type = max(type_counts, key=type_counts.get)
    
    # Identify missing types
    desired_types = ['industry_report', 'academic', 'news', 'blog', 'government']
    missing_types = [t for t in desired_types if t not in type_counts]
    
    return {
        'score': diversity_score,
        'type_counts': type_counts,
        'dominant_type': dominant_type,
        'missing_types': missing_types
    }
```

---

## Handling Limited Sources in Report

### Add Warning Banner to Report

```python
def add_source_warnings_to_report(report, config):
    """
    Add appropriate warnings based on source count and quality
    """
    source_count = config.get('actual_source_count', 0)
    
    # Critical warning for very few sources
    if source_count < 3:
        banner = f"""
╔══════════════════════════════════════════════════════════════════╗
║                       ⚠️  QUALITY NOTICE ⚠️                       ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  This report is based on only {source_count} source{'s' if source_count != 1 else ''}.                          ║
║                                                                  ║
║  SIGNIFICANT LIMITATIONS:                                        ║
║  • Cannot cross-reference claims effectively                    ║
║  • Limited perspective diversity                                ║
║  • Higher risk of source bias                                   ║
║  • Cannot verify consensus or disagreements                     ║
║  • Reduced confidence in all findings                           ║
║                                                                  ║
║  ⚠️  Treat all findings as PRELIMINARY                           ║
║  ⚠️  Seek additional sources before making decisions             ║
║  ⚠️  Verify critical claims independently                        ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
        """
        
        report.insert_after_title(banner)
        
        # Add note to confidence assessment
        report.add_confidence_caveat(f"""
**IMPORTANT**: All confidence scores in this report are severely limited by 
the small number of sources ({source_count}). Even claims marked "High Confidence" 
should be treated with significant caution. A proper research report requires 
at least 3-5 diverse sources for reliable findings.
        """)
    
    # Advisory for minimal sources
    elif source_count < 5:
        notice = f"""
**Source Quality Notice**: This report is based on {source_count} sources. 
While this meets minimum requirements, additional sources would improve 
reliability and provide better cross-verification of claims.
        """
        
        report.insert_after_executive_summary(notice)
    
    # Diversity warning
    if config.get('low_diversity_warning'):
        diversity_note = """
**Source Diversity Notice**: Sources show limited diversity in perspectives. 
Consider supplementing with additional viewpoints from different source types.
        """
        
        report.add_to_methodology_section(diversity_note)
```

---

## Testing the Source Validation

### Test Suite

```python
def test_source_validation():
    """
    Test source validation with various scenarios
    """
    validator = SourceValidation()
    
    # Test 1: Zero sources (CRITICAL ERROR)
    print("Test 1: Zero sources")
    result = validator.validate_sources([], "AI Trends 2026")
    assert result['status'] == 'CRITICAL_ERROR'
    assert result['proceed'] == False
    print("✓ Correctly blocks generation with 0 sources\n")
    
    # Test 2: One source (INSUFFICIENT)
    print("Test 2: One source")
    result = validator.validate_sources([MockSource()], "AI Trends 2026")
    assert result['status'] == 'INSUFFICIENT'
    assert result['proceed'] == 'USER_CHOICE'
    print("✓ Correctly warns with 1 source\n")
    
    # Test 3: Two sources (INSUFFICIENT)
    print("Test 3: Two sources")
    result = validator.validate_sources([MockSource(), MockSource()], "AI Trends 2026")
    assert result['status'] == 'INSUFFICIENT'
    assert result['proceed'] == 'USER_CHOICE'
    print("✓ Correctly warns with 2 sources\n")
    
    # Test 4: Three sources (MINIMAL)
    print("Test 4: Three sources")
    result = validator.validate_sources([MockSource()] * 3, "AI Trends 2026")
    assert result['status'] == 'MINIMAL'
    assert result['proceed'] == True
    print("✓ Allows with advisory at 3 sources\n")
    
    # Test 5: Five sources (ADEQUATE)
    print("Test 5: Five sources")
    result = validator.validate_sources([MockSource()] * 5, "AI Trends 2026")
    assert result['status'] == 'ADEQUATE'
    assert result['proceed'] == True
    print("✓ Proceeds normally with 5 sources\n")
    
    # Test 6: Seven+ sources (OPTIMAL)
    print("Test 6: Seven sources")
    result = validator.validate_sources([MockSource()] * 7, "AI Trends 2026")
    assert result['status'] == 'OPTIMAL'
    assert result['proceed'] == True
    print("✓ Optimal with 7+ sources\n")
    
    print("All tests passed! ✓")


class MockSource:
    """Mock source for testing"""
    def __init__(self):
        self.title = "Test Source"
        self.type = "news"
        self.url = "https://example.com"
```

---

## Implementation Checklist

### Critical Priority (Implement Immediately)

- [ ] Implement `SourceValidation` class
- [ ] Add hard block for 0 sources (CRITICAL_ERROR)
- [ ] Add user choice prompt for 1-2 sources (INSUFFICIENT)
- [ ] Add advisory for 3-4 sources (MINIMAL)
- [ ] Integrate into main workflow before any report generation
- [ ] Test with all source count scenarios (0, 1, 2, 3, 5, 7+)
- [ ] Add `InsufficientSourcesError` exception
- [ ] Implement retry mechanism with suggestions
- [ ] Add source diversity assessment
- [ ] Implement warning banners for limited-source reports

### Secondary Priority (After Critical)

- [ ] Improve search term suggestions algorithm
- [ ] Add manual source input option
- [ ] Implement source deduplication
- [ ] Add source quality scoring
- [ ] Create user-friendly error messages
- [ ] Add logging for validation events
- [ ] Implement "explain why" for validation decisions

---

## Expected Behavior After Implementation

### Scenario 1: Zero Sources

```
User: "Generate report on AI Trends 2026"
→ Workflow searches for sources
→ Finds 0 sources
→ ❌ Shows CRITICAL ERROR message
→ Suggests alternative search terms
→ Offers to retry or cancel
→ Does NOT generate any report
```

### Scenario 2: Two Sources Found

```
User: "Generate report on AI Trends 2026"
→ Workflow searches for sources
→ Finds 2 sources
→ ⚠️  Shows INSUFFICIENT WARNING
→ Lists the 2 sources found
→ Explains quality risks
→ Asks: retry / proceed / cancel?

If user chooses "proceed":
→ Generates report with prominent warning banner
→ Marks all confidence scores as "Limited Sources"
→ Flags every claim as needing additional verification
```

### Scenario 3: Five Sources Found

```
User: "Generate report on AI Trends 2026"
→ Workflow searches for sources
→ Finds 5 sources
→ ✓ Shows "Adequate coverage" message
→ Proceeds to source diversity check
→ Generates report normally
→ No special warnings needed
```

---

## Key Principles

### 1. Never Generate Without Sources

**Absolute Rule**: A research report without sources is not a research report.

Even with perfect transparency and caveats, generating a zero-source report:
- Violates the fundamental purpose of research
- Could mislead users despite warnings
- Damages credibility of the workflow
- Sets bad precedent

### 2. Inform and Empower Users

Don't silently fail or generate poor reports. Instead:
- Explain what went wrong
- Show what was found
- Suggest concrete next steps
- Let user make informed decisions

### 3. Quality Gates are Non-Negotiable

Source validation is a **gate**, not a suggestion:
- 0 sources → BLOCK (no exceptions)
- 1-2 sources → WARN and get user confirmation
- 3-4 sources → ADVISE but proceed
- 5+ sources → PROCEED normally

### 4. Fail Loudly and Helpfully

When validation fails:
- Clear, formatted error messages
- Specific suggestions for fixes
- Alternative approaches
- Never fail silently

---

## Analogy for Understanding

**Current Behavior** (Report 4):
> Student: "I couldn't find any sources for my research paper."
> 
> AI: "No problem! Here's a well-formatted speculation about what might happen, clearly labeled as having no sources."
>
> Teacher: ❌ "No. That's not a research paper. Find sources first."

**Correct Behavior** (After Implementation):
> Student: "I couldn't find any sources for my research paper."
>
> AI: ❌ "I cannot write a research paper without sources. Here are some alternative search strategies to try. Would you like to search differently, or should we pick a new topic?"
>
> Teacher: ✅ "Correct. Research requires sources."

---

## Bottom Line

### What Went Wrong with Report 4:

❌ **The system generated a report with zero sources**
- Even with excellent transparency
- Even with proper disclaimers
- Even with all the right structure

✅ **What should have happened:**
- Block report generation
- Show helpful error message
- Suggest alternatives
- NO REPORT CREATED

### Why This Matters:

1. **Credibility**: Generating sourceless reports damages trust in the workflow
2. **Quality**: No amount of formatting can compensate for lack of research
3. **Liability**: Users might act on purely speculative information
4. **Standards**: Research reports require research - this is non-negotiable

### Action Required:

**IMMEDIATELY implement source count validation as Priority 0** before any other workflow improvements. This is a blocking issue that must be fixed before the workflow can be considered reliable.

---

## Final Note

The fact that Report 4 was transparent about having no sources is commendable, but **transparency doesn't make unsourced speculation into valid research**. The workflow must enforce minimum standards rather than rely on users reading warnings.

**Analogy**: A car's safety system shouldn't just warn "brake failure" - it should prevent the car from being driven at all. Similarly, the workflow shouldn't just warn "no sources" - it should prevent report generation entirely.

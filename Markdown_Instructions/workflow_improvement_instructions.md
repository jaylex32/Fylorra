# Research Report Workflow Enhancement Instructions

## Overview
These instructions are for improving the research report generation workflow. The current output produces well-structured reports but lacks critical analysis, balanced perspectives, and confidence calibration. This document outlines systematic improvements to increase accuracy, reliability, and actionable value.

---

## Priority 1: Implement Claim Verification & Confidence Scoring

### Problem
The report makes overly optimistic claims (especially about quantum computing) without critical analysis or uncertainty acknowledgment.

### Required Changes

```python
# Add a verification step that:
1. For each major claim, search for COUNTER-EVIDENCE
2. Assign confidence scores (0-100%) to predictions
3. Flag claims that are:
   - Timeline-sensitive (e.g., "will achieve by 2026")
   - Technology-dependent (e.g., quantum computing milestones)
   - Lacking consensus in source material

# Example output format:
"Quantum computing may achieve practical advantage in specific domains 
(Confidence: 40% - highly speculative timeline)"
```

### Implementation Details

```python
def assess_claim_confidence(claim, sources):
    """
    Assess confidence level for a claim based on:
    - Number of sources supporting it
    - Consensus among sources
    - Presence of counter-evidence
    - Historical accuracy of similar predictions
    """
    confidence_factors = {
        'source_agreement': calculate_source_consensus(claim, sources),
        'counter_evidence': check_for_contradictions(claim, sources),
        'timeline_realism': assess_timeline_feasibility(claim),
        'specificity': measure_claim_specificity(claim)
    }
    
    confidence_score = weighted_average(confidence_factors)
    
    # Assign confidence labels
    if confidence_score >= 70:
        return "High confidence"
    elif confidence_score >= 40:
        return "Medium confidence"
    else:
        return "Low confidence - highly speculative"
```

---

## Priority 2: Multi-Perspective Source Analysis

### Problem
Report relies on limited sources and presents views as established facts without acknowledging diversity of perspectives.

### Required Enhancement

**Note**: The user controls the number of sources collected. The workflow should work with whatever source count is provided but should implement quality checks based on that count.

```python
# Workflow modification (adapt to user's source count setting):

def analyze_sources(sources, topic):
    """
    Works with any number of sources but provides quality warnings
    and recommendations based on count.
    """
    source_count = len(sources)
    
    # Quality assessment based on available sources
    if source_count < 3:
        warning = "⚠️ Limited sources - findings should be considered preliminary"
    elif source_count < 5:
        warning = "⚠️ Moderate source coverage - consider increasing for complex topics"
    else:
        warning = None
    
    # Source diversity analysis (works with any count)
    source_types = categorize_sources(sources)
    # Categories: industry_reports, academic, technical_blogs, news, critical_analysis
    
    diversity_score = calculate_diversity(source_types)
    
    if diversity_score < 0.3:
        warning += "\n⚠️ Low source diversity - consider adding different perspective types"
    
    return {
        'sources': sources,
        'quality_warnings': warning,
        'diversity_score': diversity_score,
        'source_breakdown': source_types
    }

# Source diversity optimization (suggest to user):
def suggest_additional_sources(topic, existing_sources):
    """
    If source count is low or diversity is lacking, suggest:
    - Contrarian/skeptical sources (search "X overhype" or "X challenges")
    - Academic papers (arxiv.org, scholar.google.com)
    - Industry analysts (Gartner, Forrester)
    - Technical practitioner blogs
    - Critical analysis pieces
    """
    pass
```

### Cross-Reference Implementation

```python
# Regardless of source count, cross-reference claims:
def cross_reference_claims(claims, sources):
    for claim in claims:
        supporting_sources = find_supporting_sources(claim, sources)
        contradicting_sources = find_contradicting_sources(claim, sources)
        
        if len(contradicting_sources) > 0:
            # FLAG: Sources disagree on this claim
            claim.add_flag("DISAGREEMENT", {
                'supporting': supporting_sources,
                'contradicting': contradicting_sources
            })
        
        if len(supporting_sources) == 1:
            # FLAG: Single-source claim
            claim.add_flag("SINGLE_SOURCE", {
                'note': 'Not corroborated by other sources'
            })
```

---

## Priority 3: Add Critical Analysis Module

### Problem
Report lacks balanced perspective, risk assessment, and consideration of implementation challenges.

### Implementation

```python
# Create new analysis sections that must be included:

def generate_critical_analysis(claims, sources):
    """
    For each major claim, generate critical analysis including:
    - Underlying assumptions
    - Dependencies and prerequisites
    - Historical precedents
    - Potential failure modes
    """
    
    critical_sections = {}
    
    for claim in claims:
        critical_sections[claim.id] = {
            'assumptions': identify_assumptions(claim),
            'dependencies': list_dependencies(claim),
            'precedents': find_historical_precedents(claim),
            'barriers': identify_implementation_barriers(claim),
            'risks': assess_risks(claim)
        }
    
    return critical_sections

# Required report subsections:
mandatory_critical_sections = [
    "Challenges & Barriers",
    "Alternative Scenarios", 
    "Risk Assessment",
    "Implementation Considerations"
]
```

### Output Format for Critical Analysis

```markdown
## Critical Analysis

### [Topic/Claim]

**Underlying Assumptions:**
- Assumes X technology will mature by Y date
- Assumes market conditions remain favorable
- Assumes regulatory environment stays permissive

**Key Dependencies:**
- Requires breakthrough in [specific area]
- Depends on [infrastructure/skills/capital] availability
- Contingent on [external factor]

**Historical Context:**
- Similar predictions in [year] resulted in [outcome]
- [Technology/approach] has historically taken X years to mature

**Potential Barriers:**
- Technical: [list technical challenges]
- Economic: [cost, ROI uncertainties]
- Organizational: [change management, skills gap]
- Regulatory: [compliance, approval timelines]

**Risk Factors:**
- High: [critical risks]
- Medium: [moderate risks]
- Low: [minor risks]
```

---

## Priority 4: Temporal Accuracy System

### Problem
Confusion between "already achieved" vs. "will achieve" (e.g., quantum advantage already demonstrated in narrow cases but report presents it as future milestone).

### Fix Required

```python
# Before making future predictions, establish current state:

def establish_temporal_context(topic):
    """
    Determine what has already been achieved vs. what is speculative
    """
    
    # Search queries to run:
    current_state_queries = [
        f"{topic} current status 2025",
        f"{topic} recent achievements",
        f"{topic} state of the art"
    ]
    
    current_state = research_queries(current_state_queries)
    
    # Categorize information by temporal status:
    return {
        'already_achieved': extract_past_accomplishments(current_state),
        'in_development': extract_active_work(current_state),
        'planned': extract_announced_plans(current_state),
        'speculative': extract_predictions(current_state)
    }

# Apply temporal markers consistently:
TEMPORAL_LANGUAGE = {
    'already_achieved': [
        "has demonstrated",
        "has achieved", 
        "currently exists",
        "is available"
    ],
    'in_development': [
        "is being developed",
        "teams are working on",
        "is in progress"
    ],
    'planned': [
        "is expected to",
        "organizations plan to",
        "is scheduled for"
    ],
    'speculative': [
        "may potentially",
        "could eventually",
        "might achieve",
        "remains to be seen"
    ]
}
```

### Verification Checkpoint

```python
# For any claim about future state:
def verify_not_already_achieved(claim):
    """
    Before stating something will happen, check if it already has
    """
    search_results = web_search(f"{claim.topic} already achieved")
    
    if evidence_of_achievement(search_results):
        return {
            'status': 'ALREADY_ACHIEVED',
            'correction': 'Reframe as current state, not future prediction',
            'evidence': search_results
        }
    
    return {'status': 'FUTURE_PREDICTION', 'verified': True}
```

---

## Priority 5: Fact-Checking Pipeline

### Problem
Technical details are vague or potentially incorrect (e.g., "Google's Titans architecture" - unclear if this exists).

### Add This Stage

```python
# After report generation, run fact-checking:

def fact_check_report(report):
    """
    Extract and verify all specific technical claims
    """
    
    # Extract specific claims
    technical_claims = extract_technical_claims(report)
    # Examples: specific products, architectures, companies, metrics
    
    verification_results = []
    
    for claim in technical_claims:
        # Search for verification
        search_query = f'"{claim.specific_term}" {claim.context}'
        results = web_search(search_query)
        
        verification = {
            'claim': claim.text,
            'verified': can_verify(results),
            'confidence': assess_verification_confidence(results),
            'sources': results[:3]  # Top 3 verification sources
        }
        
        if not verification['verified']:
            verification['flag'] = '[VERIFICATION NEEDED]'
            verification['action'] = 'Replace with verified alternative or remove'
        
        verification_results.append(verification)
    
    return verification_results

# Action on unverified claims:
def handle_unverified_claims(claim):
    """
    Options for handling unverified technical details:
    1. Replace with verified general statement
    2. Add qualifier: "According to [source], ..."
    3. Add note: "Note: Could not independently verify [X]"
    4. Remove if not essential
    """
    pass
```

### Replace Vague Statements

```python
# Transformation rules:
VAGUE_TO_SPECIFIC = {
    'approach': 'Rule: Replace with specific methodology or architecture name',
    'system': 'Rule: Replace with specific platform or technology',
    'technique': 'Rule: Replace with specific algorithm or method',
    'companies are working on': 'Rule: Name specific companies and cite source'
}

def improve_specificity(text):
    """
    Replace vague language with specific, verifiable statements
    """
    # Find vague terms
    # Search for specific examples
    # Replace with verified specifics OR add qualifier
    pass
```

---

## Priority 6: Include Missing Context

### Current Gap
No discussion of regulations, safety, sustainability, and other critical enterprise considerations.

### Add These Prompts to Analysis Stage

```python
# Mandatory context topics to research and include:

MANDATORY_CONTEXT_TOPICS = {
    'regulatory': {
        'prompts': [
            f"{topic} regulatory challenges",
            f"{topic} compliance requirements",
            "AI regulation EU AI Act",
            f"{topic} legal considerations"
        ],
        'min_paragraphs': 2
    },
    'safety': {
        'prompts': [
            f"{topic} AI safety concerns",
            f"{topic} risks and limitations",
            f"{topic} failure modes"
        ],
        'min_paragraphs': 2
    },
    'sustainability': {
        'prompts': [
            f"{topic} energy consumption",
            f"{topic} environmental impact",
            f"{topic} sustainability challenges"
        ],
        'min_paragraphs': 1
    },
    'ethics': {
        'prompts': [
            f"{topic} ethical considerations",
            f"{topic} bias concerns",
            f"{topic} fairness issues"
        ],
        'min_paragraphs': 1
    },
    'implementation': {
        'prompts': [
            f"{topic} implementation challenges",
            f"{topic} skills gap",
            f"{topic} infrastructure requirements",
            f"{topic} cost barriers"
        ],
        'min_paragraphs': 2
    }
}

def generate_context_section(topic):
    """
    For each mandatory topic, generate content
    """
    context_sections = {}
    
    for context_topic, config in MANDATORY_CONTEXT_TOPICS.items():
        # Research each topic
        findings = research_topic(config['prompts'])
        
        # Generate required paragraphs
        content = synthesize_findings(findings, 
                                     min_paragraphs=config['min_paragraphs'])
        
        context_sections[context_topic] = content
    
    return context_sections
```

### Output Format for Context Section

```markdown
## Challenges & Considerations

### Regulatory Landscape
[2+ paragraphs on regulatory challenges, compliance requirements, 
relevant legislation like EU AI Act, etc.]

### AI Safety & Risk Management
[2+ paragraphs on safety concerns, potential failure modes, 
risk mitigation strategies]

### Sustainability & Environmental Impact
[1+ paragraphs on energy consumption, carbon footprint, 
sustainability considerations]

### Ethical Considerations
[1+ paragraphs on bias, fairness, transparency, 
ethical deployment practices]

### Implementation Barriers
[2+ paragraphs on skills gaps, infrastructure requirements, 
cost considerations, organizational challenges]
```

---

## Priority 7: Confidence-Weighted Recommendations

### Problem
Recommendations are presented as if all predictions are equally likely, without acknowledging uncertainty.

### Modification

```python
# Tier recommendations by confidence level:

def generate_confidence_weighted_recommendations(analysis):
    """
    Sort recommendations by confidence and add appropriate caveats
    """
    
    recommendations = []
    
    for finding in analysis.findings:
        confidence = finding.confidence_score
        
        recommendation = {
            'action': finding.recommended_action,
            'confidence': confidence,
            'tier': categorize_confidence(confidence),
            'caveats': generate_caveats(finding),
            'timeline': suggest_timeline(finding),
            'resource_requirements': estimate_resources(finding)
        }
        
        recommendations.append(recommendation)
    
    # Sort by confidence
    recommendations.sort(key=lambda x: x['confidence'], reverse=True)
    
    return {
        'high_confidence': [r for r in recommendations if r['tier'] == 'HIGH'],
        'medium_confidence': [r for r in recommendations if r['tier'] == 'MEDIUM'],
        'low_confidence': [r for r in recommendations if r['tier'] == 'LOW']
    }

def categorize_confidence(score):
    if score >= 70:
        return 'HIGH'
    elif score >= 40:
        return 'MEDIUM'
    else:
        return 'LOW'
```

### Output Format for Recommendations

```markdown
## Recommendations

### High Confidence (>70% likelihood of value)

**🟢 [Recommendation Title]**
- **Action**: [Specific action to take]
- **Rationale**: [Why this is high confidence]
- **Timeline**: [Suggested implementation timeframe]
- **Resources**: [Required investment/team size]
- **Expected Impact**: [Quantified benefits if possible]

### Medium Confidence (40-70% likelihood of value)

**🟡 [Recommendation Title]**
- **Action**: [Specific action to take]
- **Rationale**: [Why this is medium confidence]
- **Caveats**: [What could prevent this from delivering value]
- **Timeline**: [Suggested pilot or exploration timeframe]
- **Resources**: [Required investment/team size]
- **Success Criteria**: [How to evaluate if this is working]

### Low Confidence (<40% likelihood near-term value)

**🔴 [Recommendation Title]**
- **Action**: [Specific action to take]
- **Rationale**: [Why this is included despite low confidence]
- **Risk Assessment**: [Why this is high-risk/speculative]
- **Recommended Approach**: "Monitor and reassess" OR "Small pilot only if capital available"
- **Timeline**: [Long-term exploration]
- **Warning**: [Clear statement about speculative nature]

**Example:**
🔴 **Prioritize Quantum Computing Use Cases**
- **Action**: Identify compute-intensive problems for quantum
- **Risk Assessment**: Practical quantum advantage timeline is highly uncertain
- **Recommended Approach**: Monitor developments; only pilot if you have significant R&D budget and can afford dead-end investments
- **Timeline**: 5-10+ years for practical enterprise value
- **Warning**: This is a long-term, high-risk bet. Do not allocate core operational budget.
```

---

## Priority 8: Enhanced Output Format

### Add These Sections to Every Report

```markdown
## Confidence Assessment

### High Confidence Predictions (>70%)
- [Prediction 1]: [Brief explanation of why confidence is high]
- [Prediction 2]: [Brief explanation]

### Medium Confidence Predictions (40-70%)
- [Prediction 1]: [Brief explanation of uncertainty]
- [Prediction 2]: [Brief explanation]

### Low Confidence / Speculative (<40%)
- [Prediction 1]: [Why this is highly uncertain]
- [Prediction 2]: [Why this is highly uncertain]

### Timeline Uncertainties
- [Technology/Trend]: Expected timeframe has [low/medium/high] reliability
- [Technology/Trend]: Dependent on [external factors]

---

## What We Don't Know

### Key Unknowns
- [Unknown 1]: [Why this matters and what it affects]
- [Unknown 2]: [Why this matters and what it affects]

### Data Gaps
- [Gap 1]: Limited data available on [topic]
- [Gap 2]: Conflicting information regarding [topic]

### Areas Requiring Further Research
- [Area 1]: [Why more research is needed]
- [Area 2]: [Why more research is needed]

---

## Dissenting Perspectives

### [Topic/Claim 1]
**Mainstream View**: [Summary]
**Alternative View**: [Contrarian or skeptical perspective]
**Sources**: [Citations for alternative view]

### [Topic/Claim 2]
**Mainstream View**: [Summary]
**Alternative View**: [Contrarian or skeptical perspective]
**Sources**: [Citations for alternative view]

---

## Risk Factors

### Technical Risks
- **[Risk 1]**: [Description and potential impact]
- **[Risk 2]**: [Description and potential impact]

### Business Risks
- **[Risk 1]**: [Description and potential impact]
- **[Risk 2]**: [Description and potential impact]

### Timeline Risks
- **[Risk 1]**: [Description - what if it takes longer than expected]
- **[Risk 2]**: [Description]

### Adoption Risks
- **[Risk 1]**: [Barriers to implementation]
- **[Risk 2]**: [Organizational or market resistance]
```

---

## Implementation Priority Order

Implement these improvements in the following sequence for maximum impact:

### Phase 1: Core Accuracy (Week 1)
1. **Claim Verification + Confidence Scoring** (Priority 1)
   - Highest impact on accuracy
   - Foundation for other improvements
   
2. **Fact-Checking Pipeline** (Priority 5)
   - Prevents spreading misinformation
   - Critical for credibility

### Phase 2: Balanced Analysis (Week 2)
3. **Multi-Source Collection & Cross-Referencing** (Priority 2)
   - Works with user-controlled source count
   - Improves reliability
   
4. **Critical Analysis Module** (Priority 3)
   - Adds necessary balance
   - Makes reports more actionable

### Phase 3: Completeness (Week 3)
5. **Missing Context Topics** (Priority 6)
   - Ensures comprehensive coverage
   - Addresses enterprise concerns
   
6. **Temporal Accuracy System** (Priority 4)
   - Prevents timeline confusion
   - Clarifies what's real vs. speculative

### Phase 4: Output Quality (Week 4)
7. **Confidence-Weighted Recommendations** (Priority 7)
   - Makes recommendations actionable
   - Provides honest guidance
   
8. **Enhanced Output Format** (Priority 8)
   - Improves presentation
   - Makes uncertainty visible

---

## Testing Criteria

Before marking this workflow as complete, verify it meets these standards:

### Must-Have Criteria (Blocking Issues)
- ✅ Never makes timeline predictions without confidence scores
- ✅ Includes confidence assessment section in every report
- ✅ Flags when sources disagree on claims
- ✅ Distinguishes between achieved vs. speculative developments
- ✅ Verifies all specific technical claims (products, architectures, etc.)
- ✅ Includes all mandatory context topics (regulatory, safety, sustainability, ethics, implementation)
- ✅ Provides risk assessment for all recommendations
- ✅ Tiers recommendations by confidence level

### Should-Have Criteria (Quality Issues)
- ✅ Works effectively with user-defined source count
- ✅ Includes at least one contrarian perspective per major claim
- ✅ Provides "What We Don't Know" section
- ✅ Adds appropriate caveats to low-confidence predictions
- ✅ Cross-references claims across available sources
- ✅ Replaces vague statements with specific, verifiable ones
- ✅ Includes historical context for predictions

### Quality Metrics
- **Accuracy Score**: >85% of factual claims verified
- **Balance Score**: >2 perspectives presented for controversial claims
- **Confidence Calibration**: Predictions match outcomes within confidence ranges
- **Completeness**: All mandatory sections present and substantive

---

## Code Architecture Suggestion

```python
class ImprovedResearchReportWorkflow:
    """
    Enhanced research workflow with critical analysis and confidence scoring
    """
    
    def __init__(self, config):
        # User-configurable settings
        self.source_count = config.get('source_count', 5)
        self.confidence_threshold = config.get('confidence_threshold', 0.4)
        self.include_contrarian = config.get('include_contrarian', True)
        
        # Quality gates
        self.min_verification_confidence = 0.6
        self.required_context_topics = [
            'regulatory', 'safety', 'sustainability', 
            'ethics', 'implementation'
        ]
    
    def generate_report(self, topic):
        """
        Main workflow with all enhancements
        """
        
        # Stage 1: Research with user-defined source count
        print(f"Collecting {self.source_count} sources...")
        sources = self.collect_diverse_sources(topic, self.source_count)
        
        # Quality warning if source count is low
        if self.source_count < 5:
            print(f"⚠️ Warning: Using only {self.source_count} sources - consider increasing for better coverage")
        
        # Stage 2: Establish current state (temporal accuracy)
        print("Establishing current state of technology...")
        temporal_context = self.establish_temporal_context(topic, sources)
        
        # Stage 3: Extract and verify claims
        print("Extracting claims from sources...")
        claims = self.extract_claims(sources)
        
        print("Verifying claims and searching for counter-evidence...")
        verified_claims = self.verify_each_claim(claims, sources)
        
        print("Assigning confidence scores...")
        scored_claims = self.assign_confidence_scores(verified_claims, sources)
        
        # Stage 4: Critical analysis
        print("Generating critical analysis...")
        critical_analysis = self.generate_critical_analysis(scored_claims)
        
        # Stage 5: Research mandatory context topics
        print("Researching mandatory context topics...")
        context_sections = self.generate_context_sections(topic)
        
        # Stage 6: Generate dissenting perspectives
        if self.include_contrarian:
            print("Searching for contrarian perspectives...")
            dissenting_views = self.find_dissenting_perspectives(topic, scored_claims)
        else:
            dissenting_views = None
        
        # Stage 7: Synthesize report with confidence markers
        print("Synthesizing balanced report...")
        report = self.synthesize_with_confidence(
            topic=topic,
            temporal_context=temporal_context,
            scored_claims=scored_claims,
            critical_analysis=critical_analysis,
            context_sections=context_sections,
            dissenting_views=dissenting_views
        )
        
        # Stage 8: Generate confidence-weighted recommendations
        print("Generating confidence-weighted recommendations...")
        recommendations = self.generate_tiered_recommendations(scored_claims)
        report.add_section('recommendations', recommendations)
        
        # Stage 9: Quality checks and fact-checking
        print("Running fact-checking pipeline...")
        unverified_claims = self.verify_technical_details(report)
        
        if unverified_claims:
            print(f"⚠️ Warning: {len(unverified_claims)} claims could not be verified")
            report.add_section('verification_notes', unverified_claims)
        
        # Stage 10: Flag low-confidence claims
        print("Flagging low-confidence claims...")
        low_confidence_flags = self.flag_low_confidence_claims(
            report, 
            threshold=self.confidence_threshold
        )
        
        # Stage 11: Generate enhanced sections
        print("Adding enhanced sections...")
        report.add_section('confidence_assessment', 
                          self.generate_confidence_assessment(scored_claims))
        report.add_section('unknowns', 
                          self.generate_unknowns_section(scored_claims, sources))
        report.add_section('risk_factors', 
                          self.generate_risk_assessment(scored_claims))
        
        # Final validation
        print("Validating report against quality criteria...")
        validation_results = self.validate_report(report)
        
        if not validation_results.passed:
            print("⚠️ Quality validation failed:")
            for issue in validation_results.issues:
                print(f"  - {issue}")
        
        return report
    
    # ===== Core Methods =====
    
    def collect_diverse_sources(self, topic, count):
        """
        Collect sources with diversity optimization
        """
        sources = []
        
        # Primary searches
        primary_queries = [
            f"{topic} trends 2026",
            f"{topic} enterprise adoption",
            f"{topic} predictions"
        ]
        
        for query in primary_queries:
            results = web_search(query)
            sources.extend(results[:count//3])
        
        # Add contrarian sources if enabled
        if self.include_contrarian:
            contrarian_queries = [
                f"{topic} challenges",
                f"{topic} overhype",
                f"{topic} limitations"
            ]
            
            for query in contrarian_queries:
                results = web_search(query)
                sources.extend(results[:1])  # Add 1 contrarian source per query
        
        # Assess diversity
        diversity_assessment = self.assess_source_diversity(sources)
        
        return sources[:count], diversity_assessment
    
    def verify_each_claim(self, claims, sources):
        """
        Verify each claim and search for counter-evidence
        """
        verified = []
        
        for claim in claims:
            # Search for counter-evidence
            counter_query = f"{claim.topic} challenges limitations problems"
            counter_evidence = web_search(counter_query)
            
            # Check for contradictions in sources
            contradictions = self.find_contradictions(claim, sources)
            
            claim.verification = {
                'counter_evidence': counter_evidence,
                'contradictions': contradictions,
                'single_source': len(claim.supporting_sources) == 1
            }
            
            verified.append(claim)
        
        return verified
    
    def assign_confidence_scores(self, claims, sources):
        """
        Assign 0-100 confidence scores to claims
        """
        for claim in claims:
            factors = {
                'source_agreement': self.calculate_source_consensus(claim, sources),
                'counter_evidence': self.assess_counter_evidence(claim),
                'timeline_realism': self.assess_timeline_feasibility(claim),
                'specificity': self.measure_claim_specificity(claim),
                'verification': self.assess_verification_quality(claim)
            }
            
            # Weighted average
            weights = {'source_agreement': 0.3, 'counter_evidence': 0.25, 
                      'timeline_realism': 0.25, 'specificity': 0.1,
                      'verification': 0.1}
            
            score = sum(factors[k] * weights[k] for k in factors.keys())
            
            claim.confidence_score = score
            claim.confidence_label = self.get_confidence_label(score)
        
        return claims
    
    def generate_critical_analysis(self, claims):
        """
        Generate critical analysis for each major claim
        """
        analysis = {}
        
        for claim in claims:
            analysis[claim.id] = {
                'assumptions': self.identify_assumptions(claim),
                'dependencies': self.list_dependencies(claim),
                'precedents': self.find_historical_precedents(claim),
                'barriers': self.identify_barriers(claim),
                'risks': self.assess_claim_risks(claim)
            }
        
        return analysis
    
    def generate_context_sections(self, topic):
        """
        Generate all mandatory context sections
        """
        context = {}
        
        for context_topic, config in self.required_context_topics.items():
            findings = self.research_context_topic(topic, config)
            context[context_topic] = self.synthesize_context(findings, config)
        
        return context
    
    def validate_report(self, report):
        """
        Validate report against quality criteria
        """
        issues = []
        
        # Check for required sections
        required_sections = [
            'confidence_assessment', 'unknowns', 
            'risk_factors', 'challenges_and_considerations'
        ]
        
        for section in required_sections:
            if section not in report.sections:
                issues.append(f"Missing required section: {section}")
        
        # Check for confidence scores
        if not all(hasattr(claim, 'confidence_score') for claim in report.claims):
            issues.append("Not all claims have confidence scores")
        
        # Check for verification
        unverified_count = sum(1 for claim in report.claims 
                             if not claim.verification.get('verified', False))
        
        if unverified_count > len(report.claims) * 0.15:  # More than 15% unverified
            issues.append(f"{unverified_count} claims unverified (>15% threshold)")
        
        return ValidationResult(
            passed=len(issues) == 0,
            issues=issues
        )
    
    # ===== Helper Methods =====
    
    def get_confidence_label(self, score):
        if score >= 70:
            return "High confidence"
        elif score >= 40:
            return "Medium confidence"
        else:
            return "Low confidence - highly speculative"
    
    def calculate_source_consensus(self, claim, sources):
        """Calculate agreement level among sources (0-1)"""
        supporting = sum(1 for s in sources if self.supports_claim(s, claim))
        return supporting / len(sources) if sources else 0
    
    def assess_timeline_feasibility(self, claim):
        """Assess if timeline is realistic based on historical data (0-1)"""
        # Implementation would check historical precedents
        # for similar technology adoption timelines
        pass
    
    def find_contradictions(self, claim, sources):
        """Find sources that contradict the claim"""
        # Implementation would use semantic similarity
        # to find contradicting information
        pass

# Usage example:
config = {
    'source_count': 7,  # User-configurable
    'confidence_threshold': 0.4,
    'include_contrarian': True
}

workflow = ImprovedResearchReportWorkflow(config)
report = workflow.generate_report("AI trends 2026")
```

---

## Expected Outcomes

After implementing these improvements, research reports should:

1. **Be More Accurate**
   - No claims without confidence scores
   - All technical details verified
   - Clear distinction between fact and speculation

2. **Be More Balanced**
   - Include contrarian perspectives
   - Acknowledge unknowns and uncertainties
   - Present risks alongside opportunities

3. **Be More Actionable**
   - Recommendations tiered by confidence
   - Clear risk assessments
   - Realistic timelines with caveats

4. **Be More Comprehensive**
   - Include regulatory, safety, sustainability context
   - Address implementation challenges
   - Cover technical, business, and organizational factors

5. **Be More Honest**
   - Explicit about speculation
   - Clear about data limitations
   - Transparent about disagreements in sources

---

## Bottom Line

**Make the workflow more skeptical, more thorough, and more honest about uncertainty.** The current output reads like promotional material; we need rigorous analysis instead.

The goal is not to produce longer reports, but to produce **more reliable, more balanced, and more actionable** reports that decision-makers can trust.

---

## Questions or Issues?

If you encounter any challenges implementing these improvements or need clarification on any section, document your questions and we'll review together. Focus on getting Phase 1 (Core Accuracy) working first, as it provides the foundation for everything else.

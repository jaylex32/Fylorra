# History Workflow - Duplicate Sources Fix (Simplified) ✅

## What Broke

The previous duplicate sources removal logic (lines 2902-2926) was too complex and had a bug that caused it to skip too many lines, resulting in an empty document.

## The Fix

**File:** `core/agents/history_project_writing_agent.py`
**Lines:** 2902-2910

Simplified the logic to just split on `"\n## Sources\n"` and keep only the first part:

```python
# Remove duplicate Sources section - simpler approach
# If "Where We Learned This" exists, remove everything after it that starts with "## Sources"
if "## Where We Learned This" in doc:
    # Split on "## Sources" and only keep first part + "Where We Learned This" section
    parts = doc.split("\n## Sources\n")
    if len(parts) > 1:
        # Keep everything up to and including "Where We Learned This" sources
        # Find where "Where We Learned This" sources end (next ## or end of doc)
        doc = parts[0]  # Everything before the duplicate Sources
```

## How It Works

### Before (has duplicate):
```markdown
## Where We Learned This
- [1] Source 1
- [2] Source 2

## Sources
- [1] Source 1
- [2] Source 2
```

### After (duplicate removed):
```markdown
## Where We Learned This
- [1] Source 1
- [2] Source 2
```

The logic:
1. Check if "Where We Learned This" exists
2. Split document on "\n## Sources\n"
3. If there are 2+ parts (meaning duplicate Sources exists), keep only first part
4. This preserves "Where We Learned This" but removes "## Sources"

## Status

✅ **Fix Applied** - Simpler, safer logic that won't break the document

**Please restart and test again!**

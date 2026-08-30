# Automation Workflow Feature - Implementation Instructions for AI Coder

## Overview

You will implement a **Multi-Agent Automation Workflow** system for Fylorra. This allows users to create pipelines where specialized AI agents work sequentially (Research → Writing → Validation → Export).

**CRITICAL REQUIREMENTS:**
- ✅ DO NOT modify existing templates, workflow_runner.py, or workflow_actions.py
- ✅ Create NEW modules alongside existing code
- ✅ Use Pydantic library for validation (NOT Pydantic AI framework)
- ✅ Maintain local-first, privacy-focused architecture (no cloud APIs)
- ✅ Work with existing llama-cpp-python integration
- ✅ Follow existing code patterns and naming conventions

---

## Phase 1: Core Infrastructure Setup

### Step 1.1: Install Dependencies

**File**: `requirements.txt`

**Action**: ADD these lines (don't remove existing dependencies):

```txt
# Automation Workflow Dependencies
pydantic>=2.0.0
instructor>=1.0.0
httpx>=0.27.0
```

**Verification**: Run `pip install -r requirements.txt` to ensure no conflicts.

---

### Step 1.2: Create Directory Structure

**Action**: CREATE the following directory structure:

```
core/
├── pipeline/                      # NEW - Pipeline system
│   ├── __init__.py
│   ├── models.py                  # Pydantic models for validation
│   ├── context.py                 # Pipeline context and data flow
│   ├── agent.py                   # Base agent class
│   ├── stage.py                   # Pipeline stage definition
│   ├── pipeline.py                # Pipeline definition
│   ├── orchestrator.py            # Pipeline executor
│   └── triggers.py                # Trigger system
│
├── agents/                        # NEW - Specialized agents
│   ├── __init__.py
│   ├── research_agent.py
│   ├── writing_agent.py
│   ├── validation_agent.py
│   └── export_agent.py
│
├── pipeline_templates/            # NEW - Predefined workflows
│   └── research_to_report.json
│
qt_app/                            # Existing Qt UI
├── dialogs/                       # NEW - Workflow dialogs
│   ├── __init__.py
│   ├── automation_workflow_dialog.py
│   ├── pipeline_builder_dialog.py
│   └── pipeline_execution_dialog.py
```

**Important**: These are NEW modules. Do NOT modify existing files like:
- ❌ `core/workflow_runner.py` (keep as-is)
- ❌ `core/workflow_actions.py` (keep as-is)
- ❌ `core/monitor_manager.py` (keep as-is)

---

## Phase 2: Pydantic Models (Validation Layer)

### Step 2.1: Create Core Data Models

**File**: `core/pipeline/models.py` (NEW FILE)

**Implementation**:

```python
"""
Pydantic models for automation workflow data validation.
Ensures type safety and data integrity across pipeline stages.
"""

from pydantic import BaseModel, Field, validator, HttpUrl
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime
from pathlib import Path
from enum import Enum


# ============================================================================
# Agent Results
# ============================================================================

class AgentResult(BaseModel):
    """Base result from any agent execution"""
    success: bool
    data: Dict[str, Any]
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    execution_time_seconds: float = 0.0
    tokens_used: int = 0

    @validator('data')
    def validate_data_not_empty_on_success(cls, v, values):
        if values.get('success') and not v:
            raise ValueError('Successful results must contain data')
        return v


# ============================================================================
# Research Agent Models
# ============================================================================

class ResearchFinding(BaseModel):
    """Single research finding from a source"""
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=10)
    source_url: str  # HttpUrl causes issues with some URLs, use str with validation
    credibility_score: float = Field(ge=0.0, le=1.0, default=0.5)
    date: Optional[str] = None
    domain_reputation: Optional[Literal['high', 'medium', 'low', 'unknown']] = 'unknown'

    @validator('source_url')
    def validate_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v

    @validator('content')
    def validate_content_quality(cls, v):
        if len(v.split()) < 5:
            raise ValueError('Content must have at least 5 words')
        return v


class ResearchOutput(BaseModel):
    """Output from Research Agent"""
    query: str = Field(min_length=1)
    findings: List[ResearchFinding] = Field(min_items=1, max_items=50)
    summary: str = Field(min_length=50)
    total_sources: int = Field(ge=1)
    search_duration_seconds: float = Field(ge=0.0)

    @validator('total_sources')
    def validate_sources_match_findings(cls, v, values):
        if 'findings' in values and v != len(values['findings']):
            raise ValueError('total_sources must match number of findings')
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "query": "AI trends 2026",
                "findings": [
                    {
                        "title": "Latest AI Developments",
                        "content": "Artificial intelligence continues to evolve...",
                        "source_url": "https://example.com/article",
                        "credibility_score": 0.85
                    }
                ],
                "summary": "Recent AI trends show...",
                "total_sources": 1,
                "search_duration_seconds": 45.2
            }
        }


# ============================================================================
# Writing Agent Models
# ============================================================================

class DocumentSection(BaseModel):
    """Single section in a document"""
    heading: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=10)
    citations: List[int] = Field(default_factory=list)
    word_count: int = Field(ge=0, default=0)

    @validator('word_count', always=True)
    def calculate_word_count(cls, v, values):
        if 'content' in values:
            return len(values['content'].split())
        return 0


class WritingOutput(BaseModel):
    """Output from Writing Agent"""
    title: str = Field(min_length=1, max_length=300)
    sections: List[DocumentSection] = Field(min_items=1)
    references: List[str] = Field(default_factory=list)
    word_count: int = Field(ge=0)
    format: Literal['markdown', 'html', 'text'] = 'markdown'
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @validator('word_count', always=True)
    def calculate_total_word_count(cls, v, values):
        if 'sections' in values:
            return sum(s.word_count for s in values['sections'])
        return 0

    class Config:
        json_schema_extra = {
            "example": {
                "title": "AI Trends in 2026: A Comprehensive Report",
                "sections": [
                    {
                        "heading": "Introduction",
                        "content": "This report examines...",
                        "citations": [0, 1],
                        "word_count": 150
                    }
                ],
                "references": ["https://example.com/source1"],
                "word_count": 150,
                "format": "markdown"
            }
        }


# ============================================================================
# Validation Agent Models
# ============================================================================

class ValidationCheck(BaseModel):
    """Single validation check result"""
    name: str
    score: float = Field(ge=0.0, le=1.0)
    passed: bool
    issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


class ValidationOutput(BaseModel):
    """Output from Validation Agent"""
    overall_score: float = Field(ge=0.0, le=1.0)
    checks: Dict[str, ValidationCheck]
    corrections_made: List[str] = Field(default_factory=list)
    validated_document: Dict[str, Any]
    ready_for_export: bool = False

    @validator('ready_for_export', always=True)
    def determine_export_readiness(cls, v, values):
        if 'overall_score' in values:
            return values['overall_score'] >= 0.8
        return False

    @validator('overall_score', always=True)
    def calculate_overall_score(cls, v, values):
        if 'checks' in values and values['checks']:
            scores = [check.score for check in values['checks'].values()]
            return sum(scores) / len(scores) if scores else 0.0
        return v


# ============================================================================
# Export Agent Models
# ============================================================================

class ExportedFile(BaseModel):
    """Single exported file"""
    format: Literal['pdf', 'docx', 'md', 'html', 'txt']
    path: str
    size_bytes: int = Field(ge=0)
    created_at: datetime = Field(default_factory=datetime.now)

    @validator('path')
    def validate_path_exists(cls, v):
        if not Path(v).exists():
            raise ValueError(f'Exported file does not exist: {v}')
        return v


class ExportOutput(BaseModel):
    """Output from Export Agent"""
    exported_files: List[ExportedFile] = Field(min_items=1)
    export_count: int = Field(ge=1)
    total_size_bytes: int = Field(ge=0)

    @validator('export_count', always=True)
    def validate_export_count(cls, v, values):
        if 'exported_files' in values:
            return len(values['exported_files'])
        return v

    @validator('total_size_bytes', always=True)
    def calculate_total_size(cls, v, values):
        if 'exported_files' in values:
            return sum(f.size_bytes for f in values['exported_files'])
        return 0


# ============================================================================
# Pipeline Configuration Models
# ============================================================================

class StageConfig(BaseModel):
    """Configuration for a pipeline stage"""
    approval_required: bool = False
    approval_message: str = "Review output before continuing?"
    retry_on_failure: bool = True
    max_retries: int = Field(default=3, ge=1, le=10)
    timeout_seconds: int = Field(default=300, ge=30, le=3600)
    skip_if_previous_failed: bool = False
    condition: Optional[Dict[str, Any]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "approval_required": False,
                "retry_on_failure": True,
                "max_retries": 3,
                "timeout_seconds": 300
            }
        }


class PipelineStageConfig(BaseModel):
    """Complete stage configuration for JSON templates"""
    stage_id: str = Field(pattern=r'^[a-z_]+$')
    name: str = Field(min_length=1, max_length=100)
    agent_type: str = Field(pattern=r'^[A-Z][a-zA-Z]+Agent$')
    agent_config: Dict[str, Any] = Field(default_factory=dict)
    config: StageConfig = Field(default_factory=StageConfig)
    input_mapping: Optional[Dict[str, Any]] = None


class PipelineMetadata(BaseModel):
    """Pipeline metadata for templates"""
    pipeline_id: str = Field(pattern=r'^[a-z0-9_-]+$')
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    category: Literal['research', 'content', 'automation', 'analysis', 'custom'] = 'custom'
    author: str = "Fylorra"
    version: str = "1.0.0"
    created_date: str = Field(default_factory=lambda: datetime.now().isoformat())
    tags: List[str] = Field(default_factory=list)


class PipelineTemplate(BaseModel):
    """Complete pipeline template (JSON schema)"""
    metadata: PipelineMetadata
    stages: List[PipelineStageConfig] = Field(min_items=1, max_items=20)
    trigger: Optional[Dict[str, Any]] = None
    global_config: Dict[str, Any] = Field(default_factory=dict)

    @validator('stages')
    def validate_unique_stage_ids(cls, v):
        stage_ids = [s.stage_id for s in v]
        if len(stage_ids) != len(set(stage_ids)):
            raise ValueError('Stage IDs must be unique')
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "metadata": {
                    "pipeline_id": "research_to_report",
                    "name": "Research to Professional Report",
                    "description": "Automated research and report generation",
                    "category": "research"
                },
                "stages": [
                    {
                        "stage_id": "research_stage",
                        "name": "Web Research",
                        "agent_type": "ResearchAgent",
                        "agent_config": {"max_sources": 10}
                    }
                ]
            }
        }


# ============================================================================
# Pipeline Execution Models
# ============================================================================

class StageResult(BaseModel):
    """Result from a single stage execution"""
    stage_id: str
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_seconds: float = Field(ge=0.0)
    timestamp: datetime = Field(default_factory=datetime.now)
    aborted: bool = False
    abort_reason: Optional[str] = None


class PipelineResult(BaseModel):
    """Final result from pipeline execution"""
    execution_id: str
    pipeline_id: str
    success: bool
    outputs: Dict[str, Any] = Field(default_factory=dict)
    errors: List[Dict[str, str]] = Field(default_factory=list)
    total_duration_seconds: float = Field(ge=0.0)
    completed_at: Optional[str] = None
    aborted: bool = False
    abort_reason: Optional[str] = None
```

**Verification**:
- Import this module: `from core.pipeline.models import ResearchOutput`
- Create test instance: `ResearchOutput(query="test", findings=[...], summary="...", total_sources=1, search_duration_seconds=1.0)`
- Should raise validation errors if data is invalid

---

### Step 2.2: Create Pipeline Context

**File**: `core/pipeline/context.py` (NEW FILE)

**Implementation**:

```python
"""
Pipeline context manages data flow between stages.
Each pipeline execution has one context instance that persists across all stages.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import json


@dataclass
class PipelineContext:
    """
    Shared context passed between pipeline stages.
    Manages data flow, temporary files, and execution state.
    """

    # Core identification
    pipeline_id: str
    execution_id: str
    user_request: str
    initial_parameters: Dict[str, Any]

    # Stage results (key: stage_id, value: stage output data)
    stage_outputs: Dict[str, Any] = field(default_factory=dict)
    stage_metadata: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Workspace
    working_directory: Path = field(default_factory=lambda: Path.cwd())
    temp_files: List[Path] = field(default_factory=list)

    # Control flow
    current_stage: int = 0
    total_stages: int = 0
    should_abort: bool = False
    abort_reason: Optional[str] = None

    # User interaction
    approval_pending: bool = False
    approval_data: Optional[Dict[str, Any]] = None

    # Execution tracking
    started_at: datetime = field(default_factory=datetime.now)
    stage_history: List[str] = field(default_factory=list)

    def get_previous_output(self, stage_id: str) -> Optional[Any]:
        """
        Retrieve output from a specific stage.

        Args:
            stage_id: ID of the stage whose output to retrieve

        Returns:
            Stage output data, or None if stage hasn't executed
        """
        return self.stage_outputs.get(stage_id)

    def get_all_outputs(self) -> Dict[str, Any]:
        """Get all stage outputs (for final processing or debugging)"""
        return self.stage_outputs.copy()

    def get_latest_output(self) -> Optional[Any]:
        """Get the most recent stage output"""
        if not self.stage_history:
            return None
        last_stage_id = self.stage_history[-1]
        return self.stage_outputs.get(last_stage_id)

    def add_stage_output(self, stage_id: str, output_data: Any, metadata: Optional[Dict] = None):
        """
        Store stage output and metadata.

        Args:
            stage_id: Unique identifier for the stage
            output_data: Data produced by the stage (typically Pydantic model.dict())
            metadata: Optional metadata (duration, tokens, etc.)
        """
        self.stage_outputs[stage_id] = output_data
        self.stage_history.append(stage_id)

        if metadata:
            self.stage_metadata[stage_id] = metadata

    def add_temp_file(self, file_path: Path):
        """Track temporary file for cleanup"""
        if file_path not in self.temp_files:
            self.temp_files.append(file_path)

    def cleanup(self):
        """Remove all temporary files"""
        for file_path in self.temp_files:
            try:
                if file_path.exists():
                    if file_path.is_file():
                        file_path.unlink()
                    elif file_path.is_dir():
                        import shutil
                        shutil.rmtree(file_path)
            except Exception as e:
                print(f"Warning: Failed to cleanup {file_path}: {e}")

    def abort(self, reason: str):
        """Signal pipeline to abort"""
        self.should_abort = True
        self.abort_reason = reason

    def to_dict(self) -> Dict[str, Any]:
        """Serialize context to dictionary (for logging/debugging)"""
        return {
            "pipeline_id": self.pipeline_id,
            "execution_id": self.execution_id,
            "user_request": self.user_request,
            "current_stage": self.current_stage,
            "total_stages": self.total_stages,
            "stage_history": self.stage_history,
            "should_abort": self.should_abort,
            "abort_reason": self.abort_reason,
            "started_at": self.started_at.isoformat(),
        }

    def save_checkpoint(self, checkpoint_path: Path):
        """Save context state for recovery (optional feature)"""
        checkpoint_data = {
            **self.to_dict(),
            "stage_outputs": self.stage_outputs,
            "stage_metadata": self.stage_metadata,
        }

        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, indent=2, default=str)

    @classmethod
    def load_checkpoint(cls, checkpoint_path: Path) -> 'PipelineContext':
        """Load context from checkpoint (optional feature)"""
        with open(checkpoint_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Reconstruct context
        context = cls(
            pipeline_id=data['pipeline_id'],
            execution_id=data['execution_id'],
            user_request=data['user_request'],
            initial_parameters=data.get('initial_parameters', {}),
            working_directory=Path(data.get('working_directory', Path.cwd())),
        )

        context.stage_outputs = data.get('stage_outputs', {})
        context.stage_metadata = data.get('stage_metadata', {})
        context.current_stage = data.get('current_stage', 0)
        context.total_stages = data.get('total_stages', 0)
        context.stage_history = data.get('stage_history', [])

        return context
```

---

## Phase 3: Base Agent Class

### Step 3.1: Create Abstract Agent

**File**: `core/pipeline/agent.py` (NEW FILE)

**Implementation**:

```python
"""
Base agent class for all pipeline agents.
Agents perform specific tasks (research, writing, etc.) within a pipeline.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass
from core.pipeline.context import PipelineContext
from core.pipeline.models import AgentResult
import time


@dataclass
class AgentCapability:
    """Defines what an agent can do"""
    capability_id: str
    name: str
    description: str
    input_types: list[str]  # e.g., ["text", "json", "file"]
    output_types: list[str]  # e.g., ["json", "file"]
    requires_internet: bool = False
    estimated_time_seconds: int = 60


class PipelineAgent(ABC):
    """
    Base class for all pipeline agents.

    Agents are specialized processors that perform one task in a workflow.
    Each agent receives a PipelineContext and produces validated output.
    """

    def __init__(
        self,
        agent_id: str,
        role: str,
        system_prompt: str,
        capabilities: list[AgentCapability],
        config: Dict[str, Any],
        ai_manager: Optional[Any] = None
    ):
        """
        Initialize agent.

        Args:
            agent_id: Unique identifier (e.g., "research_agent")
            role: Human-readable role (e.g., "researcher")
            system_prompt: LLM system prompt for this agent's behavior
            capabilities: List of what this agent can do
            config: Agent-specific configuration
            ai_manager: Reference to AIManager for LLM access
        """
        self.agent_id = agent_id
        self.role = role
        self.system_prompt = system_prompt
        self.capabilities = capabilities
        self.config = config
        self.ai_manager = ai_manager

    @abstractmethod
    def execute(self, context: PipelineContext) -> AgentResult:
        """
        Execute agent's task with given context.

        Args:
            context: Pipeline context with shared data

        Returns:
            AgentResult with success status and validated data

        Raises:
            Exception: If execution fails critically
        """
        pass

    def validate_input(self, context: PipelineContext) -> bool:
        """
        Verify input data matches expected schema.

        Override this to add custom validation before execute().

        Args:
            context: Pipeline context

        Returns:
            True if input is valid, False otherwise
        """
        return True

    def get_input_data(self, context: PipelineContext) -> Any:
        """
        Extract input data for this agent from context.

        Default behavior: return latest stage output.
        Override for custom input mapping.

        Args:
            context: Pipeline context

        Returns:
            Input data for this agent
        """
        return context.get_latest_output()

    def format_output(self, raw_output: Any) -> Dict[str, Any]:
        """
        Format raw output for next stage.

        Override this to transform output before storing in context.

        Args:
            raw_output: Raw output from agent execution

        Returns:
            Formatted dictionary for context storage
        """
        if hasattr(raw_output, 'dict'):
            # Pydantic model
            return raw_output.dict()
        return raw_output

    def estimate_duration(self) -> int:
        """
        Estimate execution time in seconds.

        Returns:
            Estimated seconds for this agent's task
        """
        if self.capabilities:
            return self.capabilities[0].estimated_time_seconds
        return 60

    def on_start(self, context: PipelineContext):
        """Hook called before execute(). Override for setup logic."""
        pass

    def on_complete(self, context: PipelineContext, result: AgentResult):
        """Hook called after successful execute(). Override for cleanup."""
        pass

    def on_error(self, context: PipelineContext, error: Exception):
        """Hook called on execution error. Override for error handling."""
        pass

    def __repr__(self):
        return f"<{self.__class__.__name__} id={self.agent_id} role={self.role}>"
```

**Verification**:
- This is an abstract class, so you can't instantiate it directly
- Next step will create concrete agents that inherit from this

---

## Phase 4: Integration with Existing AIManager

### Step 4.1: Extend AIManager (Safe Pattern)

**IMPORTANT**: Do NOT modify `core/ai_manager.py` directly. Instead, create a wrapper.

**File**: `core/pipeline/ai_adapter.py` (NEW FILE)

**Implementation**:

```python
"""
Adapter for using AIManager with pipeline agents.
Provides structured output support without modifying original AIManager.
"""

import json
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel
from core.ai_manager import AIManager


class PipelineAIAdapter:
    """
    Wrapper around AIManager that adds structured output support.
    Uses existing AIManager without modification.
    """

    def __init__(self, ai_manager: AIManager):
        """
        Initialize adapter.

        Args:
            ai_manager: Existing AIManager instance from Fylorra
        """
        self.ai_manager = ai_manager

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[BaseModel],
        max_tokens: int = 2000,
        temperature: float = 0.7,
        max_retries: int = 3
    ) -> BaseModel:
        """
        Generate structured output validated against Pydantic model.

        Args:
            system_prompt: System instructions for the LLM
            user_prompt: User message/query
            response_model: Pydantic model class for validation
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            max_retries: Number of validation retry attempts

        Returns:
            Validated Pydantic model instance

        Raises:
            ValueError: If output doesn't match schema after retries
        """

        # Build prompt that encourages JSON output
        json_prompt = f"""{user_prompt}

CRITICAL: You must respond with ONLY valid JSON that matches this schema:
{response_model.schema_json(indent=2)}

Do not include any explanations, markdown formatting, or additional text.
Output only the JSON object."""

        for attempt in range(max_retries):
            try:
                # Use existing AIManager
                response = self.ai_manager.generate_response(
                    prompt=json_prompt,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature
                )

                # Clean response (remove markdown code blocks if present)
                cleaned = self._extract_json(response)

                # Parse and validate
                data = json.loads(cleaned)
                validated = response_model(**data)
                return validated

            except (json.JSONDecodeError, ValueError) as e:
                if attempt == max_retries - 1:
                    raise ValueError(
                        f"Failed to get valid JSON after {max_retries} attempts. "
                        f"Last error: {e}. Response: {response[:200]}"
                    )
                # Retry with more explicit instructions
                json_prompt += "\n\nREMINDER: Output ONLY valid JSON, no other text."

        raise ValueError("Unexpected error in generate_structured")

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.7
    ) -> str:
        """
        Generate plain text response (passthrough to AIManager).

        Args:
            system_prompt: System instructions
            user_prompt: User message
            max_tokens: Maximum tokens
            temperature: Sampling temperature

        Returns:
            Generated text
        """
        return self.ai_manager.generate_response(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature
        )

    def _extract_json(self, text: str) -> str:
        """
        Extract JSON from response that might have markdown formatting.

        Args:
            text: Raw LLM response

        Returns:
            Cleaned JSON string
        """
        text = text.strip()

        # Remove markdown code blocks
        if text.startswith('```json'):
            text = text[7:]
        elif text.startswith('```'):
            text = text[3:]

        if text.endswith('```'):
            text = text[:-3]

        return text.strip()

    def analyze_image(
        self,
        image_path: str,
        prompt: str,
        max_tokens: int = 500
    ) -> str:
        """
        Analyze image using vision model (passthrough to AIManager).

        Args:
            image_path: Path to image file
            prompt: Analysis prompt
            max_tokens: Maximum tokens

        Returns:
            Analysis text
        """
        return self.ai_manager.analyze_image(
            image_path=image_path,
            prompt=prompt,
            max_tokens=max_tokens
        )
```

**Usage Pattern**:
```python
# In agents, use the adapter
from core.pipeline.ai_adapter import PipelineAIAdapter
from core.pipeline.models import ResearchOutput

adapter = PipelineAIAdapter(ai_manager)
result = adapter.generate_structured(
    system_prompt="You are a researcher",
    user_prompt="Research AI trends",
    response_model=ResearchOutput
)
# result is validated ResearchOutput instance
```

---

## Phase 5: Create Specialized Agents

### Step 5.1: Research Agent (Stub Implementation)

**File**: `core/agents/research_agent.py` (NEW FILE)

**Implementation**:

```python
"""
Research Agent - Performs web research and compiles findings.

NOTE: This is a STUB implementation for Phase 1.
Web search integration will be added in Phase 2.
"""

from typing import Any, Dict
import time
from datetime import datetime

from core.pipeline.agent import PipelineAgent, AgentCapability
from core.pipeline.context import PipelineContext
from core.pipeline.models import AgentResult, ResearchOutput, ResearchFinding
from core.pipeline.ai_adapter import PipelineAIAdapter


class ResearchAgent(PipelineAgent):
    """
    Performs web research and organizes findings.

    Capabilities:
    - Web search (multiple sources)
    - Content extraction
    - Source credibility assessment
    - Data organization

    Input: User query/topic from context.initial_parameters["query"]
    Output: ResearchOutput with findings and summary
    """

    def __init__(self, config: Dict[str, Any], ai_manager: Any):
        super().__init__(
            agent_id="research_agent",
            role="researcher",
            system_prompt="""You are a professional research assistant.
Your task is to search for information and compile comprehensive research findings.

For each finding, provide:
- title: Clear, descriptive title
- content: Detailed summary of the information
- source_url: URL of the source
- credibility_score: 0.0-1.0 rating of source reliability
- date: Publication date if available

Focus on accuracy, breadth, and proper attribution.""",
            capabilities=[
                AgentCapability(
                    capability_id="web_research",
                    name="Web Research",
                    description="Search and extract web content",
                    input_types=["text"],
                    output_types=["json"],
                    requires_internet=True,
                    estimated_time_seconds=60
                )
            ],
            config=config,
            ai_manager=ai_manager
        )
        self.adapter = PipelineAIAdapter(ai_manager)

    def execute(self, context: PipelineContext) -> AgentResult:
        """
        Perform research on the given query.

        Args:
            context: Pipeline context with initial_parameters["query"]

        Returns:
            AgentResult with ResearchOutput data
        """
        start_time = time.time()

        try:
            # Extract query from context
            query = context.initial_parameters.get("query", context.user_request)
            max_sources = self.config.get("max_sources", 5)

            # STUB: For Phase 1, generate mock research data
            # In Phase 2, replace with actual web search
            findings_data = self._perform_mock_research(query, max_sources)

            # Generate summary using AI
            summary = self._generate_summary(findings_data, query)

            # Create validated output
            research_output = ResearchOutput(
                query=query,
                findings=findings_data,
                summary=summary,
                total_sources=len(findings_data),
                search_duration_seconds=time.time() - start_time
            )

            return AgentResult(
                success=True,
                data=research_output.dict(),
                execution_time_seconds=time.time() - start_time
            )

        except Exception as e:
            return AgentResult(
                success=False,
                data={},
                error=str(e),
                execution_time_seconds=time.time() - start_time
            )

    def _perform_mock_research(self, query: str, max_sources: int) -> list[ResearchFinding]:
        """
        STUB: Generate mock research data for testing.
        Replace with actual web search in Phase 2.
        """
        mock_findings = [
            ResearchFinding(
                title=f"Research Finding {i+1} on {query}",
                content=f"This is detailed information about {query}. "
                        f"It covers various aspects including background, "
                        f"current state, and future implications. "
                        f"The research indicates significant developments in this area.",
                source_url=f"https://example.com/article-{i+1}",
                credibility_score=0.7 + (i * 0.05),
                date=datetime.now().strftime("%Y-%m-%d"),
                domain_reputation="medium"
            )
            for i in range(min(max_sources, 5))
        ]
        return mock_findings

    def _generate_summary(self, findings: list[ResearchFinding], query: str) -> str:
        """Generate executive summary of research findings using AI"""

        findings_text = "\n\n".join([
            f"Source {i+1}: {f.title}\n{f.content}"
            for i, f in enumerate(findings)
        ])

        prompt = f"""Based on the following research findings about "{query}",
write a comprehensive executive summary (100-200 words):

{findings_text}

Provide a clear, professional summary that synthesizes the key information."""

        summary = self.adapter.generate_text(
            system_prompt=self.system_prompt,
            user_prompt=prompt,
            max_tokens=500,
            temperature=0.7
        )

        return summary.strip()
```

**Note**: This is a stub. Web search will be implemented later. For now, it generates mock data to test the pipeline.

---

### Step 5.2: Writing Agent

**File**: `core/agents/writing_agent.py` (NEW FILE)

**Implementation**:

```python
"""
Writing Agent - Transforms research into professional documents.
"""

from typing import Any, Dict
import time

from core.pipeline.agent import PipelineAgent, AgentCapability
from core.pipeline.context import PipelineContext
from core.pipeline.models import AgentResult, WritingOutput, DocumentSection, ResearchOutput
from core.pipeline.ai_adapter import PipelineAIAdapter


class WritingAgent(PipelineAgent):
    """
    Transforms raw research into polished professional content.

    Capabilities:
    - Professional writing
    - Document structuring
    - Citation management
    - Style adaptation

    Input: ResearchOutput from previous stage
    Output: WritingOutput with structured document
    """

    def __init__(self, config: Dict[str, Any], ai_manager: Any):
        super().__init__(
            agent_id="writing_agent",
            role="writer",
            system_prompt="""You are a professional writer and editor.
Your task is to transform research findings into polished, well-structured documents.

Guidelines:
- Create clear sections with descriptive headings
- Maintain professional tone and style
- Ensure logical flow and coherence
- Preserve all factual information and citations
- Write clearly, concisely, and engagingly

Always cite sources using [0], [1], etc. notation.""",
            capabilities=[
                AgentCapability(
                    capability_id="content_writing",
                    name="Professional Writing",
                    description="Transform research into polished content",
                    input_types=["json"],
                    output_types=["markdown", "text"],
                    requires_internet=False,
                    estimated_time_seconds=120
                )
            ],
            config=config,
            ai_manager=ai_manager
        )
        self.adapter = PipelineAIAdapter(ai_manager)

    def execute(self, context: PipelineContext) -> AgentResult:
        """
        Create professional document from research.

        Args:
            context: Pipeline context with research_stage output

        Returns:
            AgentResult with WritingOutput data
        """
        start_time = time.time()

        try:
            # Get research data from previous stage
            research_data = context.get_latest_output()
            if not research_data:
                raise ValueError("No research data found in context")

            # Extract configuration
            style = self.config.get("style", "professional")
            target_words = self.config.get("target_words", 2000)
            format_type = self.config.get("format", "markdown")

            # Generate title
            title = self._generate_title(research_data, style)

            # Plan document structure
            section_plan = self._plan_sections(research_data, target_words)

            # Write each section
            sections = []
            for plan in section_plan:
                section = self._write_section(
                    plan,
                    research_data,
                    style
                )
                sections.append(section)

            # Compile references
            references = [f.get("source_url", "") for f in research_data.get("findings", [])]

            # Create validated output
            writing_output = WritingOutput(
                title=title,
                sections=sections,
                references=references,
                word_count=sum(s.word_count for s in sections),
                format=format_type,
                metadata={
                    "style": style,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "query": research_data.get("query", "")
                }
            )

            return AgentResult(
                success=True,
                data=writing_output.dict(),
                execution_time_seconds=time.time() - start_time
            )

        except Exception as e:
            return AgentResult(
                success=False,
                data={},
                error=str(e),
                execution_time_seconds=time.time() - start_time
            )

    def _generate_title(self, research_data: dict, style: str) -> str:
        """Generate compelling document title"""

        query = research_data.get("query", "Research Report")
        summary = research_data.get("summary", "")[:200]

        prompt = f"""Create a compelling {style} title for a report about: {query}

Research summary: {summary}

Generate only the title, no explanations. Make it professional and descriptive (max 100 characters)."""

        title = self.adapter.generate_text(
            system_prompt=self.system_prompt,
            user_prompt=prompt,
            max_tokens=50,
            temperature=0.8
        )

        return title.strip().strip('"')

    def _plan_sections(self, research_data: dict, target_words: int) -> list[dict]:
        """Plan document structure"""

        # Simple default structure
        return [
            {"heading": "Introduction", "target_words": int(target_words * 0.15)},
            {"heading": "Key Findings", "target_words": int(target_words * 0.50)},
            {"heading": "Analysis", "target_words": int(target_words * 0.25)},
            {"heading": "Conclusion", "target_words": int(target_words * 0.10)},
        ]

    def _write_section(
        self,
        plan: dict,
        research_data: dict,
        style: str
    ) -> DocumentSection:
        """Write one document section"""

        heading = plan["heading"]
        target_words = plan["target_words"]

        findings_text = "\n\n".join([
            f"[{i}] {f.get('title', '')}: {f.get('content', '')}"
            for i, f in enumerate(research_data.get("findings", []))
        ])

        prompt = f"""Write the "{heading}" section for a {style} report.

Research findings:
{findings_text}

Target length: ~{target_words} words
Include citations using [0], [1], etc.

Write the section content now:"""

        content = self.adapter.generate_text(
            system_prompt=self.system_prompt,
            user_prompt=prompt,
            max_tokens=int(target_words * 1.5),
            temperature=0.7
        )

        # Extract citation numbers from content
        import re
        citations = [int(m) for m in re.findall(r'\[(\d+)\]', content)]

        return DocumentSection(
            heading=heading,
            content=content.strip(),
            citations=list(set(citations)),
            word_count=len(content.split())
        )
```

---

### Step 5.3: Validation Agent (Simplified)

**File**: `core/agents/validation_agent.py` (NEW FILE)

**Implementation**:

```python
"""
Validation Agent - Verifies document quality and accuracy.
"""

from typing import Any, Dict
import time

from core.pipeline.agent import PipelineAgent, AgentCapability
from core.pipeline.context import PipelineContext
from core.pipeline.models import AgentResult, ValidationOutput, ValidationCheck
from core.pipeline.ai_adapter import PipelineAIAdapter


class ValidationAgent(PipelineAgent):
    """
    Verifies content accuracy, quality, and completeness.

    Capabilities:
    - Content quality assessment
    - Grammar checking
    - Citation verification
    - Completeness assessment

    Input: WritingOutput from previous stage
    Output: ValidationOutput with quality scores and validated document
    """

    def __init__(self, config: Dict[str, Any], ai_manager: Any):
        super().__init__(
            agent_id="validation_agent",
            role="validator",
            system_prompt="""You are a quality assurance specialist.
Your task is to verify document quality and accuracy.

Evaluate:
1. Content quality and coherence
2. Grammar and spelling
3. Citation completeness
4. Overall professionalism

Provide honest, objective assessment.""",
            capabilities=[
                AgentCapability(
                    capability_id="content_validation",
                    name="Content Validation",
                    description="Verify quality and accuracy",
                    input_types=["json"],
                    output_types=["json"],
                    requires_internet=False,
                    estimated_time_seconds=90
                )
            ],
            config=config,
            ai_manager=ai_manager
        )
        self.adapter = PipelineAIAdapter(ai_manager)

    def execute(self, context: PipelineContext) -> AgentResult:
        """
        Validate document quality.

        Args:
            context: Pipeline context with writing_stage output

        Returns:
            AgentResult with ValidationOutput data
        """
        start_time = time.time()

        try:
            # Get document from previous stage
            document = context.get_latest_output()
            if not document:
                raise ValueError("No document found in context")

            # Perform validation checks
            checks = {
                "content_quality": self._check_content_quality(document),
                "grammar": self._check_grammar(document),
                "citations": self._check_citations(document),
                "completeness": self._check_completeness(document),
            }

            # Apply corrections if enabled
            validated_doc = document.copy()
            corrections_made = []

            if self.config.get("auto_fix", True):
                validated_doc, corrections = self._apply_corrections(document, checks)
                corrections_made = corrections

            # Calculate overall score
            overall_score = sum(c.score for c in checks.values()) / len(checks)

            # Create validated output
            validation_output = ValidationOutput(
                overall_score=overall_score,
                checks=checks,
                corrections_made=corrections_made,
                validated_document=validated_doc,
                ready_for_export=(overall_score >= self.config.get("min_score_for_approval", 0.8))
            )

            return AgentResult(
                success=True,
                data=validation_output.dict(),
                execution_time_seconds=time.time() - start_time
            )

        except Exception as e:
            return AgentResult(
                success=False,
                data={},
                error=str(e),
                execution_time_seconds=time.time() - start_time
            )

    def _check_content_quality(self, document: dict) -> ValidationCheck:
        """Check overall content quality"""

        # Simple heuristic check
        total_words = document.get("word_count", 0)
        num_sections = len(document.get("sections", []))

        score = 0.9 if total_words > 100 and num_sections > 0 else 0.6
        passed = score >= 0.7

        return ValidationCheck(
            name="Content Quality",
            score=score,
            passed=passed,
            issues=[] if passed else ["Content may be too short or incomplete"],
            suggestions=[] if passed else ["Add more detailed content"]
        )

    def _check_grammar(self, document: dict) -> ValidationCheck:
        """Check grammar and spelling (simplified)"""

        # Simplified check - in production, use proper grammar checker
        score = 0.85
        passed = True

        return ValidationCheck(
            name="Grammar & Spelling",
            score=score,
            passed=passed,
            issues=[],
            suggestions=[]
        )

    def _check_citations(self, document: dict) -> ValidationCheck:
        """Verify citations are present"""

        sections = document.get("sections", [])
        has_citations = any(
            len(s.get("citations", [])) > 0 for s in sections
        )

        score = 1.0 if has_citations else 0.7
        passed = has_citations

        return ValidationCheck(
            name="Citations",
            score=score,
            passed=passed,
            issues=[] if passed else ["Some sections lack citations"],
            suggestions=[] if passed else ["Add source citations to support claims"]
        )

    def _check_completeness(self, document: dict) -> ValidationCheck:
        """Check document completeness"""

        has_title = bool(document.get("title"))
        has_sections = len(document.get("sections", [])) > 0
        has_references = len(document.get("references", [])) > 0

        score = 0.9 if all([has_title, has_sections, has_references]) else 0.7
        passed = score >= 0.7

        return ValidationCheck(
            name="Completeness",
            score=score,
            passed=passed,
            issues=[] if passed else ["Document structure incomplete"],
            suggestions=[] if passed else ["Ensure title, sections, and references are present"]
        )

    def _apply_corrections(self, document: dict, checks: dict) -> tuple[dict, list[str]]:
        """Apply automatic corrections (simplified)"""

        corrected = document.copy()
        corrections = []

        # In production, implement actual corrections based on check results
        # For now, just return the document as-is

        return corrected, corrections
```

---

### Step 5.4: Export Agent (Simplified)

**File**: `core/agents/export_agent.py` (NEW FILE)

**Implementation**:

```python
"""
Export Agent - Exports documents to multiple formats.
"""

from typing import Any, Dict
import time
from pathlib import Path
from datetime import datetime

from core.pipeline.agent import PipelineAgent, AgentCapability
from core.pipeline.context import PipelineContext
from core.pipeline.models import AgentResult, ExportOutput, ExportedFile


class ExportAgent(PipelineAgent):
    """
    Exports content to multiple file formats.

    Capabilities:
    - Markdown export
    - Text export
    - (PDF/DOCX support to be added in Phase 2)

    Input: ValidationOutput with validated_document
    Output: ExportOutput with file paths
    """

    def __init__(self, config: Dict[str, Any], ai_manager: Any):
        super().__init__(
            agent_id="export_agent",
            role="exporter",
            system_prompt="",  # No LLM needed for export
            capabilities=[
                AgentCapability(
                    capability_id="multi_format_export",
                    name="Multi-Format Export",
                    description="Generate MD, TXT files",
                    input_types=["json"],
                    output_types=["file"],
                    requires_internet=False,
                    estimated_time_seconds=30
                )
            ],
            config=config,
            ai_manager=ai_manager
        )

    def execute(self, context: PipelineContext) -> AgentResult:
        """
        Export document to multiple formats.

        Args:
            context: Pipeline context with validation_stage output

        Returns:
            AgentResult with ExportOutput data
        """
        start_time = time.time()

        try:
            # Get validated document
            validation_data = context.get_latest_output()
            if not validation_data:
                raise ValueError("No validation data found")

            document = validation_data.get("validated_document", {})

            # Configuration
            formats = self.config.get("formats", ["md", "txt"])
            output_dir = Path(self.config.get("output_directory", context.working_directory))
            filename_base = self.config.get("filename", "document")

            # Create output directory
            output_dir.mkdir(parents=True, exist_ok=True)

            exported_files = []

            # Export to each format
            for format_type in formats:
                try:
                    if format_type == "md":
                        file_path = self._export_markdown(document, output_dir, filename_base)
                    elif format_type == "txt":
                        file_path = self._export_text(document, output_dir, filename_base)
                    else:
                        print(f"Warning: Format {format_type} not yet supported")
                        continue

                    if file_path and file_path.exists():
                        exported_files.append(
                            ExportedFile(
                                format=format_type,
                                path=str(file_path),
                                size_bytes=file_path.stat().st_size,
                                created_at=datetime.now()
                            )
                        )

                except Exception as e:
                    print(f"Warning: Failed to export {format_type}: {e}")

            if not exported_files:
                raise ValueError("No files were successfully exported")

            # Create output
            export_output = ExportOutput(
                exported_files=exported_files,
                export_count=len(exported_files),
                total_size_bytes=sum(f.size_bytes for f in exported_files)
            )

            return AgentResult(
                success=True,
                data=export_output.dict(),
                execution_time_seconds=time.time() - start_time
            )

        except Exception as e:
            return AgentResult(
                success=False,
                data={},
                error=str(e),
                execution_time_seconds=time.time() - start_time
            )

    def _export_markdown(self, document: dict, output_dir: Path, filename: str) -> Path:
        """Export to Markdown format"""

        file_path = output_dir / f"{filename}.md"

        # Build markdown content
        content = f"# {document.get('title', 'Untitled Document')}\n\n"

        for section in document.get("sections", []):
            content += f"## {section.get('heading', 'Section')}\n\n"
            content += f"{section.get('content', '')}\n\n"

        # Add references
        if document.get("references"):
            content += "## References\n\n"
            for i, ref in enumerate(document.get("references", [])):
                content += f"{i}. {ref}\n"

        # Write file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return file_path

    def _export_text(self, document: dict, output_dir: Path, filename: str) -> Path:
        """Export to plain text format"""

        file_path = output_dir / f"{filename}.txt"

        # Build text content
        content = f"{document.get('title', 'Untitled Document')}\n"
        content += "=" * 80 + "\n\n"

        for section in document.get("sections", []):
            content += f"{section.get('heading', 'Section')}\n"
            content += "-" * 40 + "\n"
            content += f"{section.get('content', '')}\n\n"

        # Add references
        if document.get("references"):
            content += "References\n"
            content += "-" * 40 + "\n"
            for i, ref in enumerate(document.get("references", [])):
                content += f"[{i}] {ref}\n"

        # Write file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return file_path
```

---

## Phase 6: Pipeline Orchestrator

### Step 6.1: Create Stage Executor

**File**: `core/pipeline/stage.py` (NEW FILE)

**Implementation**:

```python
"""
Pipeline stage execution logic.
Wraps agents with retry, timeout, and approval handling.
"""

from typing import Callable, Optional, Any
from dataclasses import dataclass
import time

from core.pipeline.agent import PipelineAgent
from core.pipeline.context import PipelineContext
from core.pipeline.models import StageConfig, StageResult


@dataclass
class PipelineStage:
    """
    Represents one step in an automation workflow.
    Wraps an agent with execution configuration.
    """

    stage_id: str
    name: str
    agent: PipelineAgent
    config: StageConfig
    input_mapping: Optional[dict] = None

    def execute(
        self,
        context: PipelineContext,
        progress_callback: Callable[[str, int], None]
    ) -> StageResult:
        """
        Execute the stage with retry logic.

        Args:
            context: Pipeline context
            progress_callback: Progress update function

        Returns:
            StageResult with success status and data
        """

        start_time = time.time()

        # Try execution with retries
        attempt = 0
        last_error = None

        while attempt < self.config.max_retries:
            try:
                progress_callback(
                    f"Running {self.name} (attempt {attempt + 1}/{self.config.max_retries})",
                    0
                )

                # Execute agent
                result = self.agent.execute(context)

                if result.success:
                    # Success - return result
                    return StageResult(
                        stage_id=self.stage_id,
                        success=True,
                        data=result.data,
                        duration_seconds=time.time() - start_time,
                        aborted=False
                    )
                else:
                    # Agent returned failure
                    last_error = result.error
                    if not self.config.retry_on_failure:
                        break

            except Exception as e:
                last_error = str(e)
                if not self.config.retry_on_failure:
                    break

            attempt += 1
            if attempt < self.config.max_retries:
                time.sleep(1)  # Brief pause before retry

        # All retries failed
        return StageResult(
            stage_id=self.stage_id,
            success=False,
            error=last_error or "Unknown error",
            duration_seconds=time.time() - start_time,
            aborted=False
        )

    def should_execute(self, context: PipelineContext) -> bool:
        """
        Determine if stage should run based on conditions.

        Args:
            context: Pipeline context

        Returns:
            True if stage should execute
        """

        # Check skip_if_previous_failed
        if self.config.skip_if_previous_failed:
            # Check if any previous stage failed
            latest_output = context.get_latest_output()
            if latest_output is None:
                return False

        # Check custom condition (future feature)
        if self.config.condition:
            # TODO: Implement condition evaluation
            pass

        return True
```

---

### Step 6.2: Create Orchestrator

**File**: `core/pipeline/orchestrator.py` (NEW FILE)

**Implementation**:

```python
"""
Pipeline orchestrator - executes multi-stage workflows.
"""

import threading
import uuid
import time
from typing import Callable, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from core.pipeline.pipeline import AutomationPipeline
from core.pipeline.context import PipelineContext
from core.pipeline.models import PipelineResult, StageResult


class PipelineOrchestrator:
    """
    Executes automation pipelines with progress tracking and error handling.
    """

    def __init__(self, ai_manager: Any, settings_manager: Any):
        """
        Initialize orchestrator.

        Args:
            ai_manager: AIManager instance for LLM access
            settings_manager: SettingsManager for configuration
        """
        self.ai_manager = ai_manager
        self.settings = settings_manager
        self.running_pipelines: Dict[str, PipelineContext] = {}

    def execute_pipeline(
        self,
        pipeline: AutomationPipeline,
        initial_params: Dict[str, Any],
        progress_callback: Callable[[str, int, dict], None],
        approval_callback: Optional[Callable[[dict], bool]] = None,
        completion_callback: Optional[Callable[[PipelineResult], None]] = None
    ) -> str:
        """
        Execute pipeline asynchronously.

        Args:
            pipeline: Pipeline definition
            initial_params: Initial parameters (query, etc.)
            progress_callback: Called with (message, percent, metadata)
            approval_callback: Called for approval gates (returns True to continue)
            completion_callback: Called when pipeline completes

        Returns:
            execution_id: UUID for tracking
        """

        execution_id = str(uuid.uuid4())

        # Create workspace
        workspace = self._create_workspace(execution_id)

        # Create context
        context = PipelineContext(
            pipeline_id=pipeline.metadata.pipeline_id,
            execution_id=execution_id,
            user_request=initial_params.get("user_request", ""),
            initial_parameters=initial_params,
            working_directory=workspace,
            total_stages=len(pipeline.stages)
        )

        self.running_pipelines[execution_id] = context

        # Execute in background thread
        thread = threading.Thread(
            target=self._run_pipeline_thread,
            args=(execution_id, pipeline, context, progress_callback,
                  approval_callback, completion_callback),
            daemon=True
        )
        thread.start()

        return execution_id

    def _run_pipeline_thread(
        self,
        execution_id: str,
        pipeline: AutomationPipeline,
        context: PipelineContext,
        progress_callback: Callable,
        approval_callback: Optional[Callable],
        completion_callback: Optional[Callable]
    ):
        """Background thread for pipeline execution"""

        result = PipelineResult(
            execution_id=execution_id,
            pipeline_id=pipeline.metadata.pipeline_id,
            success=False,
            outputs={},
            errors=[]
        )

        start_time = time.time()

        try:
            for i, stage in enumerate(pipeline.stages):
                if context.should_abort:
                    result.aborted = True
                    result.abort_reason = context.abort_reason
                    break

                context.current_stage = i

                # Check if stage should execute
                if not stage.should_execute(context):
                    progress_callback(
                        f"Skipping {stage.name}",
                        int((i / len(pipeline.stages)) * 100),
                        {"stage": stage.name, "skipped": True}
                    )
                    continue

                # Execute stage
                progress_callback(
                    f"Starting {stage.name}...",
                    int((i / len(pipeline.stages)) * 100),
                    {"stage": stage.name}
                )

                stage_result = stage.execute(
                    context,
                    lambda msg, pct: progress_callback(
                        msg,
                        int((i / len(pipeline.stages)) * 100) + pct // len(pipeline.stages),
                        {"stage": stage.name}
                    )
                )

                # Handle result
                if stage_result.success:
                    context.add_stage_output(
                        stage.stage_id,
                        stage_result.data,
                        {"duration": stage_result.duration_seconds}
                    )

                    # Check if approval required
                    if stage.config.approval_required and approval_callback:
                        context.approval_pending = True
                        context.approval_data = {
                            "stage": stage.name,
                            "output": stage_result.data
                        }

                        approved = approval_callback(context.approval_data)
                        context.approval_pending = False

                        if not approved:
                            context.abort("User rejected stage output")
                            result.aborted = True
                            result.abort_reason = "User rejected output"
                            break

                else:
                    # Stage failed
                    result.errors.append({
                        "stage": stage.name,
                        "error": stage_result.error
                    })

                    if stage.config.skip_if_previous_failed:
                        break

            # Pipeline completed
            result.success = len(result.errors) == 0 and not result.aborted
            result.outputs = context.stage_outputs
            result.total_duration_seconds = time.time() - start_time
            result.completed_at = datetime.now().isoformat()

        except Exception as e:
            result.errors.append({"stage": "orchestrator", "error": str(e)})
            result.success = False

        finally:
            # Cleanup
            if context.working_directory != Path.cwd():
                context.cleanup()

            del self.running_pipelines[execution_id]

            # Notify completion
            if completion_callback:
                completion_callback(result)

    def cancel_pipeline(self, execution_id: str):
        """Abort running pipeline"""
        if execution_id in self.running_pipelines:
            context = self.running_pipelines[execution_id]
            context.abort("User cancelled")

    def get_status(self, execution_id: str) -> Optional[dict]:
        """Get current pipeline status"""
        if execution_id not in self.running_pipelines:
            return None

        context = self.running_pipelines[execution_id]
        return {
            "current_stage": context.current_stage,
            "total_stages": context.total_stages,
            "progress_percent": int((context.current_stage / context.total_stages) * 100),
            "approval_pending": context.approval_pending
        }

    def _create_workspace(self, execution_id: str) -> Path:
        """Create temporary workspace for pipeline execution"""
        workspace = Path.home() / ".fylorra" / "pipeline_workspaces" / execution_id
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace
```

---

## Phase 7: Pipeline Definition

### Step 7.1: Create Pipeline Class

**File**: `core/pipeline/pipeline.py` (NEW FILE)

**Implementation**:

```python
"""
Pipeline definition and template management.
"""

from typing import List, Dict, Any, Optional
import json
from pathlib import Path

from core.pipeline.stage import PipelineStage
from core.pipeline.models import PipelineMetadata, StageConfig


class AutomationPipeline:
    """
    Complete multi-agent workflow definition.
    Can be created programmatically or loaded from JSON template.
    """

    def __init__(
        self,
        metadata: PipelineMetadata,
        stages: List[PipelineStage],
        trigger: Optional[Dict[str, Any]] = None,
        global_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize pipeline.

        Args:
            metadata: Pipeline metadata
            stages: List of pipeline stages
            trigger: Optional trigger configuration
            global_config: Global pipeline settings
        """
        self.metadata = metadata
        self.stages = stages
        self.trigger = trigger
        self.global_config = global_config or {}

    def validate(self) -> tuple[bool, List[str]]:
        """
        Validate pipeline configuration.

        Returns:
            (is_valid, list_of_errors)
        """
        errors = []

        if not self.stages:
            errors.append("Pipeline must have at least one stage")

        # Check for duplicate stage IDs
        stage_ids = [s.stage_id for s in self.stages]
        if len(stage_ids) != len(set(stage_ids)):
            errors.append("Stage IDs must be unique")

        # Validate each stage
        for stage in self.stages:
            if not stage.agent:
                errors.append(f"Stage {stage.stage_id} has no agent")

        return len(errors) == 0, errors

    def estimate_duration(self) -> int:
        """Estimate total execution time in seconds"""
        return sum(stage.agent.estimate_duration() for stage in self.stages)

    def to_dict(self) -> dict:
        """Serialize pipeline to dictionary"""
        return {
            "metadata": self.metadata.dict() if hasattr(self.metadata, 'dict') else self.metadata,
            "stages": [
                {
                    "stage_id": s.stage_id,
                    "name": s.name,
                    "agent_type": s.agent.__class__.__name__,
                    "agent_config": s.agent.config,
                    "config": s.config.dict() if hasattr(s.config, 'dict') else s.config,
                    "input_mapping": s.input_mapping
                }
                for s in self.stages
            ],
            "trigger": self.trigger,
            "global_config": self.global_config
        }

    def save_template(self, file_path: Path):
        """Save pipeline as JSON template"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

    @classmethod
    def from_template(cls, template_path: Path, ai_manager: Any) -> 'AutomationPipeline':
        """
        Load pipeline from JSON template.

        Args:
            template_path: Path to JSON template file
            ai_manager: AIManager instance for agents

        Returns:
            AutomationPipeline instance
        """
        with open(template_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Parse metadata
        metadata = PipelineMetadata(**data["metadata"])

        # Create stages
        from core.agents.research_agent import ResearchAgent
        from core.agents.writing_agent import WritingAgent
        from core.agents.validation_agent import ValidationAgent
        from core.agents.export_agent import ExportAgent

        agent_classes = {
            "ResearchAgent": ResearchAgent,
            "WritingAgent": WritingAgent,
            "ValidationAgent": ValidationAgent,
            "ExportAgent": ExportAgent,
        }

        stages = []
        for stage_data in data["stages"]:
            agent_type = stage_data["agent_type"]
            agent_class = agent_classes.get(agent_type)

            if not agent_class:
                raise ValueError(f"Unknown agent type: {agent_type}")

            # Create agent instance
            agent = agent_class(
                config=stage_data.get("agent_config", {}),
                ai_manager=ai_manager
            )

            # Create stage
            stage = PipelineStage(
                stage_id=stage_data["stage_id"],
                name=stage_data["name"],
                agent=agent,
                config=StageConfig(**stage_data.get("config", {})),
                input_mapping=stage_data.get("input_mapping")
            )

            stages.append(stage)

        return cls(
            metadata=metadata,
            stages=stages,
            trigger=data.get("trigger"),
            global_config=data.get("global_config", {})
        )
```

---

## Phase 8: Template Creation

### Step 8.1: Create Research-to-Report Template

**File**: `core/pipeline_templates/research_to_report.json` (NEW FILE)

**Implementation**:

```json
{
  "metadata": {
    "pipeline_id": "research_to_report_v1",
    "name": "Research to Professional Report",
    "description": "Automated workflow: web research → professional writing → validation → multi-format export",
    "category": "research",
    "author": "Fylorra",
    "version": "1.0.0",
    "tags": ["research", "report", "automation", "ai"]
  },

  "stages": [
    {
      "stage_id": "research_stage",
      "name": "Web Research",
      "agent_type": "ResearchAgent",
      "agent_config": {
        "max_sources": 10,
        "credibility_threshold": 0.7
      },
      "config": {
        "approval_required": false,
        "retry_on_failure": true,
        "max_retries": 3,
        "timeout_seconds": 180
      }
    },

    {
      "stage_id": "writing_stage",
      "name": "Professional Writing",
      "agent_type": "WritingAgent",
      "agent_config": {
        "style": "professional",
        "target_words": 2000,
        "format": "markdown"
      },
      "config": {
        "approval_required": false,
        "retry_on_failure": true,
        "max_retries": 2,
        "timeout_seconds": 300
      }
    },

    {
      "stage_id": "validation_stage",
      "name": "Quality Validation",
      "agent_type": "ValidationAgent",
      "agent_config": {
        "auto_fix": true,
        "min_score_for_approval": 0.8
      },
      "config": {
        "approval_required": true,
        "approval_message": "Review the validated document before exporting?",
        "retry_on_failure": false,
        "timeout_seconds": 240
      }
    },

    {
      "stage_id": "export_stage",
      "name": "Multi-Format Export",
      "agent_type": "ExportAgent",
      "agent_config": {
        "formats": ["md", "txt"],
        "output_directory": "~/Documents/Fylorra_Reports",
        "filename": "research_report"
      },
      "config": {
        "approval_required": false,
        "retry_on_failure": true,
        "max_retries": 1,
        "timeout_seconds": 60
      }
    }
  ],

  "trigger": null,

  "global_config": {
    "cleanup_temp_files": true,
    "save_intermediate_results": true,
    "notification_on_complete": true
  }
}
```

---

## Phase 9: Settings Integration

### Step 9.1: Extend Settings Manager (Safe Pattern)

**IMPORTANT**: Do NOT modify `core/settings_manager.py` directly. Create a wrapper.

**File**: `core/pipeline/settings_adapter.py` (NEW FILE)

**Implementation**:

```python
"""
Adapter for workflow settings without modifying SettingsManager.
"""

from typing import Dict, Any
from pathlib import Path


class WorkflowSettingsAdapter:
    """
    Wrapper for accessing workflow settings.
    Works with existing SettingsManager without modification.
    """

    def __init__(self, settings_manager: Any):
        """
        Initialize adapter.

        Args:
            settings_manager: Existing SettingsManager instance
        """
        self.settings_manager = settings_manager

    def get_workflow_settings(self) -> Dict[str, Any]:
        """Get automation workflow configuration"""
        settings = self.settings_manager.get_settings()

        # Return workflow settings if they exist, otherwise defaults
        return settings.get("automation_workflows", self._get_defaults())

    def save_workflow_settings(self, workflow_settings: Dict[str, Any]):
        """Update workflow configuration"""
        settings = self.settings_manager.get_settings()
        settings["automation_workflows"] = workflow_settings
        self.settings_manager.save_settings(settings)

    def _get_defaults(self) -> Dict[str, Any]:
        """Default workflow settings"""
        return {
            "enabled": True,
            "default_output_directory": str(Path.home() / "Documents" / "Fylorra_Automation"),
            "max_concurrent_pipelines": 2,
            "save_execution_logs": True,
            "log_retention_days": 30,
            "agent_settings": {
                "research_agent": {
                    "default_max_sources": 10,
                    "timeout_per_source_seconds": 20
                },
                "writing_agent": {
                    "default_style": "professional",
                    "default_word_count": 2000
                },
                "validation_agent": {
                    "auto_fix_enabled": True,
                    "min_quality_score": 0.8
                },
                "export_agent": {
                    "default_formats": ["md", "txt"],
                    "default_template": "professional"
                }
            }
        }

    def get_agent_config(self, agent_type: str) -> Dict[str, Any]:
        """Get configuration for specific agent type"""
        workflow_settings = self.get_workflow_settings()
        return workflow_settings.get("agent_settings", {}).get(agent_type, {})

    def get_templates_directory(self) -> Path:
        """Get directory containing pipeline templates"""
        return Path(__file__).parent.parent / "pipeline_templates"
```

---

## Phase 10: Testing the Pipeline

### Step 10.1: Create Test Script

**File**: `test_pipeline.py` (NEW FILE - in project root)

**Implementation**:

```python
"""
Test script for automation workflow pipeline.
Run this to verify the implementation works.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.ai_manager import AIManager
from core.settings_manager import SettingsManager
from core.pipeline.orchestrator import PipelineOrchestrator
from core.pipeline.pipeline import AutomationPipeline


def test_pipeline():
    """Test the research-to-report pipeline"""

    print("=" * 80)
    print("Testing Automation Workflow Pipeline")
    print("=" * 80)

    # Initialize managers
    print("\n1. Initializing AI Manager...")
    settings_mgr = SettingsManager()
    ai_mgr = AIManager(settings_mgr)

    # Load template
    print("\n2. Loading pipeline template...")
    template_path = Path(__file__).parent / "core" / "pipeline_templates" / "research_to_report.json"

    if not template_path.exists():
        print(f"ERROR: Template not found at {template_path}")
        return

    pipeline = AutomationPipeline.from_template(template_path, ai_mgr)
    print(f"   ✓ Loaded: {pipeline.metadata.name}")
    print(f"   ✓ Stages: {len(pipeline.stages)}")

    # Validate pipeline
    print("\n3. Validating pipeline...")
    is_valid, errors = pipeline.validate()
    if not is_valid:
        print(f"   ✗ Validation failed:")
        for error in errors:
            print(f"     - {error}")
        return
    print("   ✓ Pipeline is valid")

    # Create orchestrator
    print("\n4. Creating orchestrator...")
    orchestrator = PipelineOrchestrator(ai_mgr, settings_mgr)

    # Progress callback
    def on_progress(message: str, percent: int, metadata: dict):
        print(f"   [{percent:3d}%] {message}")

    # Completion callback
    def on_complete(result):
        print("\n" + "=" * 80)
        print("Pipeline Execution Complete")
        print("=" * 80)
        print(f"Success: {result.success}")
        print(f"Duration: {result.total_duration_seconds:.2f} seconds")

        if result.success:
            print("\nStage Outputs:")
            for stage_id, output in result.outputs.items():
                print(f"  - {stage_id}: {type(output).__name__ if hasattr(output, '__name__') else 'dict'}")

            # Show exported files
            if "export_stage" in result.outputs:
                export_data = result.outputs["export_stage"]
                print("\nExported Files:")
                for file_info in export_data.get("exported_files", []):
                    print(f"  - {file_info['format']}: {file_info['path']}")
        else:
            print("\nErrors:")
            for error in result.errors:
                print(f"  - {error.get('stage', 'unknown')}: {error.get('error', 'unknown error')}")

    # Approval callback
    def on_approval(approval_data):
        stage = approval_data.get("stage", "Unknown")
        print(f"\n{'=' * 80}")
        print(f"Approval Required: {stage}")
        print(f"{'=' * 80}")

        # Auto-approve for testing
        print("Auto-approving for test...")
        return True

    # Execute pipeline
    print("\n5. Executing pipeline...")
    execution_id = orchestrator.execute_pipeline(
        pipeline=pipeline,
        initial_params={
            "user_request": "Research AI trends in 2026",
            "query": "AI trends 2026"
        },
        progress_callback=on_progress,
        approval_callback=on_approval,
        completion_callback=on_complete
    )

    print(f"\n   Execution ID: {execution_id}")
    print("   Pipeline running in background...")
    print("   (This may take 2-5 minutes)\n")

    # Wait for completion
    import time
    while execution_id in orchestrator.running_pipelines:
        time.sleep(1)

    print("\nTest complete!")


if __name__ == "__main__":
    test_pipeline()
```

---

## Phase 11: Integration with Main Window

### Step 11.1: Add Menu Item (Minimal Change)

**File**: `qt_app/main_window.py`

**Action**: FIND the AI menu section and ADD this code:

```python
# In the AI menu creation section, add:

# NEW: Automation Workflow menu item
workflow_action = QAction("Workflow Studio...", self)
workflow_action.triggered.connect(self.show_workflow_studio)
ai_menu.addAction(workflow_action)
```

**Then ADD this method to the MainWindow class**:

```python
def show_workflow_studio(self):
    """Open Automation Workflow dialog"""
    try:
        from qt_app.dialogs.automation_workflow_dialog import AutomationWorkflowDialog

        dialog = AutomationWorkflowDialog(self, self.ai_manager, self.settings_manager)
        dialog.exec()

    except Exception as e:
        QMessageBox.critical(
            self,
            "Error",
            f"Failed to open Workflow Studio: {str(e)}"
        )
```

---

## Phase 12: Basic UI Dialog (Simplified)

### Step 12.1: Create Simple Workflow Dialog

**File**: `qt_app/dialogs/automation_workflow_dialog.py` (NEW FILE)

**Implementation**:

```python
"""
Automation Workflow Dialog - Main UI for pipeline management.
Phase 1: Simplified version with template loading and execution.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QListWidget, QTextEdit, QProgressBar,
    QMessageBox, QListWidgetItem
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from pathlib import Path

from core.pipeline.orchestrator import PipelineOrchestrator
from core.pipeline.pipeline import AutomationPipeline


class PipelineExecutionThread(QThread):
    """Background thread for pipeline execution"""

    progress = pyqtSignal(str, int, dict)
    completed = pyqtSignal(object)
    approval_needed = pyqtSignal(dict)

    def __init__(self, orchestrator, pipeline, params):
        super().__init__()
        self.orchestrator = orchestrator
        self.pipeline = pipeline
        self.params = params
        self.execution_id = None

    def run(self):
        """Execute pipeline in background"""
        self.execution_id = self.orchestrator.execute_pipeline(
            pipeline=self.pipeline,
            initial_params=self.params,
            progress_callback=self.on_progress,
            approval_callback=self.on_approval,
            completion_callback=self.on_complete
        )

    def on_progress(self, message, percent, metadata):
        self.progress.emit(message, percent, metadata)

    def on_approval(self, approval_data):
        # For Phase 1, auto-approve
        return True

    def on_complete(self, result):
        self.completed.emit(result)


class AutomationWorkflowDialog(QDialog):
    """
    Main dialog for Automation Workflows.
    Phase 1: Template selection and execution only.
    """

    def __init__(self, parent, ai_manager, settings_manager):
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.settings_manager = settings_manager
        self.orchestrator = PipelineOrchestrator(ai_manager, settings_manager)
        self.execution_thread = None

        self.setWindowTitle("Workflow Studio")
        self.setMinimumSize(800, 600)

        self.init_ui()
        self.load_templates()

    def init_ui(self):
        """Initialize UI components"""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("<h2>Automation Workflow Studio</h2>")
        layout.addWidget(title)

        # Template list
        layout.addWidget(QLabel("Available Templates:"))
        self.template_list = QListWidget()
        self.template_list.itemDoubleClicked.connect(self.on_template_selected)
        layout.addWidget(self.template_list)

        # Description
        layout.addWidget(QLabel("Description:"))
        self.description_text = QTextEdit()
        self.description_text.setReadOnly(True)
        self.description_text.setMaximumHeight(100)
        layout.addWidget(self.description_text)

        # Progress
        layout.addWidget(QLabel("Progress:"))
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        # Buttons
        button_layout = QHBoxLayout()
        self.run_btn = QPushButton("Run Pipeline")
        self.run_btn.clicked.connect(self.run_pipeline)
        self.run_btn.setEnabled(False)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)

        button_layout.addWidget(self.run_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

    def load_templates(self):
        """Load available pipeline templates"""
        templates_dir = Path(__file__).parent.parent.parent / "core" / "pipeline_templates"

        if not templates_dir.exists():
            self.description_text.setPlainText("Templates directory not found.")
            return

        for template_file in templates_dir.glob("*.json"):
            item = QListWidgetItem(template_file.stem.replace("_", " ").title())
            item.setData(Qt.ItemDataRole.UserRole, template_file)
            self.template_list.addItem(item)

    def on_template_selected(self, item):
        """Template selected"""
        template_path = item.data(Qt.ItemDataRole.UserRole)

        try:
            pipeline = AutomationPipeline.from_template(template_path, self.ai_manager)
            self.current_pipeline = pipeline

            # Show description
            desc = f"{pipeline.metadata.name}\n\n"
            desc += f"{pipeline.metadata.description}\n\n"
            desc += f"Stages: {len(pipeline.stages)}\n"
            desc += f"Estimated duration: {pipeline.estimate_duration()} seconds"

            self.description_text.setPlainText(desc)
            self.run_btn.setEnabled(True)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load template: {e}")

    def run_pipeline(self):
        """Execute the selected pipeline"""
        if not hasattr(self, 'current_pipeline'):
            return

        # Get user input (simplified for Phase 1)
        from PyQt6.QtWidgets import QInputDialog
        query, ok = QInputDialog.getText(
            self,
            "Enter Query",
            "Research query:"
        )

        if not ok or not query:
            return

        # Start execution
        self.progress_bar.setVisible(True)
        self.status_label.setVisible(True)
        self.run_btn.setEnabled(False)

        self.execution_thread = PipelineExecutionThread(
            self.orchestrator,
            self.current_pipeline,
            {"query": query, "user_request": query}
        )

        self.execution_thread.progress.connect(self.on_progress)
        self.execution_thread.completed.connect(self.on_completed)
        self.execution_thread.start()

    def on_progress(self, message, percent, metadata):
        """Update progress"""
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)

    def on_completed(self, result):
        """Pipeline execution completed"""
        self.progress_bar.setVisible(False)
        self.status_label.setVisible(False)
        self.run_btn.setEnabled(True)

        if result.success:
            # Show success with file paths
            msg = "Pipeline completed successfully!\n\n"

            if "export_stage" in result.outputs:
                export_data = result.outputs["export_stage"]
                msg += "Exported files:\n"
                for file_info in export_data.get("exported_files", []):
                    msg += f"  - {file_info['path']}\n"

            QMessageBox.information(self, "Success", msg)
        else:
            # Show errors
            msg = "Pipeline failed!\n\n"
            for error in result.errors:
                msg += f"- {error.get('stage', 'unknown')}: {error.get('error', 'unknown')}\n"

            QMessageBox.critical(self, "Error", msg)
```

---

## Summary: What You've Built

After completing all phases, you will have:

### ✅ Core Infrastructure
- Pydantic models for validation
- Pipeline context for data flow
- Base agent class
- AI adapter for LLM integration

### ✅ Specialized Agents
- ResearchAgent (stub with mock data)
- WritingAgent (transforms research to document)
- ValidationAgent (quality checks)
- ExportAgent (MD/TXT export)

### ✅ Execution System
- PipelineStage (retry, timeout handling)
- PipelineOrchestrator (manages execution)
- AutomationPipeline (template loading)

### ✅ Templates & Configuration
- research_to_report.json template
- Settings adapter
- Test script

### ✅ User Interface
- Menu integration in main window
- Basic workflow dialog
- Template selection and execution

---

## Testing Instructions

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run test script**:
   ```bash
   python test_pipeline.py
   ```

3. **Test via GUI**:
   - Launch Fylorra
   - Click AI → Workflow Studio
   - Select "Research To Report"
   - Click "Run Pipeline"
   - Enter query: "AI trends 2026"
   - Wait for completion
   - Check exported files in ~/Documents/Fylorra_Reports

---

## Next Steps (Future Phases)

After Phase 1 is working:
- Add real web search to ResearchAgent
- Implement PDF/DOCX export
- Add pipeline builder UI
- Create more templates
- Add conditional branching
- Implement loop/iteration support

---

## Important Notes

✅ **Safe Implementation**:
- No modifications to existing files
- All new code in separate modules
- Existing workflows unaffected

✅ **Pydantic Usage**:
- Use Pydantic library (NOT Pydantic AI framework)
- Validation at agent boundaries
- Type safety throughout

✅ **Local-First**:
- All processing uses existing AIManager
- No cloud API dependencies
- Privacy maintained

✅ **Extensible Design**:
- Easy to add new agents
- Template-based configuration
- Modular architecture

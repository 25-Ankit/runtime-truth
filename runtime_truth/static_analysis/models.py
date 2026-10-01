"""Static analysis helper models and configuration."""

from typing import List, Optional
from pydantic import BaseModel, Field


class ParserConfig(BaseModel):
    """Configuration options for static parsers."""
    ignore_patterns: List[str] = Field(default_factory=list)
    include_dev_dependencies: bool = True
    parse_submodules: bool = True

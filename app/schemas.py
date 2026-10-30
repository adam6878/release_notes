from datetime import datetime

from pydantic import BaseModel, Field


class ReleaseIn(BaseModel):
    version: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=200)
    author: str = Field(min_length=1, max_length=100)
    notes: str = Field(default="", max_length=10000)


class ReleaseOut(BaseModel):
    id: int
    version: str
    title: str
    author: str
    notes: str
    created_at: datetime

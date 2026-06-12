from typing import List

from pydantic import BaseModel, Field


class TextPrompt(BaseModel):
    text: str = Field(..., min_length=1, max_length=200)


class BoxPrompt(BaseModel):
    box: List[int] = Field(..., min_length=4, max_length=4)


class PointPrompt(BaseModel):
    point: List[int] = Field(..., min_length=2, max_length=2)


class MattingRequest(BaseModel):
    warmup: int = 10
    erode: int = 10
    dilate: int = 10
    max_size: int = 720
    save_image: bool = False

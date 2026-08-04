from pydantic import BaseModel, Field


class AnswerSection(BaseModel):
    title: str = Field(min_length=1)
    items: list[str] = Field(default_factory=list)


class StructuredAnswer(BaseModel):
    summary: str = Field(min_length=1)
    sections: list[AnswerSection] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    notice: str | None = None

from typing import Literal

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OrganizationInput(Input):
    name: str = Field(min_length=1, max_length=160)


class InviteInput(Input):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        try:
            return validate_email(
                value, check_deliverability=False, allow_smtputf8=False
            ).ascii_email.casefold()
        except EmailNotValidError:
            raise ValueError("Invalid email address") from None


class AcceptInvitation(Input):
    token: str = Field(min_length=32, max_length=512)
    verification_token: str | None = Field(default=None, min_length=32, max_length=512)


class VerifyInvitation(Input):
    token: str = Field(min_length=32, max_length=512)
    language: Literal["fr", "en"] = "fr"


class MembershipInput(Input):
    version: int = Field(ge=1)
    active: bool
    licensed: bool
    role: Literal["admin", "member"]


class OnboardingInput(Input):
    language: Literal["fr", "en"]
    role: str = Field(default="", max_length=160)
    activity: str = Field(default="", max_length=500)
    needs: str = Field(default="", max_length=4000)
    sector: str = Field(default="", max_length=160)
    success: str = Field(default="", max_length=1000)
    preferred_output: Literal["", "document", "spreadsheet", "presentation", "checklist"] = ""


class ResourceInput(Input):
    kind: Literal["memory", "conversation"]
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(max_length=100_000)

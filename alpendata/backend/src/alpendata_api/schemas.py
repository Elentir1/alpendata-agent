from typing import Literal

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
        if value.count("@") != 1 or any(character.isspace() for character in value):
            raise ValueError("Invalid email address")
        local, domain = value.split("@")
        if not local or not domain:
            raise ValueError("Invalid email address")
        return value.casefold()


class AcceptInvitation(Input):
    token: str = Field(min_length=32, max_length=512)


class MembershipInput(Input):
    active: bool
    licensed: bool
    role: Literal["admin", "member"]


class OnboardingInput(Input):
    language: Literal["fr", "en"]
    role: str = Field(default="", max_length=160)
    activity: str = Field(default="", max_length=500)
    needs: str = Field(default="", max_length=4000)


class ResourceInput(Input):
    kind: Literal["memory", "conversation"]
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(max_length=100_000)

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.whatsapp_privacy import normalize_phone_number


FullName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=150),
]
PhoneNumber = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=20),
]
BusinessName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=150),
]


class RegisterRequest(BaseModel):
    full_name: FullName
    phone_no: PhoneNumber
    email: EmailStr
    password: SecretStr = Field(min_length=8, max_length=128)
    role: Literal["tenant", "landlord"]
    business_name: BusinessName | None = None

    @field_validator("phone_no")
    @classmethod
    def normalize_phone_no(cls, value: str) -> str:
        return normalize_phone_number(value)

    @model_validator(mode="after")
    def validate_business_name_role(self) -> "RegisterRequest":
        if self.role == "tenant" and self.business_name is not None:
            raise ValueError("business_name is only available to landlord accounts.")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)

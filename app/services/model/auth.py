from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class ResponseGetToken(BaseModel):
    access_token: str
    token_type: str
    expires_in: int

"""src/application/dtos/build_info_dto.py."""

from pydantic import BaseModel, ConfigDict


class BuildInfoResponseDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commit: str
    rama: str

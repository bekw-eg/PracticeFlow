from app.models.specialty import Specialty
from app.repositories.base import TenantScopedRepository


class SpecialtyRepository(TenantScopedRepository[Specialty]):
    model = Specialty

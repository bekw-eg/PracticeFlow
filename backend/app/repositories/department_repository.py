from app.models.department import Department
from app.repositories.base import TenantScopedRepository


class DepartmentRepository(TenantScopedRepository[Department]):
    model = Department

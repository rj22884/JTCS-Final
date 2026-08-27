from __future__ import annotations

from app.repositories.customer_repository import CustomerRepository
from app.utils.db_session import persist


class CustomerService:
    def __init__(self, repository: CustomerRepository | None = None):
        self.repository = repository or CustomerRepository()

    def search(self, query: str, *, limit: int = 20) -> list[dict]:
        return self.repository.search(query, limit=limit)

    def search_party_name(self, query: str, *, limit: int = 15) -> list[dict]:
        return self.repository.search_party_name(query, limit=limit)

    def get_detail(self, customer_id: int) -> dict:
        return self.repository.get_detail(customer_id)

    def create(self, payload: dict) -> dict:
        def _write() -> dict:
            return self.repository.create(payload)

        return persist(_write)

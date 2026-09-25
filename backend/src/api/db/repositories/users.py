"""User collection access."""

import re

from pymongo.results import DeleteResult, InsertOneResult, UpdateResult

from src.api.db.repositories.base import MongoRepository, to_object_id
from src.api.errors import NotFoundError


class UserRepository(MongoRepository):
    """CRUD access to the ``users`` collection."""

    collection_name = "users"

    def get_by_id(self, user_id: str) -> dict | None:
        return self.collection.find_one({"_id": to_object_id(user_id, label="user ID")})

    def require_by_id(self, user_id: str) -> dict:
        user = self.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user

    def get_by_email(
        self,
        email: str,
        *,
        provider: str | None = None,
        reset_token: str | None = None,
    ) -> dict | None:
        query: dict = {"email": email}
        if provider is not None:
            query["provider"] = provider
        if reset_token is not None:
            query["reset_token"] = reset_token
        return self.collection.find_one(query)

    def search(self, term: str | None = None) -> list[dict]:
        query: dict = {}
        if term:
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            query = {"$or": [{"name": pattern}, {"email": pattern}]}
        return list(self.collection.find(query).sort("created_at", -1))

    def insert(self, doc: dict) -> InsertOneResult:
        return self.collection.insert_one(doc)

    def update_by_id(self, user_id: str, fields: dict) -> UpdateResult:
        return self.collection.update_one(
            {"_id": to_object_id(user_id, label="user ID")}, {"$set": fields}
        )

    def update_by_email(self, email: str, fields: dict) -> UpdateResult:
        return self.collection.update_one({"email": email}, {"$set": fields})

    def delete_by_id(self, user_id: str) -> DeleteResult:
        return self.collection.delete_one({"_id": to_object_id(user_id, label="user ID")})

    def count(self, query: dict | None = None) -> int:
        return self.collection.count_documents(query or {})

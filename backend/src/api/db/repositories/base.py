"""Shared base class for MongoDB repositories."""

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.collection import Collection
from pymongo.database import Database

from src.api.errors import ValidationError


def to_object_id(value: str, *, label: str = "id") -> ObjectId:
    """Parse *value* into an ``ObjectId``, raising a 400 on malformed input."""
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise ValidationError(f"Invalid {label} format") from None


class MongoRepository:
    """Base class giving subclasses access to a single MongoDB collection."""

    collection_name: str = ""

    def __init__(self, db: Database) -> None:
        self._db = db

    @property
    def collection(self) -> Collection:
        return self._db[self.collection_name]

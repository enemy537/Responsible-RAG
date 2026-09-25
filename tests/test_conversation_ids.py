"""Regression tests for conversation id handling.

A user reported:

    The server rejected that request: Invalid conversation ID format
    ref 04bc113773ed - HTTP 400

`get_chat_service` chooses the store from the user's *current* consent. A
conversation created while chat-history storage was off lives in the in-memory
repository and gets an ``eph-...`` id. If the user later grants consent, that id
is handed to the MongoDB repository, which parses ids as ObjectIds and used to
answer 400 - a reply the client cannot recover from, so the user was stuck on
that conversation for good.

An id that cannot be an ObjectId cannot exist in this collection, so it is a
missing conversation (404), which clients recover from by starting a new chat.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from src.api.db.repositories.conversations import ConversationRepository  # noqa: E402
from src.api.errors import AppError, NotFoundError, ValidationError  # noqa: E402

_EPHEMERAL_ID = "eph-1a78bb912341"


@pytest.fixture()
def repo_and_collection():
    """Repository over a stub db, plus the collection mock it will use."""
    db = MagicMock()
    collection = MagicMock()
    db.__getitem__.return_value = collection
    return ConversationRepository(db), collection


@pytest.mark.parametrize(
    "bad_id",
    ["", "not-an-objectid", "msg-123", "12345", _EPHEMERAL_ID],
)
def test_unparseable_id_is_reported_as_missing(repo_and_collection, bad_id):
    repo, _ = repo_and_collection
    with pytest.raises(NotFoundError) as raised:
        repo.require_owned(bad_id, "user-1")
    assert raised.value.status_code == 404
    assert not isinstance(raised.value, ValidationError)


@pytest.mark.parametrize("bad_id", ["", "not-an-objectid", _EPHEMERAL_ID])
def test_unparseable_id_does_not_raise_on_delete(repo_and_collection, bad_id):
    """Deleting an id that cannot exist is a no-op, not a client error."""
    repo, collection = repo_and_collection
    assert repo.delete(bad_id, "user-1") is False
    collection.delete_one.assert_not_called()


def test_unparseable_id_is_not_an_app_error_500(repo_and_collection):
    """Guard against the id leaking as an unexpected server error."""
    repo, _ = repo_and_collection
    with pytest.raises(AppError) as raised:
        repo.require_owned(_EPHEMERAL_ID, "user-1")
    assert raised.value.status_code < 500


def test_valid_object_id_still_reaches_the_query(repo_and_collection):
    """The happy path must keep parsing real ids."""
    repo, collection = repo_and_collection
    oid = ObjectId()
    sentinel = {"_id": oid, "user_id": "user-1"}
    collection.find_one.return_value = sentinel

    assert repo.require_owned(str(oid), "user-1") is sentinel
    collection.find_one.assert_called_once_with({"_id": oid, "user_id": "user-1"})


def test_record_turn_with_unusable_id_is_a_noop(repo_and_collection):
    """A turn that already produced an answer must not fail on write-back."""
    repo, collection = repo_and_collection
    repo.record_turn(_EPHEMERAL_ID, memory={"summary": "s"}, last_message="hi")
    collection.update_one.assert_not_called()

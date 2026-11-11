import os

import pytest

TEST_DB = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def conn():
    if not TEST_DB:
        pytest.skip("set TEST_DATABASE_URL to a throwaway Postgres database to run the database tests")
    from relay import db
    db.load(TEST_DB)
    c = db.connect(TEST_DB)
    yield c
    c.close()


@pytest.fixture(scope="session")
def inbox():
    from relay.support_data import build
    return build()

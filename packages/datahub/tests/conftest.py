import pytest
from signal_datahub.models import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s

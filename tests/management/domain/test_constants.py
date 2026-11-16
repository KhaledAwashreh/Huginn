from datetime import timedelta

from huginn.management.domain.constants.prospecting import PREPARING_OFFER_DEFAULT_LEASE


def test_preparing_offer_lease_is_bounded_engineering_default():
    assert timedelta(minutes=5) == PREPARING_OFFER_DEFAULT_LEASE

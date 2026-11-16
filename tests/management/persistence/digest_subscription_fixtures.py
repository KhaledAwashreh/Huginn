from uuid import uuid4

from tests.management.test_matches_query_integration import _user


def seed_digest_subscriber(conn, tag):
    user, account = _user(conn, tag)
    business = conn.execute(
        "INSERT INTO operational.businesses(owner_user_id) VALUES (%s) RETURNING id",
        (user,),
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO operational.business_recommendation_preferences(business_id) VALUES (%s)",
        (business,),
    )
    conn.execute(
        "INSERT INTO operational.account_recovery_identity(account_id,verification_required,verified_email,verified_at) VALUES (%s,true,%s,now())",
        (account, f"{uuid4()}@example.test"),
    )
    offering = conn.execute(
        "INSERT INTO operational.service_offerings(business_id,name,description) VALUES (%s,'Analytics','Reporting') RETURNING id",
        (business,),
    ).fetchone()[0]
    icp = conn.execute(
        "INSERT INTO operational.ideal_client_profiles(business_id,name) VALUES (%s,'Startups') RETURNING id",
        (business,),
    ).fetchone()[0]
    strategy = conn.execute(
        "INSERT INTO operational.client_discovery_strategies(business_id,name,service_offering_id,ideal_client_profile_id,is_active) VALUES (%s,'Weekly',%s,%s,true) RETURNING id",
        (business, offering, icp),
    ).fetchone()[0]
    return user, account, strategy

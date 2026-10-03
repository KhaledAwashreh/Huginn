from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from huginn.management.domain.client_discovery_strategy import (
    NewClientDiscoveryStrategy,
)
from huginn.management.domain.common import Page
from huginn.management.domain.ideal_client_profile import (
    IdealClientProfileChanges,
    NewIdealClientProfile,
)
from huginn.management.domain.service_offering import (
    NewServiceOffering,
    ServiceOffering,
    ServiceOfferingChanges,
)
from huginn.management.errors.handlers import sanitized_validation_shape
from huginn.management.requests.authentication import LoginRequest
from huginn.management.requests.discovery_strategy import DiscoveryStrategyCreateRequest
from huginn.management.requests.ideal_client_profile import (
    IdealClientProfileCreateRequest,
    IdealClientProfileUpdateRequest,
)
from huginn.management.requests.service_offering import (
    ServiceOfferingCreateRequest,
    ServiceOfferingUpdateRequest,
)
from huginn.management.responses.authentication import LoginResponse
from huginn.management.responses.common import PageResponse
from huginn.management.responses.service_offering import ServiceOfferingResponse
from huginn.management.transport import (
    request_to_changes,
    request_to_domain,
    response_from_domain,
)


def test_strict_request_models_reject_unknown_fields_and_coercion():
    with pytest.raises(ValidationError):
        ServiceOfferingCreateRequest.model_validate({"name": 3, "description": "Valid"})
    with pytest.raises(ValidationError):
        ServiceOfferingCreateRequest.model_validate(
            {"name": "Valid", "description": "Valid", "user_id": str(uuid4())}
        )
    with pytest.raises(ValidationError):
        LoginRequest.model_validate({"username": "alice", "password": "secret", "x": 1})


def test_patch_models_preserve_omission_null_and_empty_collection_semantics():
    patch = ServiceOfferingUpdateRequest.model_validate({"name": "Updated"})
    assert patch.supplied_fields == frozenset({"name"})
    assert patch.model_dump(exclude_unset=True) == {"name": "Updated"}
    with pytest.raises(ValidationError):
        ServiceOfferingUpdateRequest.model_validate({"description": None})

    collection_patch = IdealClientProfileUpdateRequest.model_validate(
        {"industries": [], "name": "Updated"}
    )
    assert collection_patch.supplied_fields == frozenset({"name", "industries"})
    assert collection_patch.model_dump(exclude_unset=True)["industries"] == []
    with pytest.raises(ValidationError):
        IdealClientProfileUpdateRequest.model_validate({"industries": None})


def test_uuid_strings_are_accepted_in_json_request_boundary():
    company_id = uuid4()
    body = (
        '{"name":"Target","exclusions":[{"kind":"company",'
        f'"company_id":"{company_id}"}}]}}'
    )
    parsed = IdealClientProfileCreateRequest.model_validate_json(body)
    assert parsed.exclusions[0].company_id == company_id

    strategy = DiscoveryStrategyCreateRequest.model_validate(
        {
            "name": "Target",
            "service_offering_id": str(uuid4()),
            "ideal_client_profile_id": str(uuid4()),
        }
    )
    assert isinstance(strategy.service_offering_id, type(uuid4()))


def test_request_mapping_creates_domain_values_and_tracks_patch_fields():
    owner_id = uuid4()
    create = ServiceOfferingCreateRequest.model_validate(
        {"name": "Consulting", "description": "Research"}
    )
    command = request_to_domain(create, NewServiceOffering, user_id=owner_id)
    assert command == NewServiceOffering(owner_id, "Consulting", "Research")

    patch = ServiceOfferingUpdateRequest.model_validate({"description": "New"})
    changes = request_to_changes(patch, ServiceOfferingChanges)
    assert changes.values == {"description": "New"}
    assert changes.supplied_fields == frozenset({"description"})


def test_icp_company_exclusion_uuids_are_json_values_for_create_and_patch():
    company_id = uuid4()
    body = {
        "name": "Target",
        "exclusions": [{"kind": "company", "company_id": str(company_id)}],
    }
    create = IdealClientProfileCreateRequest.model_validate(body)
    created = request_to_domain(create, NewIdealClientProfile, user_id=uuid4())
    assert created.exclusions == ({"kind": "company", "company_id": str(company_id)},)

    patch = IdealClientProfileUpdateRequest.model_validate(
        {"exclusions": body["exclusions"]}
    )
    changes = request_to_changes(patch, IdealClientProfileChanges)
    assert changes.values["exclusions"] == (
        {"kind": "company", "company_id": str(company_id)},
    )


def test_typed_strategy_uuid_references_remain_uuid_values():
    offering_id, profile_id, owner_id = uuid4(), uuid4(), uuid4()
    request = DiscoveryStrategyCreateRequest.model_validate(
        {
            "name": "Target",
            "service_offering_id": str(offering_id),
            "ideal_client_profile_id": str(profile_id),
        }
    )
    command = request_to_domain(request, NewClientDiscoveryStrategy, user_id=owner_id)
    assert command.service_offering_id == offering_id
    assert command.ideal_client_profile_id == profile_id


def test_response_models_filter_private_and_undeclared_values():
    owner_id, resource_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    domain = ServiceOffering(resource_id, owner_id, "Consulting", "Research", now, now)
    response = response_from_domain(domain, ServiceOfferingResponse)
    assert response.user_id == owner_id
    assert "user_id" in response.model_dump()
    filtered = ServiceOfferingResponse.model_validate(
        {**response.model_dump(), "password_hash": "must-not-escape"}
    )
    assert "password_hash" not in filtered.model_dump()


def test_page_mapping_validates_and_filters_every_domain_item():
    owner_id = uuid4()
    now = datetime.now(UTC)
    page = Page(
        items=(
            ServiceOffering(uuid4(), owner_id, "Consulting", "Research", now, now),
            ServiceOffering(uuid4(), owner_id, "Strategy", "Planning", now, now),
        ),
        offset=0,
        limit=50,
        has_more=False,
    )
    response = response_from_domain(page, PageResponse[ServiceOfferingResponse])
    assert len(response.items) == 2
    assert all(item.user_id == owner_id for item in response.items)
    assert all("password_hash" not in item.model_dump() for item in response.items)


def test_login_response_delivers_raw_csrf_once_as_declared_field():
    csrf = "one-time-csrf-value"
    response = LoginResponse.model_validate(
        {"csrf_token": csrf, "expires_at": datetime.now(UTC)}
    )
    assert response.model_dump()["csrf_token"] == csrf
    assert "session_token" not in response.model_dump()


def test_sanitized_native_validation_shape_keeps_location_not_secrets():
    secret = "submitted-password-value"
    shape = sanitized_validation_shape(
        [
            {
                "loc": ("body", "password"),
                "type": "string_type",
                "input": secret,
                "ctx": {"secret": secret},
                "url": "https://errors.pydantic.dev/",
            },
            {
                "loc": ("body", "attacker-secret-field"),
                "type": "extra_forbidden",
                "input": secret,
            },
        ]
    )
    assert shape.status_code == 422
    assert shape.body == {
        "detail": [
            {
                "loc": ["body", "password"],
                "type": "string_type",
                "msg": "Invalid value",
            },
            {"loc": ["body"], "type": "extra_forbidden", "msg": "Invalid value"},
        ]
    }
    assert secret not in repr(shape.body)

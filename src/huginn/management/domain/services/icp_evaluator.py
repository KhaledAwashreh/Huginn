"""Framework-independent ICP evaluation policy."""

from huginn.management.domain.entities.ideal_client_profile import IdealClientProfile
from huginn.management.domain.value_objects.icp_filter import IcpCandidateFilter


def candidate_filter(profile: IdealClientProfile) -> IcpCandidateFilter | None:
    """Build a flat filter only when every positive dimension is populated.

    Candidate selection receives the three independent dimensions and a single
    global exclusion set. It must implement OR within each dimension, AND
    across dimensions, then apply exclusions as global vetoes. No Cartesian
    combinations are assembled here.
    """
    if not profile.industries or not profile.company_sizes or not profile.geographies:
        return None
    return IcpCandidateFilter(
        profile.industries,
        profile.company_sizes,
        profile.geographies,
        profile.exclusions,
    )

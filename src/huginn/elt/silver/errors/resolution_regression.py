from huginn.elt.silver.models.resolution_regression import ResolutionRegression


class ResolutionRegressionError(RuntimeError):
    """A source cohort exceeded the pre-write loss limit; see ADR-0018."""

    def __init__(self, regression: ResolutionRegression) -> None:
        """Expose operator-safe counts for the blocked source cohort."""
        self.regression = regression
        source_context = f" for source {regression.source}" if regression.source else ""
        super().__init__(
            f"Resolution batch blocked{source_context}: {regression.downgraded} of "
            f"{regression.previously_resolved} previously domain-normalized "
            f"identities would be downgraded, exceeding the "
            f"{regression.max_downgrade_percent}% limit. "
            "Review the batch and resolver health before retrying."
        )

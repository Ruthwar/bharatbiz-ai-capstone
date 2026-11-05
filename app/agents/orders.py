def fill_order(requested: int, available: int) -> tuple[int, int]:
    """Return (fulfilled, unmet) quantities in the dataset's explicit base unit."""
    fulfilled = min(max(requested, 0), max(available, 0))
    return fulfilled, max(requested - fulfilled, 0)

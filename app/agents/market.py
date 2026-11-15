from app.schemas.retail import MarketTheme


def _unique_observations(rows: list[dict]) -> list[dict]:
    unique = []
    seen = set()
    for row in rows:
        fingerprint = (
            row.get("reporter_id"),
            row.get("competitor_name"),
            row.get("product_label"),
            row.get("offer"),
            row.get("area"),
            row.get("observation_text"),
        )
        if fingerprint not in seen:
            seen.add(fingerprint)
            unique.append(row)
    return unique


def group_themes(
    observations: list[dict],
    signal_type: str | None = None,
    min_reporters: int = 1,
) -> list[MarketTheme]:
    groups = {}
    for observation in observations:
        if signal_type and observation["signal_type"] != signal_type:
            continue
        key = (
            observation["signal_type"],
            observation["subject"],
            observation.get("competitor_name") or "unknown",
            observation.get("product_label") or "unknown",
            observation.get("offer") or "",
            observation.get("area") or "unknown",
        )
        groups.setdefault(key, []).append(observation)

    themes = []
    for (signal, subject, competitor, product, offer, area), rows in groups.items():
        unique = _unique_observations(rows)
        reporters = {row.get("reporter_id") for row in unique if row.get("reporter_id")}
        if len(reporters) < min_reporters:
            continue
        if signal == "competitor_observation":
            label = "corroborated_unverified" if len(reporters) >= 2 else "single_reporter_unverified"
        else:
            label = "reported_unverified"
        themes.append(
            MarketTheme(
                signal_type=signal,
                subject=subject,
                competitor_name=competitor,
                product_label=product,
                offer=offer,
                area=area,
                report_count=len(unique),
                distinct_reporters=len(reporters),
                first_seen=min(row["observed_at"] for row in unique),
                last_seen=max(row["observed_at"] for row in unique),
                label=label,
                example_evidence=[row["evidence_span"] for row in unique[:3]],
                event_ids=list(dict.fromkeys(row["event_id"] for row in unique)),
            )
        )
    return sorted(
        themes,
        key=lambda theme: (
            -theme.distinct_reporters,
            -theme.report_count,
            theme.signal_type,
            theme.subject,
            theme.competitor_name,
            theme.offer,
            theme.area,
        ),
    )

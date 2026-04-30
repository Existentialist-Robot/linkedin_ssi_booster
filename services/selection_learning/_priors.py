"""Acceptance priors and feature-boost logic."""

from __future__ import annotations

from pathlib import Path

from services.selection_learning._constants import CANDIDATES_LOG_PATH
from services.selection_learning._models import FeaturePrior
from services.selection_learning._storage import JsonlStore


class PriorService:
    """Compute and query acceptance priors from labeled candidates."""

    @staticmethod
    def compute_acceptance_priors(
        path: Path | None = None,
        include_themes: bool = True,
        min_theme_count: int = 3,
    ) -> dict[tuple[str, str], FeaturePrior]:
        """Compute Beta-smoothed priors per (source, ssi_component)."""
        target = path or CANDIDATES_LOG_PATH
        records = [r for r in JsonlStore.read(target) if r.get("selected") is not None]

        counts: dict[tuple[str, str], list[int]] = {}
        for rec in records:
            key = (rec.get("article_source", ""), rec.get("ssi_component", ""))
            if key not in counts:
                counts[key] = [0, 0]
            counts[key][1] += 1
            if rec.get("selected") is True:
                counts[key][0] += 1

        priors: dict[tuple[str, str], FeaturePrior] = {}
        for (source, ssi), (n_sel, n_tot) in counts.items():
            raw_rate = n_sel / max(1, n_tot)
            if n_tot >= 5:
                if raw_rate > 0.70:
                    boost = 1.2
                elif raw_rate < 0.30:
                    boost = 0.8
                else:
                    boost = 1.0
            else:
                boost = 1.0

            priors[(source, ssi)] = FeaturePrior(
                feature_key="source+ssi",
                feature_value=f"{source}|{ssi}",
                n_selected=n_sel,
                n_total=n_tot,
                acceptance_rate=(n_sel + 1) / (n_tot + 2),
                boost_factor=boost,
            )

        if include_themes:
            theme_counts: dict[str, list[int]] = {}
            for rec in records:
                themes = rec.get("themes", [])
                selected = rec.get("selected") is True
                for theme in themes:
                    if theme not in theme_counts:
                        theme_counts[theme] = [0, 0]
                    theme_counts[theme][1] += 1
                    if selected:
                        theme_counts[theme][0] += 1

            for theme, (n_sel, n_tot) in theme_counts.items():
                if n_tot < min_theme_count:
                    continue
                raw_rate = n_sel / max(1, n_tot)
                if n_tot >= 5:
                    if raw_rate > 0.70:
                        boost = 1.15
                    elif raw_rate < 0.30:
                        boost = 0.85
                    else:
                        boost = 1.0
                else:
                    boost = 1.0

                priors[(f"theme:{theme}", "")] = FeaturePrior(
                    feature_key="theme",
                    feature_value=theme,
                    n_selected=n_sel,
                    n_total=n_tot,
                    acceptance_rate=(n_sel + 1) / (n_tot + 2),
                    boost_factor=boost,
                )

        return priors

    @staticmethod
    def get_acceptance_rate(
        source: str,
        ssi_component: str,
        priors: dict[tuple[str, str], FeaturePrior],
    ) -> float:
        """Return acceptance rate for (source, ssi_component), with fallbacks."""
        key = (source, ssi_component)
        if key in priors:
            return priors[key].acceptance_rate

        source_rates = [
            p.acceptance_rate
            for (src, _), p in priors.items()
            if not src.startswith("theme:") and src == source
        ]
        if source_rates:
            return sum(source_rates) / len(source_rates)

        return 0.5

    @staticmethod
    def get_boost_factor(
        source: str,
        ssi_component: str,
        themes: list[str],
        priors: dict[tuple[str, str], FeaturePrior],
    ) -> float:
        """Return combined boost factor for source/ssi/themes."""
        boost = 1.0

        key = (source, ssi_component)
        if key in priors:
            boost *= priors[key].boost_factor

        theme_boosts: list[float] = []
        for theme in themes:
            theme_key = (f"theme:{theme}", "")
            if theme_key in priors:
                theme_boosts.append(priors[theme_key].boost_factor)

        if theme_boosts:
            boost *= sum(theme_boosts) / len(theme_boosts)

        return max(0.5, min(2.0, boost))

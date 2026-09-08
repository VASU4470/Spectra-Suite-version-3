"""Shared plotting colors and legend locations."""

BASIC_COLORS = (
    ("Blue", "#1f77b4"), ("Orange", "#ff7f0e"),
    ("Green", "#2ca02c"), ("Red", "#d62728"),
    ("Purple", "#9467bd"), ("Brown", "#8c564b"),
    ("Pink", "#e377c2"), ("Gray", "#7f7f7f"),
    ("Olive", "#bcbd22"), ("Cyan", "#17becf"),
    ("Black", "#111827"),
)

PLOT_COLORS = tuple(value for _name, value in BASIC_COLORS[:-1])

LEGEND_LOCATIONS = (
    ("Automatic", "best"), ("Upper right", "upper right"),
    ("Upper left", "upper left"), ("Lower right", "lower right"),
    ("Lower left", "lower left"), ("Upper center", "upper center"),
    ("Lower center", "lower center"), ("Center right", "center right"),
    ("Center left", "center left"), ("Center", "center"),
)

import sys


def validate_weights(weight_name: float, weight_geo: float):
    """Validate that weights are in [0,1] and sum approximately to 1.0."""
    for name, val in [("--weight-name", weight_name), ("--weight-geo", weight_geo)]:
        if not 0.0 <= val <= 1.0:
            print(f"ERROR: {name} must be between 0.0 and 1.0, got {val}")
            sys.exit(1)
    total = weight_name + weight_geo
    if abs(total - 1.0) > 0.01:
        print(f"ERROR: --weight-name ({weight_name}) + --weight-geo ({weight_geo}) = {total}, must sum to 1.0")
        sys.exit(1)


def validate_threshold(threshold: float):
    if not 0.0 <= threshold <= 1.0:
        print(f"ERROR: --threshold must be between 0.0 and 1.0, got {threshold}")
        sys.exit(1)

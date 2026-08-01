from collections.abc import Mapping


def json_values_are_identical(left: object, right: object) -> bool:
    """Compare JSON values without conflating booleans and numbers."""
    if type(left) is not type(right):
        return False
    if isinstance(left, Mapping):
        if left.keys() != right.keys():
            return False
        return all(
            json_values_are_identical(left[key], right[key])
            for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            json_values_are_identical(left_value, right_value)
            for left_value, right_value in zip(left, right)
        )
    return left == right

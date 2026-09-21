"""PEP 695 syntax fixture for the classic Pylint toolchain contract."""

type Pair[T] = tuple[T, T]


def pair[T](item: T) -> Pair[T]:
    """Return a pair containing ``item`` twice."""
    return item, item

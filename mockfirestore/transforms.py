from abc import ABCMeta, abstractmethod
from typing import Tuple, Dict, List, Any

from mockfirestore._helpers import get_by_path, set_by_path, get_document_iterator


class _Transform(metaclass=ABCMeta):
    """Abstract transformation class"""

    @abstractmethod
    def __call__(self):
        raise NotImplementedError


class _ValueList(object):
    """Read-only list of values.
    Args:
        values (List | Tuple): values held in the helper.
    """

    def __init__(self, values) -> None:
        if not isinstance(values, (list, tuple)):
            raise ValueError("'values' must be a list or tuple.")

        if len(values) == 0:
            raise ValueError("'values' must be non-empty.")

        self._values = list(values)

    @property
    def values(self):
        """Values to append.
        Returns (List):
            values to be appended by the transform.
        """
        return self._values


class ArrayUnion(_Transform, _ValueList):
    """Field transform: appends missing values to an array field.
    Args:
        values (List | Tuple): values to append.
    """

    def __call__(self, document: Dict[str, Any], path: List[str]) -> List[Any]:
        try:
            item = get_by_path(document, path)
        except (TypeError, KeyError):
            item = []
        return item + self.values


class ArrayRemove(_Transform, _ValueList):
    """Field transform: remove values from an array field.
    Args:
        values (List | Tuple): values to remove.
    """

    def __call__(self, document: Dict[str, Any], path: List[str]) -> List[Any]:
        try:
            item = get_by_path(document, path)
        except (TypeError, KeyError):
            item = []

        return list(set(item).difference(set(self.values)))


class _NumericValue(object):
    """Hold a single integer / float value.
    Args:
        value (int | float): value held in the helper.
    """

    def __init__(self, value) -> None:
        if not isinstance(value, (int, float)):
            raise ValueError("Pass an integer / float value.")

        self._value = value

    @property
    def value(self):
        """Value used by the transform.
        Returns:
            (Integer | Float) value passed in the constructor.
        """
        return self._value


class Increment(_Transform, _NumericValue):
    """Field transform: increment a numeric field with specified value.
    Args:
        value (int | float): value used to increment the field.
    """

    def __call__(self, document: Dict[str, Any], path: List[str]) -> Tuple[int, float]:
        try:
            item = get_by_path(document, path)
        except (TypeError, KeyError):
            item = 0
        return item + self.value


class Maximum(_Transform, _NumericValue):
    """Field transform: bound numeric field with specified value.
    Args:
        value (int | float): value used to bound the field.
    """

    def __call__(self, document: Dict[str, Any], path: List[str]) -> Tuple[int, float]:
        try:
            item, exists = get_by_path(document, path), True
        except (TypeError, KeyError):
            exists = False
        if exists and isinstance(item, (float, int)):
            return max(item, self.value)
        else:
            return self.value


class Minimum(_Transform, _NumericValue):
    """Field transform: bound numeric field with specified value.
    Args:
        value (int | float): value used to bound the field.
    """

    def __call__(self, document: Dict[str, Any], path: List[str]) -> Tuple[int, float]:
        try:
            item, exists = get_by_path(document, path), True
        except (TypeError, KeyError):
            exists = False
        if exists and isinstance(item, (float, int)):
            return min(item, self.value)
        else:
            return self.value


def _apply_transformations(document: Dict[str, Any], data: Dict[str, Any]):
    """Handles MockFirestore transformations
    """

    increments = {}
    arr_unions = {}
    for key, value in get_document_iterator(data):
        path = key.split(".")
        if isinstance(value, _Transform):
            set_by_path(data, path, value(document, path))

        # Firestore transformations
        # Unfortunately, we can't use `isinstance` here because that would require
        # us to declare google-cloud-firestore as a dependency for this library.
        # However, it's somewhat strange that the mocked version of the library
        # requires the library itself, so we'll just leverage this heuristic as a
        # means of identifying it.
        #
        # Furthermore, we don't hardcode the full module name, since the original
        # library seems to use a thin shim to perform versioning. e.g. at the time
        # of writing, the full module name is `google.cloud.firestore_v1.transforms`,
        # and it can evolve to `firestore_v2` in the future.
        transformer = value.__class__.__name__
        if transformer == "Increment":
            increments[key] = value.value
        elif transformer == "ArrayUnion":
            arr_unions[key] = value.values

    def _update_data_with_firestore_transforms(new_values: dict, default: Any):
        """Helper function to update the data using the
        Firestore Transformations
        """
        for key, value in new_values.items():
            path = key.split(".")
            try:
                item = get_by_path(document, path)
            except (TypeError, KeyError):
                item = default
            set_by_path(data, path, item + value)

    _update_data_with_firestore_transforms(increments, 0)
    _update_data_with_firestore_transforms(arr_unions, [])

    document.update(data)

"""G5 B4: the name of a model as people read it. A work model is a path such as
`/models/qwen/Qwen3.6-35B-A3B`; only the last part is shown."""


def model_label(model: str) -> str:
    """The last part of a model path ("" stays ""). Windows and Linux separators both count."""
    return model.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]

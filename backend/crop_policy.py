"""Versioned crop geometry so in-flight scans can finish after a deployment."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CropPolicy:
    version: int = 1
    first_peak_margin: float = 0
    preserve_original_width: bool = False
    original_out_limit: float = .64


# Crop versions are replay contracts: future geometry changes need a new version.
LEGACY_CROPS = CropPolicy()
ROBUST_CROPS = CropPolicy(version=2, first_peak_margin=.10)


def crop_policy(version=None):
    if version is None or (type(version) is str and version == '1') or (type(version) is int and version == 1):
        return LEGACY_CROPS
    if (type(version) is str and version == '2') or (type(version) is int and version == 2):
        return ROBUST_CROPS
    raise ValueError('Unsupported crop version. Refresh and process the photo again.')

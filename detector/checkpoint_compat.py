"""Compatibility shim for class-aware YOLO checkpoints."""

import sys
from scripts.train_classaware import ClassAwareDetectionModel

# The checkpoint was saved when the training script ran as __main__.
main_module = sys.modules["__main__"]
main_module.ClassAwareDetectionModel = ClassAwareDetectionModel

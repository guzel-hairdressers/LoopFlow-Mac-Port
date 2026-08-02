# Non-Temporary Unit Tests (`tests/unit`)

This directory contains permanent, non-temporary unit tests for the LoopFlow codebase (converters, layer matching, serialization, geometric utilities, etc.).

## Best Practices & Standards

1. **Isolation**: Unit tests must execute quickly without requiring live running instances of Rhino or Blender where possible, using mocks or direct library calls (e.g. `rhino3dm`).
2. **Determinism**: Tests must be 100% deterministic and reproducible across macOS and Windows environments.
3. **Naming Convention**: Test files should follow the `test_<module_name>.py` naming pattern.

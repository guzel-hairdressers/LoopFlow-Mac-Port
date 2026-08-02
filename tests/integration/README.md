# Non-Temporary Integration Tests (`tests/integration`)

This directory contains permanent integration tests for end-to-end LiveLink synchronization between Rhino 8 and Blender 5.x.

## Best Practices & Standards

1. **Integration Coverage**: Verify full file roundtrips, delta sync json parsing, layer GUID hierarchy matching, and instance definition population.
2. **Headless Execution**: Integration tests should support headless execution via `blender --background --python` scripts.

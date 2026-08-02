name: Bug Report
description: Create a report to help us improve LoopFlow
title: '[BUG] '
labels: bug
assignees: guzel-hairdressers

body:
  - type: textarea
    id: description
    attributes:
      label: Bug Description
      description: A clear and concise description of what the bug is.
    validations:
      required: true

  - type: dropdown
    id: os
    attributes:
      label: Operating System
      options:
        - macOS (Apple Silicon M1/M2/M3/M4)
        - macOS (Intel)
        - Windows 10/11 (x64)
    validations:
      required: true

  - type: input
    id: versions
    attributes:
      label: Software Versions
      description: e.g. Rhino 8.12 + Blender 5.2.0
    validations:
      required: true

  - type: textarea
    id: steps
    attributes:
      label: Steps To Reproduce
      description: Steps to reproduce the behavior.
    validations:
      required: true

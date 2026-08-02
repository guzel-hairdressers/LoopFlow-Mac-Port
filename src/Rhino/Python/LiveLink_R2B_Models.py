# -*- coding: utf-8 -*-
"""
=================================================
LiveLink Rhino to Blender (Model Exporter)
=================================================
Script Name        : LiveLink_R2B_Models
Version            : v2.3
Date               : 2026-07-31
Author             : LoopFlow Team
Environment        : Rhino 8 / CPython 3.9

[Description]
Entry point for Fast Link model export (zero prompts).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from LiveLink_R2B_Fast import FastLinkExport

def RhinoLiveLinkSync():
    # Instant one-click Fast Link export with zero prompts or dialogs
    FastLinkExport()

if __name__ == "__main__":
    RhinoLiveLinkSync()

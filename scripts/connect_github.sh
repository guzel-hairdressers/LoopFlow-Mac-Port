#!/usr/bin/env bash
# 🚀 1-Click GitHub Repository Connection Script
# Author: Ruslan Fazulzyanov (guzel-hairdressers)

echo "======================================================================"
echo "Connecting LoopFlow to GitHub: guzel-hairdressers/LoopFlow_Rhino-to-Blender-Sync"
echo "======================================================================"

# Set Remote URL to your GitHub account
git remote remove origin 2>/dev/null
git remote add origin https://github.com/guzel-hairdressers/LoopFlow_Rhino-to-Blender-Sync.git

# Stage all restructured project files
git add .

# Create clean commit
git commit -m "feat: Restructure project layout & add high-performance macOS/Windows sync engine by Ruslan Fazulzyanov (guzel-hairdressers)"

# Ensure default branch is main
git branch -M main

echo ""
echo "======================================================================"
echo "Local repository committed & configured for remote origin!"
echo "To push to GitHub, run:"
echo "   git push -u origin main"
echo "======================================================================"

#!/usr/bin/env bash
# 🚀 1-Click GitHub Repository Connection Script
# Author: Ruslan F (guzel-hairdressers)

echo "======================================================================"
echo "Connecting LoopFlow to GitHub: guzel-hairdressers/LoopFlow-Mac-Port"
echo "======================================================================"

# Set Remote URL to your GitHub account repository LoopFlow-Mac-Port
git remote remove origin 2>/dev/null
git remote add origin https://github.com/guzel-hairdressers/LoopFlow-Mac-Port.git

# Stage all restructured project files
git add .

# Create clean commit
git commit -m "feat: Restructure project layout & add high-performance macOS/Windows sync engine by Ruslan F"

# Ensure default branch is main
git branch -M main

echo ""
echo "======================================================================"
echo "Local repository committed & configured for origin: LoopFlow-Mac-Port"
echo "======================================================================"

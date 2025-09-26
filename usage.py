#!/usr/bin/env python3
"""
GitHub Issue Migration - Usage Helper
=====================================

This helper script provides guidance on using the issue migration tools.
"""

import os
import sys

def print_header():
    """Print the application header"""
    print("=" * 70)
    print("🚀 GitHub Issue Migration Tool")
    print("=" * 70)
    print()

def check_setup():
    """Check if the basic setup is complete"""
    issues = []
    
    # Check if .env file exists
    if not os.path.exists('.env'):
        issues.append("❌ .env file not found")
        issues.append("   → Copy .env.example to .env and fill in your values")
    else:
        print("✅ .env file found")
    
    # Check if required files exist
    required_files = [
        'orchestrator.py',
        'issue_migrator.py', 
        'label_synchronizer.py',
        'create_project_labels.py',
        'project_v2_sync.py',
        'requirements.txt'
    ]
    
    missing_files = [f for f in required_files if not os.path.exists(f)]
    if missing_files:
        issues.extend([f"❌ Missing file: {f}" for f in missing_files])
    else:
        print("✅ All required scripts found")
    
    # Check if dependencies are installed
    try:
        import requests
        import dotenv
        print("✅ Dependencies installed")
    except ImportError as e:
        issues.append(f"❌ Missing dependency: {e.name}")
        issues.append("   → Run: pip install -r requirements.txt")
    
    return issues

def print_usage_options():
    """Print usage options"""
    print("\n" + "=" * 70)
    print("📋 Usage Options")
    print("=" * 70)
    
    print("\n🎯 Option 1: Run the Orchestrator (Recommended)")
    print("   This runs all scripts in the correct order:")
    print("   python3 orchestrator.py")
    
    print("\n🔧 Option 2: Run Individual Scripts")
    print("   Run scripts manually in this order:")
    print("   1. python3 issue_migrator.py")
    print("   2. python3 label_synchronizer.py")
    print("   3. python3 create_project_labels.py")
    print("   4. python3 project_v2_sync.py")

def print_setup_steps():
    """Print setup instructions"""
    print("\n" + "=" * 70)
    print("⚙️  Setup Steps")
    print("=" * 70)
    
    print("\n1. Install Dependencies:")
    print("   pip install -r requirements.txt")
    
    print("\n2. Configure Environment:")
    print("   cp .env.example .env")
    print("   # Edit .env with your values")
    
    print("\n3. Required GitHub Token Scopes:")
    print("   ✅ repo (Repository access)")
    print("   ✅ project (GitHub Projects V2 access)")
    print("   ✅ admin:org (Organization access)")
    
    print("\n4. Run Migration:")
    print("   python3 orchestrator.py")

def main():
    """Main function"""
    print_header()
    
    issues = check_setup()
    
    if issues:
        print("⚠️  Setup Issues Found:")
        print()
        for issue in issues:
            print(f"   {issue}")
        print()
        print_setup_steps()
    else:
        print("🎉 Setup looks good!")
        print_usage_options()
        
        print("\n" + "=" * 70)
        print("💡 Tips")
        print("=" * 70)
        print("• Start with a test repository to verify everything works")
        print("• The orchestrator provides detailed reports on execution")
        print("• Scripts can be run multiple times safely (idempotent)")
        print("• Check README.md for detailed documentation")
    
    print("\n" + "=" * 70)
    print("📚 For more information, see README.md")
    print("=" * 70)

if __name__ == "__main__":
    main()
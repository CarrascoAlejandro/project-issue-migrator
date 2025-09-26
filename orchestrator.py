#!/usr/bin/env python3
"""
Orchestrator Script for GitHub Issue Migration Project
=====================================================

This script executes all the migration scripts in the correct order:
1. issue_migrator.py - Migrates issues from source to destination repositories
2. label_synchronizer.py - Synchronizes labels between migrated issues
3. create_project_labels.py - Creates project-related labels in destination repos
4. project_v2_sync.py - Synchronizes project V2 items and field values

If any script fails, the orchestrator will continue with the remaining ones
and provide a comprehensive report at the end.
"""

import os
import sys
import subprocess
import time
from datetime import datetime
from typing import Dict, List, Tuple
from dataclasses import dataclass

@dataclass
class ScriptResult:
    """Represents the result of executing a script"""
    name: str
    success: bool
    execution_time: float
    error_message: str = ""
    output: str = ""

class MigrationOrchestrator:
    """Orchestrates the execution of all migration scripts"""
    
    SCRIPTS = [
        ("issue_migrator", "issue_migrator.py", "Migrates issues from source to destination repositories"),
        ("label_synchronizer", "label_synchronizer.py", "Synchronizes labels between migrated issues"),
        ("create_project_labels", "create_project_labels.py", "Creates project-related labels in destination repos"),
        ("project_v2_sync", "project_v2_sync.py", "Synchronizes project V2 items and field values")
    ]
    
    def __init__(self):
        self.results: List[ScriptResult] = []
        self.start_time = datetime.now()
    
    def log(self, message: str, level: str = "INFO"):
        """Print formatted log message"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
    
    def check_environment(self) -> bool:
        """Check if all required environment variables are set"""
        required_vars = ["GITHUB_TOKEN", "ORG_SOURCE", "ORG_DEST", "REPOS"]
        missing_vars = []
        
        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            self.log(f"❌ Missing required environment variables: {', '.join(missing_vars)}", "ERROR")
            self.log("Please ensure all required variables are set in your .env file", "ERROR")
            return False
        
        self.log("✅ All required environment variables are set", "INFO")
        return True
    
    def run_script(self, script_name: str, script_file: str, description: str) -> ScriptResult:
        """Execute a single script and return the result"""
        self.log(f"🚀 Starting {script_name}: {description}")
        
        start_time = time.time()
        
        try:
            # Run the script using subprocess
            result = subprocess.run(
                [sys.executable, script_file],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout per script
            )
            
            execution_time = time.time() - start_time
            
            if result.returncode == 0:
                self.log(f"✅ {script_name} completed successfully in {execution_time:.2f}s")
                return ScriptResult(
                    name=script_name,
                    success=True,
                    execution_time=execution_time,
                    output=result.stdout
                )
            else:
                self.log(f"❌ {script_name} failed with return code {result.returncode}", "ERROR")
                return ScriptResult(
                    name=script_name,
                    success=False,
                    execution_time=execution_time,
                    error_message=result.stderr,
                    output=result.stdout
                )
        
        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            self.log(f"⏰ {script_name} timed out after {execution_time:.2f}s", "ERROR")
            return ScriptResult(
                name=script_name,
                success=False,
                execution_time=execution_time,
                error_message="Script execution timed out (5 minutes)"
            )
        
        except Exception as e:
            execution_time = time.time() - start_time
            self.log(f"💥 {script_name} crashed with exception: {str(e)}", "ERROR")
            return ScriptResult(
                name=script_name,
                success=False,
                execution_time=execution_time,
                error_message=str(e)
            )
    
    def run_all_scripts(self):
        """Execute all scripts in order"""
        self.log("🎯 Starting GitHub Issue Migration Orchestrator")
        self.log(f"📅 Execution started at: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        if not self.check_environment():
            sys.exit(1)
        
        # Execute each script
        for script_name, script_file, description in self.SCRIPTS:
            if not os.path.exists(script_file):
                self.log(f"⚠️ Script file {script_file} not found, skipping {script_name}", "WARNING")
                self.results.append(ScriptResult(
                    name=script_name,
                    success=False,
                    execution_time=0,
                    error_message=f"Script file {script_file} not found"
                ))
                continue
            
            result = self.run_script(script_name, script_file, description)
            self.results.append(result)
            
            # Brief pause between scripts
            time.sleep(1)
        
        # Generate final report
        self.generate_report()
    
    def generate_report(self):
        """Generate and display a comprehensive execution report"""
        end_time = datetime.now()
        total_duration = end_time - self.start_time
        
        self._print_report_header(total_duration)
        self._print_detailed_results()
        self._print_recommendations()
        self._print_report_footer(end_time)
    
    def _print_report_header(self, total_duration):
        """Print report header with summary statistics"""
        print("\n" + "=" * 80)
        print("📊 MIGRATION ORCHESTRATOR EXECUTION REPORT")
        print("=" * 80)
        
        successful_scripts = sum(1 for r in self.results if r.success)
        failed_scripts = len(self.results) - successful_scripts
        total_execution_time = sum(r.execution_time for r in self.results)
        
        print(f"⏱️  Total Duration: {total_duration}")
        print(f"🔢 Scripts Executed: {len(self.results)}")
        print(f"✅ Successful: {successful_scripts}")
        print(f"❌ Failed: {failed_scripts}")
        print(f"⚡ Total Script Time: {total_execution_time:.2f} seconds")
        print(f"📈 Success Rate: {(successful_scripts/len(self.results)*100):.1f}%" if self.results else "0%")
    
    def _print_detailed_results(self):
        """Print detailed results for each script"""
        print("\n" + "-" * 80)
        print("📋 DETAILED RESULTS")
        print("-" * 80)
        
        for i, result in enumerate(self.results, 1):
            self._print_script_result(i, result)
    
    def _print_script_result(self, index: int, result: ScriptResult):
        """Print result for a single script"""
        status_icon = "✅" if result.success else "❌"
        print(f"\n{index}. {status_icon} {result.name.upper()}")
        print(f"   Duration: {result.execution_time:.2f} seconds")
        print(f"   Status: {'SUCCESS' if result.success else 'FAILED'}")
        
        if not result.success and result.error_message:
            print(f"   Error: {result.error_message}")
        
        self._print_script_output(result.output)
    
    def _print_script_output(self, output: str):
        """Print script output, truncating if necessary"""
        if not output:
            return
        
        output_lines = output.strip().split('\n')
        if len(output_lines) > 3:
            print("   Output (last 3 lines):")
            for line in output_lines[-3:]:
                print(f"     {line}")
        else:
            print("   Output:")
            for line in output_lines:
                print(f"     {line}")
    
    def _print_recommendations(self):
        """Print recommendations based on execution results"""
        print("\n" + "-" * 80)
        print("💡 RECOMMENDATIONS")
        print("-" * 80)
        
        failed_scripts = [r for r in self.results if not r.success]
        
        if not failed_scripts:
            print("🎉 All scripts executed successfully! Your migration is complete.")
        else:
            print("⚠️  Some scripts failed. Consider the following actions:")
            self._print_failure_recommendations(failed_scripts)
    
    def _print_failure_recommendations(self, failed_scripts: List[ScriptResult]):
        """Print specific recommendations for failed scripts"""
        for result in failed_scripts:
            print(f"   • Check {result.name}.py logs and fix any issues")
            self._print_specific_error_advice(result)
        
        print("   • Re-run individual scripts manually to debug issues")
        print("   • Check your .env file for correct configuration")
        print("   • Verify GitHub API token has sufficient permissions")
    
    def _print_specific_error_advice(self, result: ScriptResult):
        """Print specific advice based on error message"""
        if "not found" in result.error_message:
            print(f"     - Ensure {result.name}.py exists in the current directory")
        elif "timeout" in result.error_message.lower():
            print(f"     - Consider increasing timeout or optimizing {result.name}.py")
        elif result.error_message:
            print(f"     - Review error: {result.error_message[:100]}...")
    
    def _print_report_footer(self, end_time):
        """Print report footer"""
        print("\n" + "=" * 80)
        print(f"🏁 Report generated at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

def main():
    """Main entry point"""
    orchestrator = MigrationOrchestrator()
    orchestrator.run_all_scripts()

if __name__ == "__main__":
    main()
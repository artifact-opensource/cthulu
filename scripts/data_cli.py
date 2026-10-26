#!/usr/bin/env python3
"""
Cthulu Data Management CLI

Provides storage monitoring, health checks, cleanup, and export capabilities
for all data endpoints in the Cthulu system.

Usage:
    python -m scripts.data_cli status          # Show storage usage summary
    python -m scripts.data_cli health          # Check all data endpoint health
    python -m scripts.data_cli cleanup [--days N] [--dry-run]  # Cleanup old data
    python -m scripts.data_cli export [--output DIR]  # Export data for ML training
    python -m scripts.data_cli watch           # Real-time monitoring

Examples:
    python -m scripts.data_cli status
    python -m scripts.data_cli cleanup --days 30 --dry-run
    python -m scripts.data_cli export --output ./exports
"""

import argparse
import os
import sys
import sqlite3
import gzip
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class StorageInfo:
    """Storage information for a data endpoint."""
    path: str
    exists: bool
    size_bytes: int
    file_count: int
    last_modified: Optional[datetime]
    is_writable: bool
    
    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)
    
    @property
    def size_human(self) -> str:
        if self.size_bytes < 1024:
            return f"{self.size_bytes} B"
        elif self.size_bytes < 1024 * 1024:
            return f"{self.size_bytes / 1024:.1f} KB"
        elif self.size_bytes < 1024 * 1024 * 1024:
            return f"{self.size_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{self.size_bytes / (1024 * 1024 * 1024):.2f} GB"


@dataclass
class DatabaseInfo:
    """Information about a SQLite database."""
    path: str
    exists: bool
    size_bytes: int
    tables: Dict[str, int]  # table_name -> row_count
    is_writable: bool
    error: Optional[str] = None


class DataCLI:
    """Data management CLI for Cthulu."""
    
    # Data directories to monitor
    DATA_DIRS = {
        'ML_RL Events': 'ML_RL/data/raw',
        'ML_RL Training': 'ML_RL/data/training',
        'ML_RL Tier Optimizer': 'ML_RL/data/tier_optimizer',
        'ML_RL Metrics': 'ML_RL/data/metrics',
        'ML_RL Models': 'ML_RL/models',
        'Cognition Events': 'cognition/data/raw',
        'Cognition Models': 'cognition/data/models',
        'Cognition Tier Optimizer': 'cognition/data/tier_optimizer',
        'News Cache': 'news/cache',
        'Vectors': 'vectors',
        'Data': 'data',
        'Backtest Reports': 'backtesting/reports',
    }
    
    # SQLite databases to monitor
    DATABASES = [
        'cthulu.db',
        'Cthulu_ultra_aggressive.db',
        'cthulu_aggressive.db',
        'cthulu_balanced.db',
        'cthulu_conservative.db',
        'data/herald.db',
        'data/vector_fallback.db',
        'temp_prov.db',
    ]
    
    def __init__(self, project_root: Path = PROJECT_ROOT):
        self.root = project_root
    
    def get_dir_info(self, name: str, rel_path: str) -> StorageInfo:
        """Get storage info for a directory."""
        full_path = self.root / rel_path
        
        if not full_path.exists():
            return StorageInfo(
                path=rel_path,
                exists=False,
                size_bytes=0,
                file_count=0,
                last_modified=None,
                is_writable=False
            )
        
        # Calculate size and file count
        total_size = 0
        file_count = 0
        latest_time = None
        
        try:
            for f in full_path.rglob('*'):
                if f.is_file():
                    file_count += 1
                    try:
                        stat = f.stat()
                        total_size += stat.st_size
                        mtime = datetime.fromtimestamp(stat.st_mtime)
                        if latest_time is None or mtime > latest_time:
                            latest_time = mtime
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass
        
        # Check writability
        is_writable = False
        try:
            test_file = full_path / '_cli_write_test.tmp'
            test_file.write_text('test')
            test_file.unlink()
            is_writable = True
        except (OSError, PermissionError):
            pass
        
        return StorageInfo(
            path=rel_path,
            exists=True,
            size_bytes=total_size,
            file_count=file_count,
            last_modified=latest_time,
            is_writable=is_writable
        )
    
    def get_db_info(self, rel_path: str) -> DatabaseInfo:
        """Get info for a SQLite database."""
        full_path = self.root / rel_path
        
        if not full_path.exists():
            return DatabaseInfo(
                path=rel_path,
                exists=False,
                size_bytes=0,
                tables={},
                is_writable=False
            )
        
        size_bytes = full_path.stat().st_size
        tables = {}
        is_writable = False
        error = None
        
        try:
            conn = sqlite3.connect(str(full_path), timeout=5)
            cursor = conn.cursor()
            
            # Get table names
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            table_names = [row[0] for row in cursor.fetchall()]
            
            # Get row counts
            for table in table_names:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    tables[table] = cursor.fetchone()[0]
                except sqlite3.Error:
                    tables[table] = -1
            
            # Test writability
            try:
                cursor.execute("CREATE TABLE IF NOT EXISTS _cli_write_test (id INTEGER)")
                cursor.execute("DROP TABLE IF EXISTS _cli_write_test")
                conn.commit()
                is_writable = True
            except sqlite3.Error:
                pass
            
            conn.close()
        except sqlite3.Error as e:
            error = str(e)
        
        return DatabaseInfo(
            path=rel_path,
            exists=True,
            size_bytes=size_bytes,
            tables=tables,
            is_writable=is_writable,
            error=error
        )
    
    def cmd_status(self, args):
        """Show storage usage summary."""
        print("\n" + "=" * 70)
        print("📊 CTHULU DATA STORAGE STATUS")
        print("=" * 70)
        
        total_size = 0
        total_files = 0
        
        # Data directories
        print("\n📁 DATA DIRECTORIES")
        print("-" * 70)
        print(f"{'Name':<25} {'Files':>8} {'Size':>12} {'Last Modified':>20}")
        print("-" * 70)
        
        for name, rel_path in self.DATA_DIRS.items():
            info = self.get_dir_info(name, rel_path)
            if info.exists:
                last_mod = info.last_modified.strftime('%Y-%m-%d %H:%M') if info.last_modified else 'N/A'
                print(f"{name:<25} {info.file_count:>8} {info.size_human:>12} {last_mod:>20}")
                total_size += info.size_bytes
                total_files += info.file_count
            else:
                print(f"{name:<25} {'---':>8} {'---':>12} {'(not found)':>20}")
        
        # Databases
        print("\n💾 DATABASES")
        print("-" * 70)
        print(f"{'Database':<35} {'Size':>12} {'Tables':>8} {'Status':>12}")
        print("-" * 70)
        
        for rel_path in self.DATABASES:
            info = self.get_db_info(rel_path)
            if info.exists:
                size_str = f"{info.size_bytes / 1024:.1f} KB" if info.size_bytes < 1024*1024 else f"{info.size_bytes / (1024*1024):.2f} MB"
                status = "✅ OK" if info.is_writable else "🔒 R/O"
                if info.error:
                    status = "❌ ERR"
                print(f"{rel_path:<35} {size_str:>12} {len(info.tables):>8} {status:>12}")
                total_size += info.size_bytes
            else:
                print(f"{rel_path:<35} {'---':>12} {'---':>8} {'(not found)':>12}")
        
        # Summary
        print("\n" + "=" * 70)
        total_mb = total_size / (1024 * 1024)
        print(f"📊 TOTAL: {total_files:,} files, {total_mb:.2f} MB")
        print("=" * 70 + "\n")
    
    def cmd_health(self, args):
        """Check all data endpoint health."""
        print("\n" + "=" * 70)
        print("🏥 CTHULU DATA HEALTH CHECK")
        print("=" * 70)
        
        all_healthy = True
        
        # Check directories
        print("\n[1] Directory Write Tests")
        print("-" * 40)
        for name, rel_path in self.DATA_DIRS.items():
            info = self.get_dir_info(name, rel_path)
            if not info.exists:
                print(f"  ⚠️  {name}: NOT FOUND")
            elif info.is_writable:
                print(f"  ✅ {name}: WRITABLE")
            else:
                print(f"  ❌ {name}: NOT WRITABLE")
                all_healthy = False
        
        # Check databases
        print("\n[2] Database Health")
        print("-" * 40)
        for rel_path in self.DATABASES:
            info = self.get_db_info(rel_path)
            if not info.exists:
                print(f"  ⚠️  {rel_path}: NOT FOUND")
            elif info.error:
                print(f"  ❌ {rel_path}: ERROR - {info.error}")
                all_healthy = False
            elif info.is_writable:
                total_rows = sum(v for v in info.tables.values() if v >= 0)
                print(f"  ✅ {rel_path}: OK ({len(info.tables)} tables, {total_rows:,} rows)")
            else:
                print(f"  🔒 {rel_path}: READ-ONLY")
        
        # Check recent data production
        print("\n[3] Recent Data Production (last 24h)")
        print("-" * 40)
        cutoff = datetime.now() - timedelta(hours=24)
        
        event_dirs = [
            ('ML_RL Events', 'ML_RL/data/raw'),
            ('Cognition Events', 'cognition/data/raw'),
            ('Training Events', 'ML_RL/data/training/raw'),
        ]
        
        for name, rel_path in event_dirs:
            full_path = self.root / rel_path
            if full_path.exists():
                recent_files = []
                for f in full_path.glob('*.jsonl.gz'):
                    try:
                        if datetime.fromtimestamp(f.stat().st_mtime) > cutoff:
                            recent_files.append(f)
                    except:
                        pass
                
                if recent_files:
                    print(f"  ✅ {name}: {len(recent_files)} new files")
                else:
                    print(f"  ⚠️  {name}: No new files")
            else:
                print(f"  ⚠️  {name}: Directory not found")
        
        # Summary
        print("\n" + "=" * 70)
        if all_healthy:
            print("✅ All critical endpoints healthy")
        else:
            print("❌ Some endpoints have issues - review above")
        print("=" * 70 + "\n")
        
        return 0 if all_healthy else 1
    
    def cmd_cleanup(self, args):
        """Cleanup old data files."""
        days = args.days
        dry_run = args.dry_run
        cutoff = datetime.now() - timedelta(days=days)
        
        print("\n" + "=" * 70)
        print(f"🧹 CTHULU DATA CLEANUP (older than {days} days)")
        if dry_run:
            print("   [DRY RUN - no files will be deleted]")
        print("=" * 70)
        
        total_deleted = 0
        total_bytes = 0
        
        # Cleanup event logs
        event_dirs = [
            'ML_RL/data/raw',
            'cognition/data/raw',
            'ML_RL/data/training/raw',
        ]
        
        for rel_path in event_dirs:
            full_path = self.root / rel_path
            if not full_path.exists():
                continue
            
            print(f"\n📁 {rel_path}")
            deleted = 0
            bytes_freed = 0
            
            for f in full_path.glob('*.jsonl*'):
                try:
                    mtime = datetime.fromtimestamp(f.stat().st_mtime)
                    if mtime < cutoff:
                        size = f.stat().st_size
                        if dry_run:
                            print(f"  Would delete: {f.name} ({size/1024:.1f} KB)")
                        else:
                            f.unlink()
                            print(f"  Deleted: {f.name}")
                        deleted += 1
                        bytes_freed += size
                except (OSError, PermissionError) as e:
                    print(f"  Error with {f.name}: {e}")
            
            if deleted > 0:
                print(f"  → {deleted} files, {bytes_freed/1024:.1f} KB")
                total_deleted += deleted
                total_bytes += bytes_freed
        
        # Summary
        print("\n" + "=" * 70)
        if dry_run:
            print(f"Would delete: {total_deleted} files, {total_bytes/(1024*1024):.2f} MB")
            print("Run without --dry-run to actually delete")
        else:
            print(f"Deleted: {total_deleted} files, {total_bytes/(1024*1024):.2f} MB freed")
        print("=" * 70 + "\n")
    
    def cmd_export(self, args):
        """Export data for ML training."""
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print("\n" + "=" * 70)
        print(f"📤 CTHULU DATA EXPORT")
        print(f"   Output: {output_dir.absolute()}")
        print("=" * 70)
        
        # Export event logs
        print("\n[1] Exporting Event Logs...")
        event_sources = [
            ('ML_RL/data/raw', 'ml_events'),
            ('cognition/data/raw', 'cognition_events'),
        ]
        
        for src_path, prefix in event_sources:
            full_src = self.root / src_path
            if not full_src.exists():
                print(f"  ⚠️  {src_path}: Not found, skipping")
                continue
            
            # Combine all JSONL files
            all_events = []
            for f in sorted(full_src.glob('*.jsonl.gz')):
                try:
                    with gzip.open(f, 'rt', encoding='utf-8') as gz:
                        for line in gz:
                            try:
                                event = json.loads(line.strip())
                                all_events.append(event)
                            except json.JSONDecodeError:
                                pass
                except Exception as e:
                    print(f"  Error reading {f.name}: {e}")
            
            if all_events:
                out_file = output_dir / f"{prefix}.jsonl"
                with open(out_file, 'w', encoding='utf-8') as f:
                    for event in all_events:
                        f.write(json.dumps(event) + '\n')
                print(f"  ✅ {prefix}: {len(all_events)} events → {out_file.name}")
            else:
                print(f"  ⚠️  {prefix}: No events found")
        
        # Export database tables
        print("\n[2] Exporting Database Tables...")
        for db_path in ['cthulu.db']:
            full_path = self.root / db_path
            if not full_path.exists():
                continue
            
            try:
                conn = sqlite3.connect(str(full_path), timeout=5)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall() if not row[0].startswith('_')]
                
                for table in tables:
                    cursor.execute(f"SELECT * FROM {table}")
                    rows = cursor.fetchall()
                    
                    if rows:
                        out_file = output_dir / f"db_{table}.jsonl"
                        with open(out_file, 'w', encoding='utf-8') as f:
                            for row in rows:
                                f.write(json.dumps(dict(row), default=str) + '\n')
                        print(f"  ✅ {table}: {len(rows)} rows → db_{table}.jsonl")
                
                conn.close()
            except sqlite3.Error as e:
                print(f"  ❌ {db_path}: {e}")
        
        print("\n" + "=" * 70)
        print(f"✅ Export complete: {output_dir.absolute()}")
        print("=" * 70 + "\n")
    
    def cmd_watch(self, args):
        """Real-time monitoring of data endpoints."""
        import time
        
        print("\n" + "=" * 70)
        print("👀 CTHULU DATA WATCH (Ctrl+C to stop)")
        print("=" * 70)
        
        try:
            while True:
                # Clear and redraw
                print("\033[2J\033[H")  # Clear screen
                print("=" * 70)
                print(f"👀 CTHULU DATA WATCH - {datetime.now().strftime('%H:%M:%S')}")
                print("=" * 70)
                
                # Quick status
                total_size = 0
                for name, rel_path in list(self.DATA_DIRS.items())[:6]:
                    info = self.get_dir_info(name, rel_path)
                    status = "✅" if info.is_writable else "❌"
                    print(f"  {status} {name:<25} {info.file_count:>6} files  {info.size_human:>10}")
                    total_size += info.size_bytes
                
                print("-" * 70)
                print(f"  Total: {total_size/(1024*1024):.2f} MB")
                print("\nPress Ctrl+C to stop")
                
                time.sleep(5)
        except KeyboardInterrupt:
            print("\n\nWatch stopped.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Cthulu Data Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # status command
    status_parser = subparsers.add_parser('status', help='Show storage usage summary')
    
    # health command
    health_parser = subparsers.add_parser('health', help='Check all data endpoint health')
    
    # cleanup command
    cleanup_parser = subparsers.add_parser('cleanup', help='Cleanup old data files')
    cleanup_parser.add_argument('--days', type=int, default=30,
                               help='Delete files older than N days (default: 30)')
    cleanup_parser.add_argument('--dry-run', action='store_true',
                               help='Show what would be deleted without deleting')
    
    # export command
    export_parser = subparsers.add_parser('export', help='Export data for ML training')
    export_parser.add_argument('--output', type=str, default='./exports',
                              help='Output directory (default: ./exports)')
    
    # watch command
    watch_parser = subparsers.add_parser('watch', help='Real-time data monitoring')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    cli = DataCLI()
    
    if args.command == 'status':
        cli.cmd_status(args)
    elif args.command == 'health':
        return cli.cmd_health(args)
    elif args.command == 'cleanup':
        cli.cmd_cleanup(args)
    elif args.command == 'export':
        cli.cmd_export(args)
    elif args.command == 'watch':
        cli.cmd_watch(args)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

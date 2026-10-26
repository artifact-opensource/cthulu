# Database ACLs and Permissions

To ensure the repository SQLite database (`cthulu.db` / `Cthulu.db`) is writable on deployed systems, follow these steps on Windows:

1. Take ownership of the DB file(s):

   takeown /f "C:\path\to\cthulu\cthulu.db" /a

2. Grant Modify permission to the service or user account running Cthulu:

   icacls "C:\path\to\cthulu\cthulu.db" /grant "<DOMAIN\\User>:(M)" /C
   icacls "C:\path\to\cthulu" /grant "<DOMAIN\\User>:(OI)(CI)(M)" /C

3. Remove readonly attribute if present:

   attrib -R "C:\path\to\cthulu\cthulu.db"

4. Verify by running a write test (from repo root):

   python -c "import sqlite3; conn=sqlite3.connect('cthulu.db'); c=conn.cursor(); c.execute('CREATE TABLE IF NOT EXISTS __perm_test(id INTEGER PRIMARY KEY)'); c.execute('INSERT INTO __perm_test DEFAULT VALUES'); conn.commit(); print('Insert OK'); conn.close()"

# Automated helper

A convenience script is provided: `tools\set_db_acls.ps1` which takes optional `-DbPath` and `-User` arguments. Running it with elevated privileges will set ownership and grant Modify permission.

# CI/CD recommendation

- Add a deployment step in CI that runs the `tools/set_db_acls.ps1` under an elevated account (or configure the deployment user appropriately).
- Add a health check step after deployment which runs the same write test and fails the deployment if it can't write.
- Keep the DB in the project root or explicitly set the `database.path` in `config.json` and ensure the deployment script uses that path.

## Example: GitHub Actions (Windows runner)

This example shows how a deployment workflow could grant ACLs (requires appropriate privileges on the runner) and run a quick write test as the final health check. Use with care — it requires a Windows runner that can change ACLs.

```yaml
name: Deploy and verify DB ACLs
on: workflow_dispatch
jobs:
  set-db-acl:
    runs-on: windows-2022
    steps:
      - uses: actions/checkout@v4
      - name: Grant DB ACLs
        shell: powershell
        run: |
          .\tools\set_db_acls.ps1 -DbPath '.\\cthulu.db' -User "$env:USERNAME" -Verbose
      - name: DB write health check
        shell: pwsh
        run: |
          python -c "import sqlite3,sys; conn=sqlite3.connect('cthulu.db'); c=conn.cursor(); c.execute('CREATE TABLE IF NOT EXISTS __perm_test(id INTEGER PRIMARY KEY)'); c.execute('INSERT INTO __perm_test DEFAULT VALUES'); conn.commit(); print('Insert OK'); conn.close()"
```

Note: On managed runners you may not have permission to change ACLs; prefer running these steps on your deployment host or as part of a provisioning playbook (Ansible, PowerShell DSC, etc.).

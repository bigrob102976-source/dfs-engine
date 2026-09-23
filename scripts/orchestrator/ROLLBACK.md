# Orchestrator Rollback

If the centralized orchestrator (`run_orchestrator.ps1`) misbehaves after
cutover, rollback requires **no code changes** -- only re-enabling the two
scheduled tasks it replaced and, optionally, turning the orchestrator's own
task off.

## Rollback steps

1. Re-enable the two original per-sport tasks:
   ```powershell
   Enable-ScheduledTask -TaskName "BigMoneyDFS_MLB_DK_Fetch_Worker"
   Enable-ScheduledTask -TaskName "BigMoneyDFS_NFL_DK_Fetch_Worker"
   ```
   These tasks are never deleted during cutover -- only disabled -- so this
   alone restores the exact pre-orchestrator schedule.

2. Disable the orchestrator's own task so it stops launching jobs in
   parallel with the two tasks just re-enabled (skip if it was never
   registered):
   ```powershell
   Disable-ScheduledTask -TaskName "BigMoneyDFS_Orchestrator"
   ```

3. Confirm state:
   ```powershell
   Get-ScheduledTask -TaskName "BigMoneyDFS_MLB_DK_Fetch_Worker","BigMoneyDFS_NFL_DK_Fetch_Worker","BigMoneyDFS_Orchestrator" |
     Select-Object TaskName, State
   ```
   Expect the two worker tasks `Ready`/`Running` and the orchestrator task
   `Disabled`.

That's the entire rollback. `run_mlb_dk_fetch_worker.ps1` and
`run_nfl_dk_fetch_worker.ps1` were never modified by the orchestrator work,
so the two re-enabled tasks resume running the exact same production
pipelines they always did.

## If a hung/stuck orchestrator process needs to be stopped manually

The orchestrator holds a named Mutex (`Global\BigMoneyDFS_Orchestrator`)
for single-instance protection. To stop a running instance directly rather
than through Task Scheduler:

```powershell
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
  Where-Object { $_.CommandLine -like "*run_orchestrator.ps1*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

The mutex is released automatically when the process ends (including an
abandoned-mutex release on the next orchestrator start if it was killed
abruptly), so no manual mutex cleanup is required.

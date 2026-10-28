# Legacy updater disabled: it assumes C:\CardBot_repo and fetches from main.
# Do not use until a portable, branch-aware updater has been implemented and tested.
Write-Host "[BLOCKED] This updater is unsafe for the portable build and has been disabled." -ForegroundColor Red
Write-Host "Use the reviewed rebuild/deploy-ready branch manually until the new updater is ready."
exit 2

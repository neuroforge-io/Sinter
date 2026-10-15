# Working safely on Sinter

Read [CONTRIBUTING.md](CONTRIBUTING.md) and the relevant development or release
instructions before changing the product. Preserve local work and historical
evidence; a successful source test does not qualify an installed release.

## Shared-machine operations

- Run local command workloads sequentially, including commands delegated to
  agents. Hand execution ownership over explicitly and wait for the previous
  command to finish. Agents can review and reason without launching extra jobs.
- On Linux, use `nice -n 19 ionice -c 3` for scans, tests, archiving and builds.
  Low scheduling priority is not a resource limit: also bound time, memory and
  output size as appropriate. Do not launch unattended background maintenance.
- Before a large job, check free space on every filesystem it will write to.
  Budget source copies, extraction, build outputs and temporary files together.
  Keep at least 1 GiB available, and more when the job's measured needs require it.
  Stop admission rather than exhaust the disk.
- Reuse the primary checkout or a suitable existing worktree. Create an isolated
  checkout only when needed. Reuse an unchanged frozen source snapshot instead
  of copying it for each probe. Keep runtime scratch separate from durable logs.

## Interruption and recovery

- Use one private operation directory with the source commit, intent, exact
  commands, logs, child process identities and completion status. Flush durable
  checkpoints before destructive boundaries. Never commit private runtime data.
- A yielded tool call or observation timeout is not a terminated process. Resume
  its existing handle; establish whether it finished before launching a retry.
  Signal only a process owned by this operation after verifying its identity.
  Reap its children before starting another workload.
- Preserve original inputs and uncertain remote results. Do not automatically
  replay a request whose outcome is unknown. An interrupted deletion requires
  inspection of both the remaining source and the recovery copy before retrying.

## Finish and clean up

- Confirm actual changes are merged and pushed before retiring their branches or
  checkouts. Inspect every ref in a scratch repository, not just its HEAD. Keep
  unmerged work and unique patches for explicit integration or review.
- Preserve needed ignored files before archiving a managed worktree. Keep useful
  failure reports and qualification receipts; dispose of reproducible scratch
  promptly after the evidence is secured.
- Inventory exact paths before deletion. Verify a recovery copy's contents and
  checksum, and recheck source identity, changes, mounts and active use before
  removal. Do not use broad temporary-directory globs or global prune commands.
- Protect live workspaces, credentials, browser profiles, models and other
  projects. Report held paths honestly. End with the source commit, push status,
  remaining worktrees/branches, recovery locations and measured free space.

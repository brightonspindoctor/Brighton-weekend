# Database backups

The Supabase project is on the Free plan, which keeps no backups you can
restore. `.github/workflows/backup-database.yml` makes an encrypted copy of the
database every night at 03:41 (Europe/London) and keeps it for 30 days as a
workflow artifact. Each copy holds three files made with Supabase's CLI:
`roles.sql`, `schema.sql` and `data.sql` (all tables, including sign-in
accounts). It is encrypted with AES-256 before it leaves GitHub's runner,
because anyone signed in to GitHub can download a public repository's
artifacts.

## Set it up (once)

1. In the Supabase dashboard, open the project, click **Connect**, choose
   **Session pooler** and copy the connection string. Put the database
   password in place of `[YOUR-PASSWORD]` (reset it under
   **Database → Settings** if you don't have it).
2. Make a long random passphrase, for example with a password manager's
   generator (30 characters or more). Keep it in your password manager:
   without it the backups can't be opened.
3. In GitHub, open the repository's **Settings → Secrets and variables →
   Actions** and add two repository secrets: `SUPABASE_DB_URL` (the connection
   string) and `BACKUP_PASSPHRASE` (the passphrase).
4. Under **Actions → Nightly database backup**, click **Run workflow** and
   check the run finishes with a "database-backup" artifact.

Until both secrets are set, each run stops with a warning and saves nothing.

## Open a backup

1. **Actions → Nightly database backup →** pick a run, and download the
   **database-backup** artifact (a zip).
2. Unzip it, then decrypt and unpack the copy (it asks for the passphrase):

   ```sh
   gpg --decrypt brighton-weekend-2026-10-14.tar.gz.gpg | tar -xz
   ```

The three `.sql` files hold personal data: delete them when you've finished.

## Restore

- **Into a new project** (if the old one is lost): follow Supabase's
  [Backup and Restore using the CLI](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore)
  guide from "Restore backup using CLI", using these three files. Then run the
  clean-up part of the latest `supabase/v77-…` file again (the hourly pg_cron
  job isn't in the copy), point `SUPABASE_URL` and the publishable key in
  `index.html` and `admin.html` at the new project, and set up Google sign-in
  and the sign-in emails again in its dashboard.
- **A few lost rows**: find the table's `COPY` block in `data.sql` and add the
  rows back.

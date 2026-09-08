# Brighton Weekend — Complete Latest Package (v24)

This is the complete upload package containing the latest combined app features:

## App
- Thursday–Sunday weekend view everywhere
- Discover tab
- Comedy tab
- Happenings tab
- Venues / Settings tab
- Back to Today navigation
- One-year event range support
- Sold Out event status
- Finish times where available
- Interested / Ticket Bought / Not Interested commitments
- Group-based social activity
- Multiple groups per user
- Public and private groups
- 3-digit PIN for private groups
- Happenings grouped by social circle
- New activity indicator on Happenings (red/bold + notification dot)
- Admin page
- PWA support and home-screen installation
- Home-screen install button at the bottom of Venues / Settings
- Venue selection including Komedia, The Forge Comedy Club and Theatre Royal Brighton

## Files to upload to GitHub
Upload ALL files and folders in this package to the root of:
brightonspindoctor.github.io/Brighton-weekend/

Do not upload the ZIP itself.

## Supabase
The latest required database migration is:
supabase-groups-v20.sql

Run this in Supabase SQL Editor if you have not already run it.
If you already successfully ran the groups migration, you do NOT need to run it again.

No additional Supabase migration is required for the Thursday, Comedy, Happenings notification or Home Screen button features.

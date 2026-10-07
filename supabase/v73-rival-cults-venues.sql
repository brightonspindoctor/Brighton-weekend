-- v73: venues added with the Rival Cults gig list, so people can pick them
-- when adding a community event (keep in step with VENUES in index.html).
alter table public.bw_custom_events drop constraint if exists bw_custom_events_venue_allowed;
alter table public.bw_custom_events add constraint bw_custom_events_venue_allowed check (venue in (
  'Brighton Centre','Brighton Dome','CHALK','Concorde 2','The Old Market','Green Door Store',
  'Volks','Quarters','Patterns','DUST','Komedia','The Forge Comedy Club','Theatre Royal Brighton',
  'The Hope & Ruin','The Prince Albert','A L P H A B E T','The Pipeline','Brighton Racecourse',
  'The Gladstone','Babble','Old Albion','Amex Stadium','Shelter Hall',
  'The Brunswick','Caroline of Brunswick','The Cowley Club','Daltons','The Folklore Rooms',
  'Fortune of War','Resident','The Rose Hill','Rossi Bar','The Bee''s Mouth','The Waterbear',
  'Other'
));

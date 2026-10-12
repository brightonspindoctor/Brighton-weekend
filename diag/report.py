import json,sys
a={e['id']:e for e in json.load(open('diag/before.json'))['events']}
b={e['id']:e for e in json.load(open('events.json'))['events']}
moved=[];sold=[]
for i,e in b.items():
    o=a.get(i)
    if not o:continue
    if e.get('ticket_url')!=o.get('ticket_url'):moved.append((e['venue'],e['date'],e['title'],o.get('ticket_url'),e.get('ticket_url')))
    if e.get('status')=='SOLD OUT' and o.get('status')!='SOLD OUT':sold.append((e['venue'],e['date'],e['title'],e.get('ticket_url')))
json.dump({'moved':sorted(moved),'sold':sorted(sold)},open('diag/report.json','w'),indent=1,ensure_ascii=False)
print(len(moved),'moved',len(sold),'sold')

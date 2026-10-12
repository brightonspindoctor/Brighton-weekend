import asyncio,json,sys
from pathlib import Path
from urllib.request import Request,urlopen
from playwright.async_api import async_playwright
S=json.load(open('diag/sample.json'));OUT=Path('diag/out');OUT.mkdir(exist_ok=True)
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36'
def plain(u):
    try:
        with urlopen(Request(u,headers={'User-Agent':UA,'Accept':'text/html'}),timeout=30) as r:return r.read().decode('utf-8','replace'),r.geturl(),None
    except Exception as e:return '',u,str(e)
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True);ctx=await b.new_context(user_agent=UA,locale='en-GB')
        sem=asyncio.Semaphore(6);idx=[]
        async def one(i,s):
            async with sem:
                pg=await ctx.new_page();err=None;html='';final=s['url']
                try:
                    await pg.goto(s['url'],wait_until='domcontentloaded',timeout=30000)
                    try:await pg.wait_for_load_state('networkidle',timeout=10000)
                    except Exception:pass
                    await pg.wait_for_timeout(1500);html=await pg.content();final=pg.url
                except Exception as e:err=str(e)[:200]
                finally:await pg.close()
                (OUT/f'{i}.html').write_text(html)
                ph,pf,pe=await asyncio.to_thread(plain,s['url']);(OUT/f'{i}.plain.html').write_text(ph)
                idx.append(dict(s,i=i,final=final,err=err,plain_final=pf,plain_err=pe,size=len(html),plain_size=len(ph)))
        await asyncio.gather(*(one(i,s) for i,s in enumerate(S)))
        await b.close()
    json.dump(sorted(idx,key=lambda x:x['i']),open(OUT/'index.json','w'),indent=1)
asyncio.run(main())

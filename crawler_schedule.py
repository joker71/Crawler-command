import asyncio

import schedule
import time
from nohope import crawl

schedule.every(2).hours.do(lambda: asyncio.run(crawl()))

while True:
    schedule.run_pending()
    time.sleep(10)
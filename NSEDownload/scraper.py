from bs4 import BeautifulSoup
import datetime
import requests
import os
import re
import math
import threading
import queue
import pandas as pd
from NSEDownload.static_data import get_headers, get_adjusted_headers, get_symbol_mapping_url, get_company_events_url, get_symbol_count_url

q = queue.Queue()
interm_dfs = []
incomplete_df = False

def worker_thread():

    # attempt = 0
    while True:
        
        stage, url = q.get()
        try:
            response = requests.get(url, timeout=20, headers=get_headers())
        except Exception as e:

            # if(attempt == 0):
            #     attempt = 1
            #     continue
            print("Please try again. Error has occured \n", e)
            response = None
            global incomplete_df
            incomplete_df = True

        if(response is not None and response.status_code == requests.codes.ok):

            try:
                page_content = BeautifulSoup(response.content, "html.parser")
                lines = page_content.find(id="csvContentDiv").get_text()
                lines = lines.replace(':', ", \n")

                with open(str(stage) + ".csv", "w") as file:
                    file.write(lines)

                df = pd.read_csv(str(stage) + ".csv")
                df.set_index("Date", inplace=True)
                df = df[::-1]

                interm_dfs[stage] = df

            except AttributeError:
                pass

        try:
            os.remove(str(stage) + ".csv")
        except(OSError):
            pass

        q.task_done()


def scrape_data(x, y, type, indexName=None, url=None, stockSymbol=None, symbolCount=None):

    stage, total_stages = 0, math.ceil((y-x).days/365)
    global interm_dfs, incomplete_df
    interm_dfs = [pd.DataFrame()] * total_stages
    incomplete_df = False

    threading.Thread(target=worker_thread, daemon=True).start()

    for stage in range(total_stages):

        start_date = x + stage * datetime.timedelta(days=365)
        end_date = start_date + datetime.timedelta(days=364)

        if(start_date > y):
            break

        if(end_date > y):
            end_date = y

        if(type == 'stock'):
            final_url = get_symbol_mapping_url() + '?symbol=' + stockSymbol + '&segmentLink=3&symbolCount' + symbolCount + "&series=EQ&dateRange=+&fromDate=" + \
                start_date.strftime(
                    "%d-%m-%Y")+"&toDate="+end_date.strftime("%d-%m-%Y")+"&dataType=PRICEVOLUMEDELIVERABLE"

        if(type == 'index'):
            final_url = url + '?indexType='+indexName + \
                '&fromDate=' + \
                start_date.strftime("%d-%m-%Y") + '&toDate=' + \
                end_date.strftime("%d-%m-%Y")

        q.put([stage, final_url])

    q.join()

    result = pd.DataFrame()

    if(incomplete_df == False):
        for stage in range(total_stages):
            result = pd.concat([result, interm_dfs[stage]])

        result.index = pd.to_datetime(result.index)
        result.sort_index(inplace=True)

    if(incomplete_df == True):
        print("Returning empty df as complete data not received.")

    return result


def scrape_bonus_splits(stockSymbol, event_type):

    dates, ratio = [], []

    if(not (event_type == "SPLIT" or event_type == "BONUS")):
        print("Event type not understood")
        return [ratio, dates]

    url = get_company_events_url() + stockSymbol + \
        "&Industry=&ExDt=More%20than%2024%20Months&exDt=More%20than%2024%20Months&recordDt=&bcstartDt=&industry=&CAType=" + event_type
    response = requests.get(url, timeout=60, headers=get_adjusted_headers())

    page_content = BeautifulSoup(response.content, "html.parser")
    page_content = page_content.text.replace('\n', '').replace('\t', '')

    date_start = page_content.find('exDt:"')
    date_end = page_content.find(',', date_start)

    while(date_start != -1):

        sub_start = page_content.find('Spl')
        if(event_type == "BONUS"):
            sub_start = page_content.find('Bonus')

        sub_end = page_content.find(',', sub_start)

        num = re.findall('\d+', page_content[sub_start:sub_end])

        if(event_type == "BONUS"):
            ratio.append((int(num[0])+int(num[1]))/int(num[1]))
        else:
            ratio.append(int(num[0])/int(num[1]))

        dates.append(page_content[date_start+6:date_end-1])
        page_content = page_content[date_end:-1]

        date_start = page_content.find('exDt:"')
        date_end = page_content.find(',', date_start)

    return [ratio, dates]


def scrape_symbolCount(stockSymbol):

    try:
        response = requests.post(get_symbol_count_url(), data={
                                 "symbol": stockSymbol}, headers=get_headers(), timeout=20)
    except requests.exceptions.RequestException as e:
        raise SystemExit(e)

    if(response.status_code != requests.codes.ok):
        response.raise_for_status()

    page_content = BeautifulSoup(response.content, "html.parser")
    symbolCount = str(page_content)

    return symbolCount

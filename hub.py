#standard libraries
import random
import time

import numpy as np
import pytz
import pandas
import pandas as pd
import os
import datetime as dt



#non-standard libraries
import pandas_market_calendars as mcal
from tzlocal import get_localzone
from dateutil.relativedelta import relativedelta

#internal libraries
import core_library
import dbmsIO
import multiprocessing_library as mpl
import extract_library
import transform_library

def get_clock():
    #localTZOffset = time.timezone / 3600.0
    #get local time and timezone
    nowTS = pd.Timestamp(dt.datetime.now().astimezone())
    #nowTS = pd.Timestamp(dt.datetime(year=2022, month=3, day=14, hour=3, minute=15).astimezone())

    localTZ = nowTS.tzinfo

    #convert to UTC for standard comparison
    nowUTC = nowTS.tz_convert('UTC')
    #nowUTC = nowUTC + relativedelta(days=4)
    #nowlocalTZ = pd.Timestamp(dt.datetime.now().astimezone()).tz_convert('localTZ')

    nyse = mcal.get_calendar('NYSE')

    marketSchedule = nyse.schedule(start_date=nowUTC.date() - relativedelta(years=1), end_date=nowUTC.date())
    validDays = []
    flag = True
    for i in range(len(marketSchedule.index.to_list())):
        if(flag):
            mDay = marketSchedule.index.to_list()[i]
            #print(mDay)
            if(nowUTC.date()<mDay.date()):
                validDays.append(mDay)
                flag = False
                print(mDay)
            else:
                validDays.append(mDay)

    marketSchedule = marketSchedule.loc[validDays]
    validDays.reverse()

    lastOpen = pd.Timestamp(marketSchedule['market_open'][-1])
    lastClose = pd.Timestamp(marketSchedule['market_close'][-1])
    nextOpen = pd.Timestamp(marketSchedule['market_open'][0])

    isOpen = nowUTC > lastOpen and nowUTC < lastClose
    preMarket = nowUTC < lastOpen
    postMarket = nowUTC > lastClose
    clock = {}

    clock['nowUTC'] = nowUTC
    clock['lastOpen'] = lastOpen
    clock['lastClose'] = lastClose
    clock['nextOpen'] = nextOpen

    clock['isOpen'] = isOpen
    clock['preMarket'] = preMarket
    clock['postMarket'] = postMarket

    clock['validDays'] = validDays
    clock['marketSchedule'] = marketSchedule
    print('PRINTING CLOCK')
    for key, value in clock.items():
        print(key,':  ',value)

#    print(clock)
    return clock



def gen_market_data(credentials,tckrs,settings,api,forceMDataPull=False,verbose = True):
    #check if market is open
    clock = get_clock()
    #apiClock = api.get_clock()
    #print(apiClock)

    #print(clock['marketSchedule'])


    actionDf = pd.read_csv(ROOT_DIR + r'/' + "data/ACTIONS DATA.csv")

    active_assets = transform_library.object_to_df(api.list_assets(status='active'))
    active_assets.sort_values('SYMBOL', inplace=True)
    active_assets = active_assets.reset_index(drop=True)

    #print('Market Open:', clock['marketOpen'])
    preMarket = clock['validDays'][1].date() == dt.datetime.now().date() and not clock['isOpen']
    postMarket = clock['validDays'][1].date()>dt.datetime.now().date()
    keys = list(settings['marketData'].keys())
    #keys.reverse()
    print(keys)

    for key in keys:
        #print(key)
        sourceFile = ROOT_DIR + r'/' + settings['marketData'][key]['file name']
        #print(sourceFile)
        isFileValid = (os.path.exists(sourceFile) and (
                dt.datetime.fromtimestamp(os.path.getmtime(sourceFile)).date() == dt.datetime.now().date()))
        #print('isFileValid',isFileValid)
        dataValid = (isFileValid and not forceMDataPull)
        if (clock['isOpen'] or clock['postMarket']) and key == 'DAILY MARKET DATA':
            dataValid=False
        #print('dataValid',dataValid)
        #print('')

        if (dataValid):
            print(key, 'saved Data is up to date...')
            core_library.log_entry(logFile="project_log.txt", logText=(key, ' saved Data is up to date...'),
                                   logMode='a', gap=False)
        else:

            print(key, 'Dataset is either missing or out of date, retrieving now...')
            core_library.log_entry(logFile="project_log.txt",
                                   logText=(key, ' Dataset is either missing or out of date, retrieving now...'),
                                   logMode='a', gap=False)

            offset = settings['marketData'][key]['offset']
            #if preMarket:
                #offset+=1
            #
            range = settings['marketData'][key]['range'] +offset

            if range>len(clock['validDays']):
                range=len(clock['validDays'])-1
            #print(range,offset)
            startDate = clock['validDays'][range]
            endDate = clock['validDays'][offset]
            #print(startDate.date(), endDate.date())
            #print(clock['marketSchedule'].loc[str(endDate.date())])
            #print(clock['marketSchedule'].loc[str(startDate.date())])
            #print(startDate, endDate)

            startDate = clock['marketSchedule']['market_open'].loc[str(startDate.date())]
            endDate = clock['marketSchedule']['market_close'].loc[str(endDate.date())]


            startDate = pd.Timestamp(startDate.strftime("%Y-%m-%d %H:%M:%S"), tz='UTC').isoformat()
            if (key == 'DAILY MARKET DATA'):
                if clock['isOpen']:
                    endDate =  pd.Timestamp(dt.datetime.now().astimezone()).tz_convert('UTC') - relativedelta(minutes=15)
                else:
                    endDate = endDate - relativedelta(minutes=15)
            endDate = pd.Timestamp(endDate.strftime("%Y-%m-%d %H:%M:%S"), tz='UTC').isoformat()


            #print(startDate.tzinfo)
            print('START: ', startDate,)
            print('END: ',endDate)



            #if(key == 'YESTERDAY MARKET DATA'):
            #if (key == 'DAILY MARKET DATA'):
            if (True):
            #if key == 'MONTHLY MARKET DATA':
                data = extract_library.get_iex(credentials=credentials,api=api, symbols=tckrs,
                                               timeFrame=settings['marketData'][key]['IEX']['interval'],
                                               startDate=startDate, endDate=endDate, fileName=sourceFile,
                                               actionsDf=actionDf, verbose=verbose)
                print('DATA')
                print(data)
                if not data.empty:

                    data['DATETIME'] = pd.to_datetime(data['DATETIME'])
                    #print("PRINTING DATA")
                    #print(data)
                    #print(data.info())
                    statData = transform_library.m_data_to_stats(data, fileName=key, verbose=verbose)
    #                print(statData.head(5).to_string())
                    mergedData = pd.merge(active_assets, statData, how="left", on=['SYMBOL'])
                    mergedData = mergedData.dropna(how='any').reset_index(drop=True)
                    if(key == 'YESTERDAY MARKET DATA'):
                        tckrs = mergedData['SYMBOL'].to_list()
                    dbmsIO.file_save(mergedData, sourceFile)
                    core_library.log_entry(logFile="project_log.txt", logText=(key, " Saved..."), logMode='a')


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))